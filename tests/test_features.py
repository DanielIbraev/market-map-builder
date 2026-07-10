"""Tests for the VC-workflow features: provenance, digest, export, memo.

Offline (mock) — no API key required.
Run with: pytest  |  python -m tests.test_features
"""
from __future__ import annotations

import csv
import json
import os
import tempfile

from src.digest import render_digest, run_digest
from src.export import export_sector, load_sector_rows
from src.memo import write_memo
from src.models import Company
from src.refresh import refresh_sector
from src.research import research_sector
from src.vault_writer import parse_company_note, write_vault

SECTOR = "AI coding assistants"


def _build(vault):
    r = research_sector(SECTOR, num_companies=12, mock=True, quiet=True)
    write_vault(r, vault_path=vault, quiet=True)
    return r


# --- provenance -------------------------------------------------------------

def test_notes_carry_citations_and_freshness():
    with tempfile.TemporaryDirectory() as vault:
        _build(vault)
        with open(os.path.join(vault, "ai-coding-assistants", "cursor.md"), encoding="utf-8") as fh:
            text = fh.read()
        assert "last_verified:" in text
        assert "_Facts verified as of" in text
        parsed = parse_company_note(text)
        assert parsed["citations"].get("general") == "https://cursor.com"
        assert parsed["last_round"].startswith("Series B")
        assert "Thrive Capital" in parsed["lead_investors"]
        assert parsed["last_verified"]


def test_deal_memo_fields_roundtrip_through_refresh():
    with tempfile.TemporaryDirectory() as vault:
        _build(vault)
        res = refresh_sector(SECTOR, vault_path=vault, mock=True, quiet=True)
        assert res["updated"] == [], res["updated"]  # nothing falsely 'changed'


# --- digest ------------------------------------------------------------------

def test_digest_reports_movement_and_writes_note():
    with tempfile.TemporaryDirectory() as vault:
        r = _build(vault)
        # Make one company stale so the digest has something to say.
        import re
        p = os.path.join(vault, "ai-coding-assistants", "cursor.md")
        with open(p, encoding="utf-8") as fh:
            text = fh.read()
        text = text.replace("- **Funding stage:** growth", "- **Funding stage:** seed")
        text = re.sub(r"^funding_stage: growth$", "funding_stage: seed", text, flags=re.M)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)

        out = run_digest(SECTOR, vault_path=vault, mock=True, quiet=True)
        assert os.path.exists(out["digest_path"])
        assert "seed → growth" in out["text"]
        assert "Moved" in out["text"]


def test_digest_render_no_movement():
    fake = {"added": [], "updated": [], "unchanged": ["A"], "retained": [],
            "broken_links": [], "hub_path": "/x/_y-map.md"}
    text = render_digest(SECTOR, fake)
    assert "No movement detected" in text


# --- export ------------------------------------------------------------------

