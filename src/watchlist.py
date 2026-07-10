"""Watchlist + portfolio overlay — track many sectors, watch your companies.

State lives in `vault/_watchlist.md` (the vault IS the database — human-
editable markdown, no side-car JSON):

    # Watchlist
    ## Sectors
    - AI coding assistants
    ## Portfolio
    - Cursor

* `run_watchlist()` refreshes + digests every tracked sector in one pass and
  writes a combined digest to `vault/_digest-YYYY-MM-DD.md`.
* Portfolio companies get a ★ in every hub table they appear in.
* `overlay()` answers "where does <portfolio company> sit?": which maps it is
  in, its rivals there, and which rivals moved recently (changelog entries).

Kept Python 3.9-compatible.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from .digest import post_webhook, run_digest
from .models import slugify
from .vault_writer import extract_changelog, parse_company_note

WATCHLIST_BASENAME = "_watchlist.md"


# ---------------------------------------------------------------------------
# Watchlist file
# ---------------------------------------------------------------------------

def watchlist_path(vault_path: str) -> str:
    return os.path.join(vault_path, WATCHLIST_BASENAME)


def load_watchlist(vault_path: str) -> Dict[str, List[str]]:
    """Parse the watchlist file -> {'sectors': [...], 'portfolio': [...]}."""
    out = {"sectors": [], "portfolio": []}
    try:
        with open(watchlist_path(vault_path), encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return out
    section = None
    for line in text.splitlines():
        stripped = line.strip()
        m = re.match(r"^##\s+(.+)$", stripped)
        if m:
            title = m.group(1).strip().lower()
            section = "sectors" if title.startswith("sector") else (
                "portfolio" if title.startswith("portfolio") else None)
            continue
        if section and stripped.startswith("- "):
            item = stripped[2:].strip()
            if item and item not in out[section]:
                out[section].append(item)
    return out


def save_watchlist(vault_path: str, data: Dict[str, List[str]]) -> str:
    os.makedirs(vault_path, exist_ok=True)
    lines = [
        "---",
        "type: watchlist",
        "updated: %s" % datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "---",
        "",
        "# Watchlist",
        "",
        "## Sectors",
        "",
    ]
    lines += ["- %s" % s for s in data.get("sectors", [])] or ["_none tracked yet_"]
    lines += ["", "## Portfolio", ""]
    lines += ["- %s" % p for p in data.get("portfolio", [])] or ["_none tracked yet_"]
    lines.append("")
    path = watchlist_path(vault_path)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return path


def add_item(vault_path: str, kind: str, value: str) -> bool:
    """Add a sector/portfolio entry. Returns False if already present."""
    data = load_watchlist(vault_path)
    slugs = {slugify(v) for v in data[kind]}
    if slugify(value) in slugs:
        return False
    data[kind].append(value)
    save_watchlist(vault_path, data)
    return True


def remove_item(vault_path: str, kind: str, value: str) -> bool:
    data = load_watchlist(vault_path)
    target = slugify(value)
    kept = [v for v in data[kind] if slugify(v) != target]
    if len(kept) == len(data[kind]):
        return False
    data[kind] = kept
    save_watchlist(vault_path, data)
    return True


def portfolio_slugs(vault_path: str) -> set:
    return {slugify(p) for p in load_watchlist(vault_path)["portfolio"]}


# ---------------------------------------------------------------------------
# Run: refresh + digest every tracked sector
# ---------------------------------------------------------------------------

def run_watchlist(
    vault_path: str = "./vault",
    num_companies: int = 12,
    mock: bool = False,
    quiet: bool = False,
    webhook: Optional[str] = None,
) -> Dict[str, object]:
    data = load_watchlist(vault_path)
    if not data["sectors"]:
        raise FileNotFoundError(
            "Watchlist has no sectors. Add one with: watchlist add \"<sector>\""
        )
    portfolio = portfolio_slugs(vault_path)

    sections: List[str] = []
    per_sector = []
    for sector in data["sectors"]:
        out = run_digest(
            sector, vault_path=vault_path, num_companies=num_companies,
            mock=mock, quiet=quiet, webhook=None, portfolio=portfolio,
        )
        per_sector.append((sector, out))
        sections.append(out["text"])

    date = datetime.now(timezone.utc).date().isoformat()
    combined = (
        "# Watchlist digest · %s\n\n_%d sector(s) refreshed._\n\n---\n\n" % (date, len(per_sector))
        + "\n---\n\n".join(sections)
    )
    combined_path = os.path.join(vault_path, "_digest-%s.md" % date)
    with open(combined_path, "w", encoding="utf-8") as fh:
        fh.write(combined)

    delivered = post_webhook(webhook, combined) if webhook else False
    return {
        "digest_path": combined_path,
        "text": combined,
        "sectors": per_sector,
        "delivered": delivered,
    }


# ---------------------------------------------------------------------------
# Overlay: where does a portfolio company sit?
# ---------------------------------------------------------------------------

def overlay(
    company: str, vault_path: str = "./vault", recent_days: int = 30
) -> Dict[str, object]:
    """Scan every sector map for `company`; report rivals + recent rival moves."""
    slug = slugify(company)
    hits = []
    if not os.path.isdir(vault_path):
        raise FileNotFoundError("Vault %s does not exist — run `map` first." % vault_path)

    cutoff = datetime.now(timezone.utc) - timedelta(days=recent_days)

    for entry in sorted(os.listdir(vault_path)):
        sector_dir = os.path.join(vault_path, entry)
        note_path = os.path.join(sector_dir, slug + ".md")
        if not os.path.isdir(sector_dir) or not os.path.exists(note_path):
            continue
        with open(note_path, encoding="utf-8") as fh:
            parsed = parse_company_note(fh.read())

        rivals = []
        for rival_name in parsed.get("related_companies", []):
            rival_slug = slugify(rival_name)
            rival_path = os.path.join(sector_dir, rival_slug + ".md")
            recent_moves: List[str] = []
            if os.path.exists(rival_path):
                with open(rival_path, encoding="utf-8") as fh:
                    for line in extract_changelog(fh.read()):
                        m = re.search(r"\*\*(\d{4}-\d{2}-\d{2})", line)
                        if not m:
                            continue
                        try:
                            when = datetime.strptime(m.group(1), "%Y-%m-%d").replace(
                                tzinfo=timezone.utc)
                        except ValueError:
                            continue
                        if when >= cutoff:
                            recent_moves.append(line.lstrip("- ").strip())
            rivals.append({"name": rival_name, "slug": rival_slug,
                           "recent_moves": recent_moves})

        hits.append({
            "sector": entry,
            "note_path": note_path,
            "stage": parsed.get("funding_stage", "unknown"),
            "last_verified": parsed.get("last_verified", ""),
            "rivals": rivals,
        })

    return {"company": company, "slug": slug, "hits": hits}


def render_overlay(report: Dict[str, object]) -> str:
    """Human-readable overlay report."""
    hits = report["hits"]
    if not hits:
        return (
            "'%s' does not appear in any mapped sector.\n"
            "Map a sector it belongs to first: map \"<sector>\"" % report["company"]
        )
    lines = ["Position report: %s" % report["company"], ""]
    for h in hits:
        lines.append("● %s  (stage: %s, verified: %s)" % (
            h["sector"], h["stage"], h["last_verified"] or "—"))
        if not h["rivals"]:
            lines.append("    no rivals recorded in this map")
        for r in h["rivals"]:
            flag = ""
            if r["recent_moves"]:
                flag = "  ⚠ moved recently"
            lines.append("    vs %s%s" % (r["name"], flag))
            for mv in r["recent_moves"]:
                lines.append("        · %s" % mv)
        lines.append("")
    return "\n".join(lines)
