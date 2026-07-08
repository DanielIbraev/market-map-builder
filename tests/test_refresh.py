"""Refresh-mode tests: diff detection, changelog, add/retain, idempotency.

Offline (mock) — no API key required.
Run with: pytest  |  python -m tests.test_refresh
"""
from __future__ import annotations

import os
import tempfile

from src.models import Company
from src.refresh import refresh_sector
from src.research import research_sector
from src.vault_writer import write_vault

SECTOR = "AI coding assistants"


def _seed_stale_vault(vault: str):
    """Write a vault with deliberately stale data to diff against."""
    r = research_sector(SECTOR, num_companies=12, mock=True, quiet=True)
    r.companies = [c for c in r.companies if c.slug != "continue"]  # drop one
    for c in r.companies:
        if c.slug == "cursor":
            c.funding_stage = "seed"
            c.total_funding_disclosed = "$20M"
            c.key_differentiator = "Old differentiator."
    r.companies.append(Company(name="OldCo", one_line_description="Only in old vault.",
                               funding_stage="seed", related_companies=["Cursor"]))
    write_vault(r, vault_path=vault, quiet=True)


def test_refresh_detects_changes_adds_and_retains():
    with tempfile.TemporaryDirectory() as vault:
        _seed_stale_vault(vault)
        res = refresh_sector(SECTOR, vault_path=vault, mock=True, quiet=True)

        assert res["mode"] == "refreshed"
        assert "Continue" in res["added"]
        assert "OldCo" in res["retained"]
        updated_names = [n for n, _ in res["updated"]]
        assert "Cursor" in updated_names
        assert res["broken_links"] == []

        cursor = os.path.join(vault, "ai-coding-assistants", "cursor.md")
        with open(cursor, encoding="utf-8") as fh:
            text = fh.read()
        assert "## Changelog" in text
        assert "seed → growth" in text


def test_refresh_is_idempotent():
    with tempfile.TemporaryDirectory() as vault:
        _seed_stale_vault(vault)
        refresh_sector(SECTOR, vault_path=vault, mock=True, quiet=True)
        res2 = refresh_sector(SECTOR, vault_path=vault, mock=True, quiet=True)
        assert res2["updated"] == []
        assert res2["added"] == []
        # No duplicate changelog entries piled up on Cursor.
        cursor = os.path.join(vault, "ai-coding-assistants", "cursor.md")
        with open(cursor, encoding="utf-8") as fh:
            text = fh.read()
        assert text.count("seed → growth") == 1


def test_refresh_on_empty_vault_creates_it():
    with tempfile.TemporaryDirectory() as vault:
        res = refresh_sector(SECTOR, vault_path=vault, mock=True, quiet=True)
        assert res["mode"] == "created"
        assert len(res["added"]) > 0
        assert res["broken_links"] == []


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
