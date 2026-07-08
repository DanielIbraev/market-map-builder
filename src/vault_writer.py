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

from .models import Company, SectorResearch, slugify
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
) -> Dict[str, object]:
    """Write the full vault for `research`. Returns paths + a link-check result.

    `summary` lets a caller (e.g. refresh) pass a pre-computed landscape summary
    so we don't spend a second API call. If None, we generate one.
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
    _write_file(hub_path, _render_hub_note(research, summary))

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
# Rendering
# ---------------------------------------------------------------------------

def _render_company_note(company: Company, research: SectorResearch) -> str:
    sector_slug = research.sector_slug
    founded = str(company.founded_year) if company.founded_year else "unknown"

    fm = [
        "---",
        "company: %s" % _yaml_scalar(company.name),
        "sector: %s" % _yaml_scalar(research.sector_name),
        "funding_stage: %s" % _yaml_scalar(company.funding_stage),
        "founded: %s" % (company.founded_year if company.founded_year else "unknown"),
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
        "- **Total disclosed funding:** %s" % (company.total_funding_disclosed or "undisclosed"),
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
    if company.source_urls:
        for url in company.source_urls:
            body.append("- %s" % url)
    else:
        body.append("_No sources recorded._")

    if research.source == "mock":
        body += ["", "---", "> ⚠️ **Sample data** (offline mock mode) — illustrative only, verify before citing."]

    body.append("")  # trailing newline
    return "\n".join(fm) + "\n".join(body)


def _render_hub_note(research: SectorResearch, summary: str) -> str:
    sector = research.sector_name
    sector_slug = research.sector_slug
    companies = research.companies

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
        "| Company | Stage | Founded | One-liner |",
        "| --- | --- | --- | --- |",
    ]
    for c in companies:
        founded = str(c.founded_year) if c.founded_year else "—"
        oneliner = _table_cell(c.one_line_description)
        lines.append(
            "| %s | %s | %s | %s |" % (_wikilink(c.name), c.funding_stage, founded, oneliner)
        )
    if not companies:
        lines.append("| _none found_ | | | |")

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
