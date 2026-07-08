"""Typed data models + shared helpers for Market Map Builder.

Pydantic v2 models are the single source of truth for the company schema.
They also enforce the "no fabricated data" rule: anything unknown normalizes
to explicit "unknown" / "undisclosed" rather than a guessed value.

Kept Python 3.9-compatible (typing.Optional / typing.List, no match/case).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Controlled vocabularies
# ---------------------------------------------------------------------------

# Canonical funding stages. Anything we can't confidently map -> "unknown".
FUNDING_STAGES = (
    "pre-seed",
    "seed",
    "series A",
    "series B",
    "series C",
    "growth",
    "public",
    "acquired",
    "bootstrapped",
    "unknown",
)

# Cheap normalization table for messy model output (e.g. "Series-A", "SeriesB").
_STAGE_ALIASES = {
    "preseed": "pre-seed",
    "pre seed": "pre-seed",
    "seriesa": "series A",
    "series-a": "series A",
    "seriesb": "series B",
    "series-b": "series B",
    "seriesc": "series C",
    "series-c": "series C",
    "seriesd": "growth",
    "series d": "growth",
    "series e": "growth",
    "late stage": "growth",
    "ipo": "public",
    "publicly traded": "public",
    "unknown/private": "unknown",
    "private": "unknown",
    "n/a": "unknown",
    "": "unknown",
}


def normalize_funding_stage(value: Optional[str]) -> str:
    """Map free-text stage to a canonical FUNDING_STAGES value; default 'unknown'."""
    if not value:
        return "unknown"
    raw = str(value).strip().lower()
    if raw in _STAGE_ALIASES:
        return _STAGE_ALIASES[raw]
    for stage in FUNDING_STAGES:
        if raw == stage.lower():
            return stage
    # Loose contains-match as a last resort (e.g. "series a (led by ...)").
    for stage in FUNDING_STAGES:
        if stage != "unknown" and stage.lower() in raw:
            return stage
    return "unknown"


def slugify(text: str) -> str:
    """Filesystem/Obsidian-safe slug: lowercase, ASCII, hyphen-separated.

    Wikilinks in generated notes must match the target note filename exactly
    (minus `.md`), so slugify() is the ONE authority both the writer and the
    linker call — never hand-roll a slug elsewhere.
    """
    # Strip accents -> ASCII (e.g. "Coderabbit™" -> "coderabbit").
    normalized = unicodedata.normalize("NFKD", str(text))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.lower()
    # Replace any run of non-alphanumerics with a single hyphen.
    ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text)
    ascii_text = ascii_text.strip("-")
    return ascii_text or "untitled"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Company(BaseModel):
    """A single company in a sector map."""

    name: str
    one_line_description: str = ""
    founded_year: Optional[int] = None
    funding_stage: str = "unknown"
    total_funding_disclosed: str = "undisclosed"
    key_differentiator: str = ""
    target_customer: str = ""
    related_companies: List[str] = Field(default_factory=list)
    source_urls: List[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _name_not_empty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Company.name cannot be empty")
        return v

    @field_validator("funding_stage")
    @classmethod
    def _valid_stage(cls, v: str) -> str:
        return normalize_funding_stage(v)

    @field_validator("founded_year")
    @classmethod
    def _sane_year(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return None
        # Reject obviously fabricated / nonsensical years rather than trust them.
        current = datetime.now(timezone.utc).year
        if v < 1970 or v > current + 1:
            return None
        return v

    @property
    def slug(self) -> str:
        return slugify(self.name)


class SectorResearch(BaseModel):
    """The full result of researching one sector."""

    sector_name: str
    researched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    companies: List[Company] = Field(default_factory=list)
    # "live" = real web-search research; "mock" = free offline sample data.
    source: str = "live"

    @property
    def sector_slug(self) -> str:
        return slugify(self.sector_name)

    def company_by_slug(self, slug: str) -> Optional[Company]:
        for c in self.companies:
            if c.slug == slug:
                return c
        return None
