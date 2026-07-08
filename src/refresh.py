"""Refresh mode — re-run research on an existing sector and diff into the vault.

Rules (from the spec):
* Re-run research, then diff against existing notes.
* Changed company -> update its note AND append a timestamped `## Changelog` entry.
* New company -> add a note and link it from the (regenerated) hub.
* Never duplicate notes — companies are matched on slugified name.

The vault is the database: prior state is read back out of the notes themselves
(via vault_writer.parse_company_note), not a side-car file.

Kept Python 3.9-compatible.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from .models import Company, SectorResearch, normalize_funding_stage, slugify
from .research import generate_landscape_summary, research_sector
from . import vault_writer as vw


def refresh_sector(
    sector: str,
    vault_path: str = "./vault",
    num_companies: int = 12,
    mock: bool = False,
    quiet: bool = False,
) -> Dict[str, object]:
    """Refresh an existing sector map in place. Returns a change summary."""
    new_research = research_sector(sector, num_companies=num_companies, mock=mock, quiet=quiet)
    sector_slug = new_research.sector_slug
    sector_dir = os.path.join(vault_path, sector_slug)

    existing = _load_existing_notes(sector_dir)

    # No prior map -> this is effectively a first run.
    if not existing:
        result = vw.write_vault(new_research, vault_path=vault_path, quiet=quiet)
        return {
            "mode": "created",
            "sector_dir": result["sector_dir"],
            "hub_path": result["hub_path"],
            "added": [c.name for c in new_research.companies],
            "updated": [],
            "unchanged": [],
            "retained": [],
            "broken_links": result["broken_links"],
        }

    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%d %H:%M UTC")

    added: List[str] = []
    updated: List[Tuple[str, List[str]]] = []
    unchanged: List[str] = []
    new_slugs = set()

    for company in new_research.companies:
        new_slugs.add(company.slug)
        prior = existing.get(company.slug)
        if prior is None:
            # Brand-new company -> new note with an "added" changelog entry.
            vw.write_company_note(
                company,
                new_research,
                vault_path,
                changelog=["- **%s** — Added to the map." % stamp],
            )
            added.append(company.name)
            continue

        changes = _diff(prior, company)
        if changes:
            entry = "- **%s** — %s." % (stamp, "; ".join(changes))
            changelog = list(prior.get("changelog", [])) + [entry]
            vw.write_company_note(company, new_research, vault_path, changelog=changelog)
            updated.append((company.name, changes))
        else:
            unchanged.append(company.name)  # leave the note untouched

    # Companies that were in the vault but not re-found this run: keep their
    # notes as-is, but reconstruct them so the regenerated hub stays complete.
    retained: List[str] = []
    retained_companies: List[Company] = []
    for slug, prior in existing.items():
        if slug in new_slugs:
            continue
        retained.append(prior.get("name") or slug)
        retained_companies.append(vw.reconstruct_company(prior))

    # Regenerate ONLY the hub from the merged set (never rewrites company notes).
    merged = SectorResearch(
        sector_name=new_research.sector_name,
        companies=list(new_research.companies) + retained_companies,
        source=new_research.source,
        researched_at=now,
    )
    summary = generate_landscape_summary(merged, mock=mock)
    hub_path = vw.write_hub_note(merged, vault_path, summary=summary)

    broken = vw.verify_vault_links(sector_dir)

    if not quiet:
        _report(added, updated, unchanged, retained, broken)

    return {
        "mode": "refreshed",
        "sector_dir": sector_dir,
        "hub_path": hub_path,
        "added": added,
        "updated": updated,
        "unchanged": unchanged,
        "retained": retained,
        "broken_links": broken,
    }


# ---------------------------------------------------------------------------
# Diffing
# ---------------------------------------------------------------------------

def _diff(prior: dict, new: Company) -> List[str]:
    """Human-readable list of what changed between an old note and new data."""
    changes: List[str] = []

    old_stage = normalize_funding_stage(prior.get("funding_stage"))
    if old_stage != new.funding_stage:
        changes.append("funding stage: %s → %s" % (old_stage, new.funding_stage))

    old_year = prior.get("founded_year")
    if old_year != new.founded_year:
        changes.append(
            "founded: %s → %s"
            % (old_year if old_year else "unknown", new.founded_year if new.founded_year else "unknown")
        )

    old_fund = (prior.get("total_funding_disclosed") or "").strip()
    new_fund = (new.total_funding_disclosed or "").strip()
    if old_fund != new_fund:
        changes.append("total funding: %s → %s" % (old_fund or "undisclosed", new_fund or "undisclosed"))

    if _norm(prior.get("key_differentiator")) != _norm(new.key_differentiator):
        changes.append("differentiator updated")

    if _norm(prior.get("target_customer")) != _norm(new.target_customer):
        changes.append("target customer updated")

    if _norm(prior.get("one_line_description")) != _norm(new.one_line_description):
        changes.append("description updated")

    old_rel = {slugify(r) for r in prior.get("related_companies", [])}
    new_rel = {slugify(r) for r in new.related_companies}
    if old_rel != new_rel:
        changes.append("related companies updated")

    return changes


def _norm(text: Optional[str]) -> str:
    return " ".join((text or "").split()).strip().lower()


# ---------------------------------------------------------------------------
# Existing-note loading
# ---------------------------------------------------------------------------

def _load_existing_notes(sector_dir: str) -> Dict[str, dict]:
    """Map slug -> parsed note dict for every company note in the sector dir."""
    existing: Dict[str, dict] = {}
    if not os.path.isdir(sector_dir):
        return existing
    for fn in os.listdir(sector_dir):
        if not fn.endswith(".md") or fn.startswith("_"):
            continue  # skip the hub note (_..-map.md)
        slug = fn[:-3]
        try:
            with open(os.path.join(sector_dir, fn), encoding="utf-8") as fh:
                parsed = vw.parse_company_note(fh.read())
        except OSError:
            continue
        existing[slug] = parsed
    return existing


def _report(added, updated, unchanged, retained, broken) -> None:
    try:
        from rich.console import Console  # type: ignore

        p = Console().print
    except Exception:
        p = print
    p("Refresh complete: %d added, %d updated, %d unchanged, %d retained."
      % (len(added), len(updated), len(unchanged), len(retained)))
    for name in added:
        p("  + added: %s" % name)
    for name, changes in updated:
        p("  ~ updated: %s (%s)" % (name, "; ".join(changes)))
    if broken:
        p("  WARNING: %d broken wikilink(s)." % len(broken))