def test_export_csv_has_all_companies_and_columns():
    with tempfile.TemporaryDirectory() as vault:
        r = _build(vault)
        path = export_sector(SECTOR, vault_path=vault, fmt="csv")
        with open(path, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == len(r.companies)
        cursor = next(row for row in rows if row["name"] == "Cursor")
        assert cursor["funding_stage"] == "growth"
        assert "Thrive Capital" in cursor["lead_investors"]
        assert cursor["last_verified"]
        assert "https://cursor.com" in cursor["sources"]


def test_export_json():
    with tempfile.TemporaryDirectory() as vault:
        _build(vault)
        path = export_sector(SECTOR, vault_path=vault, fmt="json")
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        assert isinstance(data, list) and data
        assert {"name", "last_round", "investors"} <= set(data[0].keys())


def test_export_missing_sector_errors():
    with tempfile.TemporaryDirectory() as vault:
        try:
            export_sector("never mapped", vault_path=vault)
            assert False, "expected FileNotFoundError"
        except FileNotFoundError:
            pass


# --- memo ---------------------------------------------------------------------

def test_memo_offline_grounded_and_flags_unknowns():
    with tempfile.TemporaryDirectory() as vault:
        _build(vault)
        path = write_memo(SECTOR, "Zed", vault_path=vault, mock=True, quiet=True)
        assert os.path.exists(path)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        assert "DRAFT" in text
        assert "[[zed]]" in text                      # wikilinked to the note
        assert "Open questions for diligence" in text
        # Zed's funding is unknown -> must surface as a question, not a value.
        assert "total capital raised" in text.lower()
        assert "## Sources" in text


def test_memo_unknown_company_errors():
    with tempfile.TemporaryDirectory() as vault:
        _build(vault)
        try:
            write_memo(SECTOR, "Nonexistent Corp", vault_path=vault, mock=True, quiet=True)
            assert False, "expected FileNotFoundError"
        except FileNotFoundError as exc:
            assert "not in the" in str(exc)


# --- static site builder ------------------------------------------------------

def test_site_builder_outputs_catalog_and_sector_json():
    from src.site_builder import build_site
    with tempfile.TemporaryDirectory() as vault, tempfile.TemporaryDirectory() as site:
        _build(vault)
        out = build_site(vault_path=vault, site_dir=site, quiet=True)
        assert "ai-coding-assistants" in out["sectors"]

        with open(os.path.join(site, "data", "catalog.json"), encoding="utf-8") as fh:
            cat = json.load(fh)
        acs = [s for c in cat["categories"] for s in c["subsectors"]
               if s["slug"] == "ai-coding-assistants"][0]
        assert acs["mapped"] and acs["companies"] == 10
        assert cat["stats"]["mapped"] == 1

        with open(os.path.join(site, "data", "ai-coding-assistants.json"), encoding="utf-8") as fh:
            data = json.load(fh)
        cursor = next(c for c in data["companies"] if c["id"] == "cursor")
        assert cursor["fM"] == 400.0                      # "$400M+" parsed
        assert "github-copilot" in cursor["rel"]          # relations as slugs
        assert cursor["lead"] == "Thrive Capital"
        assert data["source"] == "mock" and data["summary"]


# --- watchlist / portfolio overlay -------------------------------------------

def test_watchlist_roundtrip_and_run():
    from src.watchlist import add_item, load_watchlist, remove_item, run_watchlist
    with tempfile.TemporaryDirectory() as vault:
        assert add_item(vault, "sectors", SECTOR)
        assert not add_item(vault, "sectors", SECTOR)          # no duplicates
        assert add_item(vault, "portfolio", "Cursor")
        data = load_watchlist(vault)
        assert data["sectors"] == [SECTOR] and data["portfolio"] == ["Cursor"]

        out = run_watchlist(vault_path=vault, mock=True, quiet=True)
        assert os.path.exists(out["digest_path"])
        assert "Watchlist digest" in out["text"]

        # Portfolio company is starred in the hub it appears in.
        hub = os.path.join(vault, "ai-coding-assistants", "_ai-coding-assistants-map.md")
        with open(hub, encoding="utf-8") as fh:
            assert "★ Cursor" in fh.read()

        assert remove_item(vault, "portfolio", "Cursor")
        assert load_watchlist(vault)["portfolio"] == []


def test_overlay_reports_position_and_recent_rival_moves():
    from src.watchlist import overlay, render_overlay
    with tempfile.TemporaryDirectory() as vault:
        _build(vault)
        # Give a rival (GitHub Copilot) a fresh changelog entry.
        res = None
        p = os.path.join(vault, "ai-coding-assistants", "github-copilot.md")
        with open(p, encoding="utf-8") as fh:
            text = fh.read()
        from datetime import datetime, timezone
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        with open(p, "a", encoding="utf-8") as fh:
            fh.write("\n## Changelog\n- **%s** — funding stage: seed → public.\n" % stamp)

        report = overlay("Cursor", vault_path=vault)
        assert len(report["hits"]) == 1
        hit = report["hits"][0]
        assert hit["sector"] == "ai-coding-assistants"
        rival_names = {r["name"] for r in hit["rivals"]}
        assert "GitHub Copilot" in rival_names
        copilot = next(r for r in hit["rivals"] if r["name"] == "GitHub Copilot")
        assert copilot["recent_moves"], "recent changelog entry should be surfaced"
        text = render_overlay(report)
        assert "moved recently" in text


def test_overlay_absent_company():
    from src.watchlist import overlay, render_overlay
    with tempfile.TemporaryDirectory() as vault:
        _build(vault)
        report = overlay("Ghost Startup", vault_path=vault)
        assert report["hits"] == []
        assert "does not appear" in render_overlay(report)


def _run_all():
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
            passed += 1
    print("\n%d test(s) passed." % passed)


if __name__ == "__main__":
    _run_all()
