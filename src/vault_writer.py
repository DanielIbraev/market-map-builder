"""Obsidian vault writer — turns SectorResearch into interlinked markdown notes.

The vault (a folder of .md files) IS the database. No plugins, no Obsidian API.

Layout produced under `{vault_path}/{sector_slug}/`:
    _{sector_slug}-map.md    <- hub note (table, summary, Mermaid graph)
    {company_slug}.md        <- one note per company

Wikilink integrity is load-bearing: every `[[target]]` must equal a note's
filename minus `.md`, or Obsidian won't resolve it. `slugify()` (from models)
is the single authority for both filenames and link targets, and
`verify_vault_links()` proves the invariant after writing.

Kept Python 3.9-compatible.
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

from .models import Company, SectorResearch, is_unknown, slugify
from .research import generate_landscape_summary

WIKILINK_RE = re.compile(r"\[\[([^\]\|]+)(?:\|[^\]]*)?\]\]")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_vault(
    research: SectorResearch,
    vault_path: str = "./vault",
    summary: Optional[str] = None,
    quiet: bool = False,
    portfolio: Optional[set] = None,
) -> Dict[str, object]:
    """Write the full vault for `research`. Returns paths + a link-check result.

    `summary` lets a caller (e.g. refresh) pass a pre-computed landscape summary
    so we don't spend a second API call. If None, we generate one.
    `portfolio` is an optional set of company slugs to star in the hub table.
    """
    sector_slug = research.sector_slug
    sector_dir = os.path.join(vault_path, sector_slug)
    os.makedirs(sector_dir, exist_ok=True)

    written: List[str] = []

    # --- company notes -----------------------------------------------------
    for company in research.companies:
        path = os.path.join(sector_dir, company.slug + ".md")
        _write_file(path, _render_company_note(company, research))
        written.append(path)

    # --- hub note ----------------------------------------------------------
    if summary is None:
        summary = generate_landscape_summary(research)
    hub_path = os.path.join(sector_dir, "_%s-map.md" % sector_slug)
    _write_file(hub_path, _render_hub_note(research, summary, portfolio=portfolio))

    broken = verify_vault_links(sector_dir)

    if not quiet:
        _print("Wrote %d company notes + hub to %s" % (len(written), sector_dir))
        if broken:
            _print("WARNING: %d broken wikilink(s) detected." % len(broken))

    return {
        "sector_dir": sector_dir,
        "hub_path": hub_path,
        "company_notes": written,
        "broken_links": broken,
    }


def verify_vault_links(sector_dir: str) -> List[Tuple[str, str]]:
    """Return [(note_filename, broken_target)] for every unresolved wikilink.

    A target resolves if `{target}.md` exists in the same sector directory.
    """
    existing = {
        fn[:-3]
        for fn in os.listdir(sector_dir)
        if fn.endswith(".md")
    }
    broken: List[Tuple[str, str]] = []
    for fn in sorted(existing):
        full = os.path.join(sector_dir, fn + ".md")
        try:
            text = _read_file(full)
        except OSError:
            continue
        for target in WIKILINK_RE.findall(text):
            target = target.strip()
            if target and target not in existing:
                broken.append((fn + ".md", target))
    return broken


# ---------------------------------------------------------------------------
# Single-artifact writers (used by refresh so it can update in place)
# ---------------------------------------------------------------------------

def company_note_path(vault_path: str, research: SectorResearch, company: Company) -> str:
    return os.path.join(vault_path, research.sector_slug, company.slug + ".md")


def write_company_note(
    company: Company,
    research: SectorResearch,
    vault_path: str,
    changelog: Optional[List[str]] = None,
) -> str:
    os.makedirs(os.path.join(vault_path, research.sector_slug), exist_ok=True)
    path = company_note_path(vault_path, research, company)
    _write_file(path, _render_company_note(company, research, changelog=changelog))
    return path


def write_hub_note(
    research: SectorResearch,
    vault_path: str,
    summary: Optional[str] = None,
    portfolio: Optional[set] = None,
) -> str:
    os.makedirs(os.path.join(vault_path, research.sector_slug), exist_ok=True)
    if summary is None:
        summary = generate_landscape_summary(research)
    path = os.path.join(vault_path, research.sector_slug, "_%s-map.md" % research.sector_slug)
    _write_file(path, _render_hub_note(research, summary, portfolio=portfolio))
    return path


# ---------------------------------------------------------------------------
# Note parsing (read an existing note back into a Company + its changelog)
# ---------------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(r"^_.*_$")


def parse_company_note(text: str) -> dict:
    """Best-effort parse of a generated note back into comparable fields.

    Only extracts what refresh diffs on; formatting/round-trip fidelity is not
    a goal. Returns a dict of the Company-ish fields plus 'changelog' (raw lines).
    """
    out = {
        "name": "",
        "one_line_description": "",
        "founded_year": None,
        "funding_stage": "unknown",
        "total_funding_disclosed": "undisclosed",
        "key_differentiator": "",
        "target_customer": "",
        "related_companies": [],
        "source_urls": [],
        "last_round": "",
        "lead_investors": [],
        "investors": [],
        "headcount": "",
        "hq": "",
        "business_model": "",
        "notable_customers": [],
        "founders": [],
        "citations": {},
        "last_verified": "",
        "changelog": [],
    }

    # Frontmatter
    fm_match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).splitlines():
            m = re.match(r"^([a-zA-Z_]+):\s*(.*)$", line)
            if not m:
                continue
            key, val = m.group(1), m.group(2).strip()
            val = _unquote_yaml(val)
            if key == "company":
                out["name"] = val
            elif key == "funding_stage":
                out["funding_stage"] = val or "unknown"
            elif key == "founded":
                out["founded_year"] = int(val) if val.isdigit() else None
            elif key == "last_verified":
                out["last_verified"] = "" if is_unknown(val) else val

    # Title (authoritative name if present)
    title = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if title:
        out["name"] = title.group(1).strip()

    out["one_line_description"] = _clean_para(_section_between(text, r"^#\s+.+$", "## Details"))
    out["key_differentiator"] = _clean_para(
        _section_between(text, "## What makes them different", "##")
    )

    details = _section_between(text, "## Details", "##")
    out["total_funding_disclosed"] = _detail(details, "Total disclosed funding") or "undisclosed"
    out["target_customer"] = _detail(details, "Target customer") or ""
    founded_detail = _detail(details, "Founded")
    if out["founded_year"] is None and founded_detail and founded_detail.isdigit():
        out["founded_year"] = int(founded_detail)

    # Deal-memo detail bullets ("unknown" collapses back to empty).
    def _scalar_detail(label):
        v = _detail(details, label)
        return "" if is_unknown(v) else v

    def _list_detail(label):
        v = _detail(details, label)
        if is_unknown(v):
            return []
        return [p.strip() for p in v.split(";") if p.strip()]

    out["last_round"] = _scalar_detail("Last round")
    out["headcount"] = _scalar_detail("Headcount")
    out["hq"] = _scalar_detail("HQ")
    out["business_model"] = _scalar_detail("Business model")
    out["lead_investors"] = _list_detail("Lead investors")
    out["investors"] = _list_detail("Investors")
    out["notable_customers"] = _list_detail("Notable customers")
    out["founders"] = _list_detail("Founders")

    related_block = _section_between(text, "## Related companies", "##")
    for target, alias in re.findall(r"\[\[([^\]\|]+)(?:\|([^\]]*))?\]\]", related_block):
        out["related_companies"].append((alias or target).strip())

    sources_block = _section_between(text, "## Sources", "##")
    for line in sources_block.splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        cited = re.match(r"-\s*\*\*(.+?)\*\*\s*—\s*(\S+)", line)
        if cited:
            out["citations"][cited.group(1).strip().lower()] = cited.group(2).strip()
        elif "http" in line:
            out["source_urls"].append(line[2:].strip())

    out["changelog"] = extract_changelog(text)
    return out


def reconstruct_company(parsed: dict) -> Company:
    """Rebuild a Company from a parsed note (for companies not re-found)."""
    return Company(
        name=parsed.get("name") or "Unknown",
        one_line_description=parsed.get("one_line_description", ""),
        founded_year=parsed.get("founded_year"),
        funding_stage=parsed.get("funding_stage", "unknown"),
        total_funding_disclosed=parsed.get("total_funding_disclosed", "undisclosed"),
        key_differentiator=parsed.get("key_differentiator", ""),
        target_customer=parsed.get("target_customer", ""),
        related_companies=list(parsed.get("related_companies", [])),
        source_urls=list(parsed.get("source_urls", [])),
        last_round=parsed.get("last_round", ""),
        lead_investors=list(parsed.get("lead_investors", [])),
        investors=list(parsed.get("investors", [])),
        headcount=parsed.get("headcount", ""),
        hq=parsed.get("hq", ""),
        business_model=parsed.get("business_model", ""),
        notable_customers=list(parsed.get("notable_customers", [])),
        founders=list(parsed.get("founders", [])),
        citations=dict(parsed.get("citations", {})),
        last_verified=parsed.get("last_verified", ""),
    )


def extract_changelog(text: str) -> List[str]:
    """Return the raw '- ...' bullet lines under an existing '## Changelog'."""
    block = _section_between(text, "## Changelog", "##")
    return [ln.rstrip() for ln in block.splitlines() if ln.strip().startswith("- ")]


def _section_between(text: str, start_pat: str, stop_literal: str) -> str:
    m = re.search(start_pat, text, re.MULTILINE)
    if not m:
        return ""
    rest = text[m.end():]
    stop = rest.find("\n" + stop_literal)
    return (rest if stop < 0 else rest[:stop]).strip()


def _detail(details_block: str, label: str) -> str:
    m = re.search(r"-\s*\*\*%s:\*\*\s*(.+)" % re.escape(label), details_block)
    return m.group(1).strip() if m else ""


def _clean_para(text: str) -> str:
    text = text.strip()
    if not text or _PLACEHOLDER_RE.match(text):
        return ""
    # Collapse the (usually single) paragraph into one line.
    return " ".join(text.split())


def _unquote_yaml(val: str) -> str:
    val = val.strip()
    if len(val) >= 2 and val[0] == '"' and val[-1] == '"':
        return val[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return val


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_company_note(
    company: Company,
    research: SectorResearch,
    changelog: Optional[List[str]] = None,
) -> str:
    sector_slug = research.sector_slug
    founded = str(company.founded_year) if company.founded_year else "unknown"

    fm = [
        "---",
        "company: %s" % _yaml_scalar(company.name),
        "sector: %s" % _yaml_scalar(research.sector_name),
        "funding_stage: %s" % _yaml_scalar(company.funding_stage),
        "founded: %s" % (company.founded_year if company.founded_year else "unknown"),
        "last_verified: %s" % (company.last_verified or "unknown"),
        "tags: [company, %s]" % sector_slug,
        "---",
        "",
    ]

    body = [
        "# %s" % company.name,
        "",
        company.one_line_description or "_No description available._",
        "",
        "## Details",
        "- **Founded:** %s" % founded,
        "- **Funding stage:** %s" % company.funding_stage,
        "- **Last round:** %s" % _or_unknown(company.last_round),
        "- **Lead investors:** %s" % _join_or_unknown(company.lead_investors),
        "- **Total disclosed funding:** %s" % (company.total_funding_disclosed or "undisclosed"),
        "- **Investors:** %s" % _join_or_unknown(company.investors),
        "- **Headcount:** %s" % _or_unknown(company.headcount),
        "- **HQ:** %s" % _or_unknown(company.hq),
        "- **Business model:** %s" % _or_unknown(company.business_model),
        "- **Notable customers:** %s" % _join_or_unknown(company.notable_customers),
        "- **Founders:** %s" % _join_or_unknown(company.founders),
        "- **Target customer:** %s" % (company.target_customer or "unknown"),
        "",
        "## What makes them different",
        company.key_differentiator or "_Not documented._",
        "",
        "## Related companies",
    ]
    if company.related_companies:
        for rel in company.related_companies:
            body.append("- %s" % _wikilink(rel))
    else:
        body.append("_No direct competitors identified in this map._")

    body += ["", "## Sources"]
    cited_urls = set()
    for label in sorted(company.citations):
        url = company.citations[label]
        body.append("- **%s** — %s" % (label.strip().lower(), url))
        cited_urls.add(url)
    for url in company.source_urls:
        if url not in cited_urls:
            body.append("- %s" % url)
    if not company.citations and not company.source_urls:
        body.append("_No sources recorded._")
    if company.last_verified:
        body += ["", "_Facts verified as of %s._" % company.last_verified]

    if research.source == "mock":
        body += ["", "---", "> ⚠️ **Sample data** (offline mock mode) — illustrative only, verify before citing."]

    # Changelog is always the LAST section so refresh can append to it in place.
    if changelog:
        body += ["", "## Changelog"]
        body += list(changelog)

    body.append("")  # trailing newline
    return "\n".join(fm) + "\n".join(body)


def _render_hub_note(
    research: SectorResearch, summary: str, portfolio: Optional[set] = None
) -> str:
    sector = research.sector_name
    sector_slug = research.sector_slug
    companies = research.companies
    portfolio = portfolio or set()

    lines = [
        "---",
        "type: sector-map",
        "sector: %s" % _yaml_scalar(sector),
        "researched_at: %s" % research.researched_at.strftime("%Y-%m-%d %H:%M UTC"),
        "company_count: %d" % len(companies),
        "tags: [sector-map, %s]" % sector_slug,
        "---",
        "",
        "# %s — Market Map" % sector,
        "",
        "_%d companies · researched %s · source: %s_"
        % (len(companies), research.researched_at.strftime("%Y-%m-%d"), research.source),
        "",
    ]

    if research.source == "mock":
        lines += ["> ⚠️ **Sample data** (offline mock mode) — illustrative only, verify before citing.", ""]

    # --- table -------------------------------------------------------------
    lines += [
        "## Companies",
        "",
        "| Company | Stage | Founded | Last round | One-liner | Verified |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for c in companies:
        founded = str(c.founded_year) if c.founded_year else "—"
        oneliner = _table_cell(c.one_line_description)
        star = "★ " if c.slug in portfolio else ""
        link = "[[%s|%s%s]]" % (c.slug, star, c.name)
        last_round = _table_cell(c.last_round) if not is_unknown(c.last_round) else "—"
        verified = c.last_verified or "—"
        lines.append(
            "| %s | %s | %s | %s | %s | %s |"
            % (link, c.funding_stage, founded, last_round, oneliner, verified)
        )
    if not companies:
        lines.append("| _none found_ | | | | | |")
    if portfolio:
        lines += ["", "_★ = portfolio company (from the watchlist)._"]

    # --- landscape summary -------------------------------------------------
    lines += ["", "## Landscape summary", "", summary.strip() or "_Not available._", ""]

    # --- graph -------------------------------------------------------------
    lines += ["## Relationship graph", "", _mermaid_block(companies), ""]

    return "\n".join(lines)


def _mermaid_block(companies: List[Company]) -> str:
    if not companies:
        return "```mermaid\ngraph TD\n  empty[\"No companies\"]\n```"

    by_slug = {c.slug: c for c in companies}
    out = ["```mermaid", "graph TD"]

    # Declare every node first so isolated companies still render.
    for c in companies:
        out.append("  %s[\"%s\"]" % (_mermaid_id(c.slug), _mermaid_label(c.name)))

    seen_edges = set()
    for c in companies:
        for rel in c.related_companies:
            rel_slug = slugify(rel)
            if rel_slug not in by_slug:
                continue
            key = (c.slug, rel_slug)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            out.append("  %s --> %s" % (_mermaid_id(c.slug), _mermaid_id(rel_slug)))

    out.append("```")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _wikilink(name: str) -> str:
    """`[[slug|Name]]` — target is the filename (slug); alias is the readable name."""
    return "[[%s|%s]]" % (slugify(name), name)


def _mermaid_id(slug: str) -> str:
    ident = slug.replace("-", "_")
    if not ident or not ident[0].isalpha():
        ident = "n_" + ident
    return ident


def _mermaid_label(name: str) -> str:
    # Quotes inside a "..." label break Mermaid; swap for a safe char.
    return name.replace('"', "'").replace("[", "(").replace("]", ")")


def _or_unknown(value: str) -> str:
    return value.strip() if value and value.strip() else "unknown"


def _join_or_unknown(items: List[str]) -> str:
    # ';' separator: entries themselves may contain commas ("finance, defense").
    items = [i.strip() for i in (items or []) if i and i.strip()]
    return "; ".join(items) if items else "unknown"


def _table_cell(text: str) -> str:
    text = (text or "").replace("\n", " ").replace("|", "\\|").strip()
    if len(text) > 90:
        text = text[:87].rstrip() + "…"
    return text or "—"


def _yaml_scalar(value: str) -> str:
    """Quote a YAML scalar when it contains characters that would break parsing."""
    s = str(value)
    if s == "":
        return '""'
    if re.search(r"[:#\[\]{}\",&*!|>%@`]", s) or s.strip() != s or s[0] in "-?":
        return '"%s"' % s.replace("\\", "\\\\").replace('"', '\\"')
    return s


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------

def _write_file(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def _read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _print(msg: str) -> None:
    try:
        from rich.console import Console  # type: ignore

        Console().print(msg)
    except Exception:
        print(msg)
