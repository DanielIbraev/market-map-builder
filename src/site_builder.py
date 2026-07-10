"""Static site builder — turn the vault into a deployable, zero-backend atlas.

Security model (why static): the deployed site is pure files — no server, no
runtime API calls, no credentials anywhere in the frontend. Research happens
locally via the CLI (key stays in .env on your machine); this module just
serializes the resulting vault into JSON the pages fetch relatively.
Nothing to hack, nothing to steal, free to host anywhere static.

Outputs into `docs/site/`:
    data/catalog.json      <- taxonomy x vault: which sectors are mapped
    data/<sector>.json     <- per-sector payload for map.html

Kept Python 3.9-compatible.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .export import load_sector_rows
from .memo import _hub_summary  # reuse the hub-summary extractor
from .models import slugify
from .taxonomy import TAXONOMY

DEFAULT_SITE_DIR = os.path.join("docs", "site")


def build_site(vault_path: str = "./vault", site_dir: str = DEFAULT_SITE_DIR,
               quiet: bool = False) -> Dict[str, object]:
    """Serialize every mapped sector + the catalog. Returns a build summary."""
    data_dir = os.path.join(site_dir, "data")
    os.makedirs(data_dir, exist_ok=True)

    mapped = _mapped_sectors(vault_path)
    built: List[str] = []
    total_companies = 0

    for slug, meta in mapped.items():
        payload = _sector_payload(meta["name"], vault_path)
        if payload is None:
            continue
        with open(os.path.join(data_dir, "%s.json" % slug), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        built.append(slug)
        total_companies += len(payload["companies"])
        mapped[slug]["companies"] = len(payload["companies"])
        mapped[slug]["source"] = payload["source"]

    catalog = _catalog(mapped)
    with open(os.path.join(data_dir, "catalog.json"), "w", encoding="utf-8") as fh:
        json.dump(catalog, fh, ensure_ascii=False)

    if not quiet:
        print("Site data built: %d sector(s), %d companies -> %s"
              % (len(built), total_companies, data_dir))
    return {"site_dir": site_dir, "sectors": built,
            "companies": total_companies, "catalog": catalog}


# ---------------------------------------------------------------------------
# Vault -> payloads
# ---------------------------------------------------------------------------

def _mapped_sectors(vault_path: str) -> Dict[str, dict]:
    """slug -> {name} for every sector directory in the vault."""
    out: Dict[str, dict] = {}
    if not os.path.isdir(vault_path):
        return out
    for entry in sorted(os.listdir(vault_path)):
        sector_dir = os.path.join(vault_path, entry)
        hub = os.path.join(sector_dir, "_%s-map.md" % entry)
        if not os.path.isdir(sector_dir) or not os.path.exists(hub):
            continue
        name = entry.replace("-", " ")
        source = "live"
        try:
            with open(hub, encoding="utf-8") as fh:
                head = fh.read(2000)
            m = re.search(r"^sector:\s*\"?(.+?)\"?\s*$", head, re.MULTILINE)
            if m:
                name = m.group(1)
            if "source: mock" in head:
                source = "mock"
        except OSError:
            pass
        out[entry] = {"name": name, "source": source}
    return out


def _sector_payload(sector_name: str, vault_path: str) -> Optional[dict]:
    try:
        rows = load_sector_rows(sector_name, vault_path=vault_path)
    except FileNotFoundError:
        return None
    slug = slugify(sector_name)
    hub = os.path.join(vault_path, slug, "_%s-map.md" % slug)
    source = "live"
    try:
        with open(hub, encoding="utf-8") as fh:
            if "source: mock" in fh.read(2000):
                source = "mock"
    except OSError:
        pass

    present = {r["slug"] for r in rows}
    companies = []
    for r in rows:
        cites = r.get("citations") or {}
        src = cites.get("general") or next(iter(cites.values()), None) \
            or (r.get("source_urls") or [None])[0]
        companies.append({
            "id": r["slug"],
            "name": r.get("name") or r["slug"],
            "stage": r.get("funding_stage") or "unknown",
            "founded": r.get("founded_year"),
            "funding": r.get("total_funding_disclosed") or "undisclosed",
            "fM": _funding_millions(r.get("total_funding_disclosed")),
            "round": r.get("last_round") or "",
            "lead": "; ".join(r.get("lead_investors") or []),
            "inv": "; ".join(r.get("investors") or []),
            "hc": r.get("headcount") or "",
            "hq": r.get("hq") or "",
            "bm": r.get("business_model") or "",
            "fnd": "; ".join(r.get("founders") or []),
            "target": r.get("target_customer") or "",
            "desc": r.get("one_line_description") or "",
            "diff": r.get("key_differentiator") or "",
            "rel": [s for s in (slugify(x) for x in r.get("related_companies") or [])
                    if s in present],
            "src": src or "",
            "verified": r.get("last_verified") or "",
        })
    return {
        "sector": sector_name,
        "slug": slug,
        "source": source,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "summary": _hub_summary(sector_name, vault_path),
        "companies": companies,
    }


def _funding_millions(text: Optional[str]):
    """'$400M+', '~$1.2B (reported)' -> millions as a number; None if unknown."""
    if not text:
        return None
    m = re.search(r"\$\s*([\d,]+(?:\.\d+)?)\s*([MmBb])", text)
    if not m:
        return None
    val = float(m.group(1).replace(",", ""))
    if m.group(2).lower() == "b":
        val *= 1000
    return round(val, 1)


def _catalog(mapped: Dict[str, dict]) -> dict:
    seen = set()
    categories = []
    for cat, subs in TAXONOMY.items():
        entries = []
        for name in subs:
            slug = slugify(name)
            seen.add(slug)
            info = mapped.get(slug)
            entries.append({
                "name": name, "slug": slug,
                "mapped": info is not None,
                "companies": (info or {}).get("companies", 0),
                "source": (info or {}).get("source", ""),
            })
        categories.append({"name": cat, "subsectors": entries})

    custom = [
        {"name": info["name"], "slug": slug, "mapped": True,
         "companies": info.get("companies", 0), "source": info.get("source", "")}
        for slug, info in mapped.items() if slug not in seen
    ]
    n_mapped = sum(1 for c in categories for s in c["subsectors"] if s["mapped"]) + len(custom)
    n_companies = sum(s["companies"] for c in categories for s in c["subsectors"]) \
        + sum(c["companies"] for c in custom)
    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "stats": {
            "subsectors": sum(len(c["subsectors"]) for c in categories) + len(custom),
            "mapped": n_mapped,
            "companies": n_companies,
        },
        "categories": categories,
        "custom": custom,
    }
