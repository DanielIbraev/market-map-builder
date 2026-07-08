"""Link-integrity test: every [[wikilink]] in every generated note must resolve.

Runs fully offline (mock engine) — no API key required.
Run with either:  pytest    |    python -m tests.test_vault_links
"""
from __future__ import annotations

import os
import tempfile

from src.research import research_sector
from src.vault_writer import verify_vault_links, write_vault, WIKILINK_RE


def _build(sector: str, n: int, tmp: str):
    research = research_sector(sector, num_companies=n, mock=True, quiet=True)
    return write_vault(research, vault_path=tmp, quiet=True), research


def test_no_broken_links_curated():
    with tempfile.TemporaryDirectory() as tmp:
        result, _ = _build("AI coding assistants", 12, tmp)
        assert result["broken_links"] == [], result["broken_links"]


def test_no_broken_links_generic():
    with tempfile.TemporaryDirectory() as tmp:
        result, _ = _build("quantum networking hardware", 8, tmp)
        assert result["broken_links"] == [], result["broken_links"]


def test_every_wikilink_target_has_a_file():
    """Belt-and-suspenders: independently re-scan the vault for link targets."""
    with tempfile.TemporaryDirectory() as tmp:
        result, _ = _build("AI coding assistants", 10, tmp)
        sector_dir = result["sector_dir"]
        note_names = {fn[:-3] for fn in os.listdir(sector_dir) if fn.endswith(".md")}
        for fn in os.listdir(sector_dir):
            if not fn.endswith(".md"):
                continue
            with open(os.path.join(sector_dir, fn), encoding="utf-8") as fh:
                for target in WIKILINK_RE.findall(fh.read()):
                    assert target.strip() in note_names, (fn, target)


def test_hub_note_exists_and_links_all_companies():
    with tempfile.TemporaryDirectory() as tmp:
        result, research = _build("AI coding assistants", 10, tmp)
        with open(result["hub_path"], encoding="utf-8") as fh:
            hub = fh.read()
        for c in research.companies:
            assert ("[[%s|" % c.slug) in hub, c.slug


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
