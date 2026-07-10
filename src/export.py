"""Exports — get sector data OUT of the vault, into the tools VCs live in.

Reads straight from the vault notes (the vault IS the database), so exports
are free, offline, and always reflect what's on disk — including manual edits.

Formats:
* CSV  — Airtable / Google Sheets / Excel ready, one row per company.
* JSON — machine-readable, same fields.

Kept Python 3.9-compatible.
"""
from __future__ import annotations

import csv
import json
import os
from typing import Dict, List, Optional

from .models import slugify
from .vault_writer import parse_company_note

CSV_COLUMNS = [
    "name", "funding_stage", "founded_year", "total_funding_disclosed",
    "last_round", "lead_investors", "investors", "headcount", "hq",
    "business_model", "notable_customers", "founders", "target_customer",
    "one_line_description", "key_differentiator", "related_companies",
    "sources", "last_verified",
]


def load_sector_rows(sector: str, vault_path: str = "./vault") -> List[Dict[str, object]]:
    """Parse every company note in a sector back into dicts (skips the hub)."""
    sector_dir = os.path.join(vault_path, slugify(sector))
    if not os.path.isdir(sector_dir):
        raise FileNotFoundError(
            "No vault found for '%s' at %s — run `map` first." % (sector, sector_dir)
        )
    rows: List[Dict[str, object]] = []
    for fn in sorted(os.listdir(sector_dir)):
        if not fn.endswith(".md") or fn.startswith("_"):
            continue
        with open(os.path.join(sector_dir, fn), encoding="utf-8") as fh:
            parsed = parse_company_note(fh.read())
        parsed["slug"] = fn[:-3]
        rows.append(parsed)
    if not rows:
        raise FileNotFoundError("No company notes found in %s." % sector_dir)
    return rows


def _row_to_flat(parsed: Dict[str, object]) -> Dict[str, str]:
    """Flatten a parsed note into CSV-safe string cells."""
    def join(key):  # lists -> '; ' cells (entries may contain commas)
        return "; ".join(parsed.get(key) or [])

    sources = list((parsed.get("citations") or {}).values())
    for u in parsed.get("source_urls") or []:
        if u not in sources:
            sources.append(u)

    return {
        "name": parsed.get("name") or "",
        "funding_stage": parsed.get("funding_stage") or "unknown",
        "founded_year": str(parsed.get("founded_year") or ""),
        "total_funding_disclosed": parsed.get("total_funding_disclosed") or "",
        "last_round": parsed.get("last_round") or "",
        "lead_investors": join("lead_investors"),
        "investors": join("investors"),
        "headcount": parsed.get("headcount") or "",
        "hq": parsed.get("hq") or "",
        "business_model": parsed.get("business_model") or "",
        "notable_customers": join("notable_customers"),
        "founders": join("founders"),
        "target_customer": parsed.get("target_customer") or "",
        "one_line_description": parsed.get("one_line_description") or "",
        "key_differentiator": parsed.get("key_differentiator") or "",
        "related_companies": join("related_companies"),
        "sources": "; ".join(sources),
        "last_verified": parsed.get("last_verified") or "",
    }


def export_sector(
    sector: str,
    vault_path: str = "./vault",
    fmt: str = "csv",
    out_path: Optional[str] = None,
) -> str:
    """Export a sector to CSV or JSON. Returns the written file path."""
    fmt = (fmt or "csv").strip().lower()
    if fmt not in ("csv", "json"):
        raise ValueError("Format must be 'csv' or 'json'.")

    rows = load_sector_rows(sector, vault_path=vault_path)
    sector_slug = slugify(sector)
    sector_dir = os.path.join(vault_path, sector_slug)
    if out_path is None:
        out_path = os.path.join(sector_dir, "_%s-export.%s" % (sector_slug, fmt))

    flat = [_row_to_flat(r) for r in rows]

    if fmt == "csv":
        with open(out_path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(flat)
    else:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(flat, fh, indent=2, ensure_ascii=False)
            fh.write("\n")

    return out_path
