"""First-draft deal memos — the intern's least favorite document, generated.

Builds a grounded draft memo for one company from its vault note plus the
sector context (rivals' notes + hub landscape summary):

* Live mode: Claude writes the narrative (call lives in research.py, per the
  security rule) — grounded ONLY in the vault notes it is given.
* Mock / no-key mode: a structured template memo assembled from the same
  notes. Every UNKNOWN field becomes an explicit open diligence question —
  honest gaps instead of hallucinated filler.

Output: vault/{sector}/memos/{company}-memo-{date}.md  (wikilinked back to
the company note, so it joins the Obsidian graph).

Kept Python 3.9-compatible.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .models import is_unknown, slugify
from .research import generate_memo_body
from .export import load_sector_rows


def write_memo(
    sector: str,
    company: str,
    vault_path: str = "./vault",
    mock: bool = False,
    quiet: bool = False,
) -> str:
    """Generate and write a draft memo. Returns the memo file path."""
    rows = load_sector_rows(sector, vault_path=vault_path)
    target_slug = slugify(company)
    target = None
    for r in rows:
        if r.get("slug") == target_slug or slugify(r.get("name") or "") == target_slug:
            target = r
            break
    if target is None:
        names = ", ".join(sorted(r.get("name") or r.get("slug") for r in rows))
        raise FileNotFoundError(
            "'%s' is not in the %s map. Companies present: %s" % (company, sector, names)
        )

    rivals = [r for r in rows if r is not target and _is_rival(target, r)]
    summary = _hub_summary(sector, vault_path)
    date = datetime.now(timezone.utc).date().isoformat()

    body = None
    if not mock:
        try:
            body = generate_memo_body(sector, target, rivals, summary)
        except RuntimeError as exc:
            if not quiet:
                print("Note: %s Falling back to the offline template memo." % exc)
    if body is None:
        body = _template_memo(sector, target, rivals, summary, date)

    header = _memo_header(sector, target, date, mock or body is None)
    memos_dir = os.path.join(vault_path, slugify(sector), "memos")
    os.makedirs(memos_dir, exist_ok=True)
    path = os.path.join(memos_dir, "%s-memo-%s.md" % (target["slug"], date))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(header + body.rstrip() + "\n")
    return path


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def _memo_header(sector: str, t: dict, date: str, offline: bool) -> str:
    lines = [
        "---",
        "type: deal-memo-draft",
        "company: %s" % t.get("name"),
        "sector: %s" % sector,
        "generated: %s" % date,
        "tags: [deal-memo, draft, %s]" % slugify(sector),
        "---",
        "",
        "> **DRAFT — machine-generated first pass.** Grounded only in the vault "
        "notes as of %s%s. Verify every figure against the cited sources before "
        "circulating." % (t.get("last_verified") or date,
                          " (offline template)" if offline else ""),
        "",
    ]
    return "\n".join(lines)


def _template_memo(sector, t, rivals, summary, date) -> str:
    name = t.get("name") or "Unknown"
    lines: List[str] = ["# Deal memo (draft): %s" % name, ""]

    # --- snapshot ---
    lines += [
        "## Snapshot",
        "",
        "- **What they do:** %s" % _v(t.get("one_line_description")),
        "- **Stage / founded:** %s · %s" % (t.get("funding_stage") or "unknown",
                                            t.get("founded_year") or "unknown"),
        "- **Last round:** %s" % _v(t.get("last_round")),
        "- **Total disclosed:** %s" % _v(t.get("total_funding_disclosed")),
        "- **Lead investors:** %s" % _vl(t.get("lead_investors")),
        "- **Investors:** %s" % _vl(t.get("investors")),
        "- **Headcount / HQ:** %s · %s" % (_v(t.get("headcount")), _v(t.get("hq"))),
        "- **Business model:** %s" % _v(t.get("business_model")),
        "- **Founders:** %s" % _vl(t.get("founders")),
        "- **Full note:** [[%s]]" % t["slug"],
        "",
    ]

    # --- market ---
    lines += ["## Market context", ""]
    if summary:
        lines += [summary, ""]
    lines += ["The %s map currently tracks %d direct or adjacent players." %
              (sector, len(rivals) + 1), ""]

    # --- positioning ---
    lines += ["## Competitive positioning", "",
              "**Their edge:** %s" % _v(t.get("key_differentiator")), ""]
    if rivals:
        lines += ["| Rival | Stage | Their edge |", "| --- | --- | --- |"]
        for r in rivals:
            lines.append("| [[%s\\|%s]] | %s | %s |" % (
                r["slug"], r.get("name") or r["slug"],
                r.get("funding_stage") or "unknown",
                _cell(r.get("key_differentiator"))))
        lines.append("")
    else:
        lines += ["_No direct rivals identified in the current map._", ""]

    # --- customers ---
    lines += ["## Customer & go-to-market", "",
              "- **Target customer:** %s" % _v(t.get("target_customer")),
              "- **Notable customers:** %s" % _vl(t.get("notable_customers")), ""]

    # --- open questions from the gaps ---
    questions = _open_questions(t)
    lines += ["## Open questions for diligence", ""]
    for q in questions:
        lines.append("- [ ] %s" % q)
    lines.append("")

    # --- sources ---
    lines += ["## Sources", ""]
    cites: Dict[str, str] = t.get("citations") or {}
    if cites:
        for label in sorted(cites):
            lines.append("- **%s** — %s" % (label, cites[label]))
    for u in t.get("source_urls") or []:
        if u not in cites.values():
            lines.append("- %s" % u)
    if not cites and not (t.get("source_urls") or []):
        lines.append("_No sources recorded — treat all facts above as unverified._")
    lines.append("")
    return "\n".join(lines)


def _open_questions(t: dict) -> List[str]:
    """Every unknown field becomes an explicit diligence question."""
    qs: List[str] = []
    checks = [
        (t.get("last_round"), "What was the most recent round (stage, size, date, valuation)?"),
        (t.get("lead_investors"), "Who led the last round, and are insiders following on?"),
        (t.get("total_funding_disclosed"), "What is total capital raised to date?"),
        (t.get("headcount"), "Current headcount and 12-month growth trajectory?"),
        (t.get("business_model"), "How do they monetize (pricing, contract size, margins)?"),
        (t.get("notable_customers"), "Reference customers and logo quality — who pays today?"),
        (t.get("founders"), "Founding team background and prior outcomes?"),
        (t.get("hq"), "Where is the team based, and is it distributed?"),
    ]
    for value, q in checks:
        empty = (not value) if isinstance(value, list) else is_unknown(value)
        if empty:
            qs.append(q)
    # Always-on associate questions.
    qs += [
        "Revenue scale and growth rate (none of this is in public sources)?",
        "Churn/retention signals — do customers renew and expand?",
        "What would have to be true for this to be a fund-returner in this market?",
    ]
    return qs


def _is_rival(t: dict, other: dict) -> bool:
    rel = {slugify(x) for x in (t.get("related_companies") or [])}
    orel = {slugify(x) for x in (other.get("related_companies") or [])}
    return other["slug"] in rel or slugify(t.get("name") or "") in orel


def _hub_summary(sector: str, vault_path: str) -> str:
    slug = slugify(sector)
    hub = os.path.join(vault_path, slug, "_%s-map.md" % slug)
    try:
        with open(hub, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return ""
    m = re.search(r"## Landscape summary\n+(.*?)(?:\n## |\Z)", text, re.DOTALL)
    return m.group(1).strip() if m else ""


def _v(value: Optional[str]) -> str:
    return "**UNKNOWN**" if is_unknown(value) else str(value).strip()


def _vl(values: Optional[List[str]]) -> str:
    values = [v for v in (values or []) if v.strip()]
    return "; ".join(values) if values else "**UNKNOWN**"


def _cell(text: Optional[str]) -> str:
    t = " ".join((text or "").split()).replace("|", "\\|")
    if len(t) > 110:
        t = t[:107].rstrip() + "…"
    return t or "—"
