"""Research engine — the ONLY module that touches the Anthropic API or the key.

Design / security notes
------------------------
* The API key is read from the environment (loaded from .env by python-dotenv)
  exclusively inside `_get_client()`. It is never passed as a function argument,
  never printed, never logged, and never written into the vault.
* `anthropic` is imported lazily inside the live path, so the free offline
  `--mock` engine runs with no SDK and no key installed.
* All user-supplied text is validated by `validate_query()` BEFORE it reaches
  the API — stripped, length-limited, character-whitelisted, non-empty.
* We never fabricate funding/date data: anything the model can't verify is left
  as "unknown" / "undisclosed" (see models.normalize_funding_stage and the
  extraction prompt below).

Kept Python 3.9-compatible.
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import List, Optional

from .models import FUNDING_STAGES, Company, SectorResearch

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Model + server tool. Sonnet 4.6 supports the improved web-search variant with
# dynamic filtering (fewer tokens, better results). Change here if you need the
# basic `web_search_20250305` variant (e.g. on a platform that lacks the newer
# one).
MODEL = os.environ.get("MARKET_MAP_MODEL", "claude-sonnet-4-6")
WEB_SEARCH_TOOL_TYPE = os.environ.get("MARKET_MAP_WEB_SEARCH_TOOL", "web_search_20260209")

# Input-validation limits (defense-in-depth before any API call).
MIN_QUERY_LEN = 2
MAX_QUERY_LEN = 80
# Letters, digits, spaces, and a small set of punctuation real sector/company
# names use. Deliberately conservative to reject junk / injection-ish input.
_QUERY_ALLOWED = re.compile(r"^[A-Za-z0-9 .,/&+#'\-()]+$")

MIN_COMPANIES = 4
MAX_COMPANIES = 25

# Bound the server-side web-search continuation loop (pause_turn handling).
_MAX_CONTINUATIONS = 6


# ---------------------------------------------------------------------------
# Terminal progress (Rich if available, plain print otherwise)
# ---------------------------------------------------------------------------

class _Printer:
    def __init__(self, quiet: bool = False) -> None:
        self.quiet = quiet
        self._console = None
        if not quiet:
            try:
                from rich.console import Console  # type: ignore

                self._console = Console(stderr=False)
            except Exception:
                self._console = None

    def info(self, msg: str) -> None:
        if self.quiet:
            return
        if self._console is not None:
            self._console.print(msg)
        else:
            print(_strip_markup(msg))

    def warn(self, msg: str) -> None:
        text = "[yellow]⚠ " + msg + "[/yellow]"
        if self.quiet:
            # Warnings still matter even when quiet -> stderr, unstyled.
            print("WARNING: " + msg, file=sys.stderr)
            return
        if self._console is not None:
            self._console.print(text)
        else:
            print("WARNING: " + msg, file=sys.stderr)


def _strip_markup(msg: str) -> str:
    return re.sub(r"\[/?[a-zA-Z0-9 =#]+\]", "", msg)


# ---------------------------------------------------------------------------
# Input validation (runs before any API call)
# ---------------------------------------------------------------------------

def validate_query(text: str) -> str:
    """Validate + normalize a sector/company query. Raises ValueError if unsafe.

    Returns the cleaned string (collapsed whitespace, stripped).
    """
    if text is None:
        raise ValueError("Query is required.")
    cleaned = " ".join(str(text).split())  # collapse/normalize whitespace
    if len(cleaned) < MIN_QUERY_LEN:
        raise ValueError("Query is too short (min %d characters)." % MIN_QUERY_LEN)
    if len(cleaned) > MAX_QUERY_LEN:
        raise ValueError("Query is too long (max %d characters)." % MAX_QUERY_LEN)
    if not _QUERY_ALLOWED.match(cleaned):
        raise ValueError(
            "Query contains unsupported characters. Use letters, numbers, "
            "spaces and basic punctuation (. , / & + # ' - ( ))."
        )
    return cleaned


def _clamp_num_companies(n: int) -> int:
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 12
    return max(MIN_COMPANIES, min(MAX_COMPANIES, n))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def research_sector(
    sector: str,
    num_companies: int = 12,
    mock: bool = False,
    quiet: bool = False,
) -> SectorResearch:
    """Research a sector into a validated `SectorResearch`.

    * `mock=True` returns free, offline sample data (no key / SDK required).
    * Otherwise runs the live web-search research engine.
    """
    sector = validate_query(sector)
    num_companies = _clamp_num_companies(num_companies)
    printer = _Printer(quiet=quiet)

    if mock:
        printer.info("[bold cyan]Researching[/bold cyan] %s [dim](offline mock mode)[/dim]…" % sector)
        research = _mock_research(sector, num_companies)
        printer.info("[green]✓[/green] Loaded %d sample companies." % len(research.companies))
        return research

    printer.info("[bold cyan]Researching[/bold cyan] %s [dim](live web search)[/dim]…" % sector)
    client = _get_client()

    dossier = _discover_and_research(client, sector, num_companies, printer)
    companies = _extract_structured(client, sector, dossier, num_companies, printer)

    if not companies:
        printer.warn("No verifiable companies were found for this sector.")
    elif len(companies) < num_companies:
        printer.warn(
            "Found %d companies (requested %d) — returning only verified ones, "
            "not padding with invented entries." % (len(companies), num_companies)
        )

    return SectorResearch(sector_name=sector, companies=companies, source="live")


# ---------------------------------------------------------------------------
# Live engine (lazy anthropic import; key stays inside this module)
# ---------------------------------------------------------------------------

def _get_client():
    """Construct the Anthropic client. Key comes from env only; never echoed."""
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv()  # loads .env if present; no-op otherwise
    except Exception:
        pass  # python-dotenv is optional; env vars may already be set.

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your "
            "key, or run in offline mode with --mock. (The key is read only here "
            "and never printed or stored.)"
        )

    try:
        import anthropic  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "The 'anthropic' package is not installed. Run "
            "`pip install -r requirements.txt`, or use --mock for offline mode."
        ) from exc

    # Constructor reads ANTHROPIC_API_KEY from the environment itself.
    return anthropic.Anthropic()


def _web_search_tool() -> dict:
    return {"type": WEB_SEARCH_TOOL_TYPE, "name": "web_search"}


def _run_with_websearch(client, system: str, user: str, max_tokens: int, printer: "_Printer") -> str:
    """Run one web-search-enabled turn, resuming through pause_turn, return text."""
    messages = [{"role": "user", "content": user}]
    text_parts: List[str] = []

    for _ in range(_MAX_CONTINUATIONS):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            tools=[_web_search_tool()],
            messages=messages,
        )
        # Collect any text the model produced this turn.
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(block.text)
            elif getattr(block, "type", None) == "server_tool_use":
                q = ""
                try:
                    q = (block.input or {}).get("query", "")
                except Exception:
                    q = ""
                if q:
                    printer.info("  [dim]› searching:[/dim] %s" % q)

        if resp.stop_reason == "pause_turn":
            # Server hit its web-search iteration cap; resume where it left off.
            messages.append({"role": "assistant", "content": resp.content})
            continue
        break

    return "\n".join(p for p in text_parts if p).strip()


def _discover_and_research(client, sector: str, num_companies: int, printer: "_Printer") -> str:
    """Call 1: web-search the sector into a plain-text research dossier."""
    system = (
        "You are a diligent venture-capital analyst. You research real, currently "
        "active companies using web search and cite sources. You NEVER invent "
        "funding figures, founding dates, or companies. If a fact isn't verifiable, "
        "you say 'unknown' rather than guessing."
    )
    user = (
        "Research the sector: \"%s\".\n\n"
        "Identify %d–%d real, currently active companies competing in this space. "
        "Use web search to verify each one. For every company, gather:\n"
        "- one-line description\n- founding year (if known)\n"
        "- funding stage (pre-seed/seed/series A/B/C/growth/public/unknown)\n"
        "- total disclosed funding (e.g. \"$40M\", or \"undisclosed\")\n"
        "- key differentiator vs. competitors in the same space\n"
        "- target customer\n- which of the OTHER companies in this set are its most "
        "direct competitors or adjacent players\n- source URLs you used.\n\n"
        "Write a concise dossier with one clearly-labelled section per company. "
        "Only include companies you could actually verify — do not pad the list."
        % (sector, max(MIN_COMPANIES, num_companies - 2), num_companies + 2)
    )
    printer.info("  [dim]Discovering companies via web search…[/dim]")
    dossier = _run_with_websearch(client, system, user, max_tokens=6000, printer=printer)
    if not dossier:
        printer.warn("Web search returned no usable text.")
    return dossier


def _extraction_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "companies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "one_line_description": {"type": "string"},
                        "founded_year": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                        "funding_stage": {"type": "string", "enum": list(FUNDING_STAGES)},
                        "total_funding_disclosed": {"type": "string"},
                        "key_differentiator": {"type": "string"},
                        "target_customer": {"type": "string"},
                        "related_companies": {"type": "array", "items": {"type": "string"}},
                        "source_urls": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["name"],
                },
            }
        },
        "required": ["companies"],
    }


def _extract_structured(
    client, sector: str, dossier: str, num_companies: int, printer: "_Printer"
) -> List[Company]:
    """Call 2: turn the dossier into strict JSON, then validate into models."""
    if not dossier:
        return []

    printer.info("  [dim]Extracting structured company data…[/dim]")
    system = (
        "You convert research notes into strict JSON. Output ONLY a JSON object "
        "matching the requested shape — no markdown, no code fences, no preamble. "
        "Copy facts faithfully from the notes; where a fact is missing use null "
        "(founded_year) or the string \"unknown\"/\"undisclosed\". Never invent data."
    )
    schema = _extraction_schema()
    user = (
        "From the research notes below about the \"%s\" sector, produce JSON of the "
        "form {\"companies\": [ ... ]} where each company has exactly these keys: "
        "name, one_line_description, founded_year, funding_stage, "
        "total_funding_disclosed, key_differentiator, target_customer, "
        "related_companies (names of other companies IN this list), source_urls.\n\n"
        "funding_stage must be one of: %s.\n\n"
        "JSON Schema (for shape reference):\n%s\n\n=== RESEARCH NOTES ===\n%s"
        % (sector, ", ".join(FUNDING_STAGES), json.dumps(schema), dossier)
    )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    raw = "".join(
        block.text for block in resp.content if getattr(block, "type", None) == "text"
    )
    data = _parse_json_object(raw)
    if not data:
        printer.warn("Could not parse structured output from the model.")
        return []

    companies = _companies_from_raw(data.get("companies", []), printer)
    # Keep only cross-links that point at companies we actually kept.
    _prune_related(companies)
    return companies


def _parse_json_object(text: str) -> Optional[dict]:
    """Best-effort extraction of a JSON object from model text."""
    if not text:
        return None
    text = text.strip()
    # Strip ```json ... ``` fences if the model added them.
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fall back to the outermost { ... } span.
    start = text.find("{")
    end = text.rfind("}")
    if 0 <= start < end:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _companies_from_raw(raw_list, printer: "_Printer") -> List[Company]:
    companies: List[Company] = []
    seen = set()
    for item in raw_list or []:
        if not isinstance(item, dict):
            continue
        try:
            company = Company(**item)
        except Exception as exc:  # skip malformed entries rather than crash
            printer.warn("Skipping a malformed company entry: %s" % exc)
            continue
        if company.slug in seen:
            continue  # never duplicate on slug
        seen.add(company.slug)
        companies.append(company)
    return companies


def _prune_related(companies: List[Company]) -> None:
    """Drop related_companies that don't resolve to a company in this set."""
    by_slug = {c.slug: c.name for c in companies}
    from .models import slugify

    for c in companies:
        kept = []
        seen = set()
        for rel in c.related_companies:
            rel_slug = slugify(rel)
            if rel_slug == c.slug:
                continue  # no self-links
            if rel_slug in by_slug and rel_slug not in seen:
                kept.append(by_slug[rel_slug])  # normalize to canonical name
                seen.add(rel_slug)
        c.related_companies = kept


# ---------------------------------------------------------------------------
# Landscape summary (also an API call -> lives here per the security rule)
# ---------------------------------------------------------------------------

def generate_landscape_summary(research: SectorResearch, mock: bool = False) -> str:
    """One-paragraph synthesis of the competitive dynamics for the hub note."""
    if mock or research.source == "mock":
        return _mock_landscape_summary(research)

    if not research.companies:
        return "No companies were found for this sector, so no landscape summary is available."

    lines = []
    for c in research.companies:
        lines.append(
            "- %s (%s, %s): %s"
            % (c.name, c.funding_stage, c.total_funding_disclosed, c.key_differentiator or c.one_line_description)
        )
    try:
        client = _get_client()
    except RuntimeError:
        # No key available at summary time — degrade gracefully instead of failing.
        return _mock_landscape_summary(research)

    resp = client.messages.create(
        model=MODEL,
        max_tokens=600,
        system=(
            "You are a VC analyst. Write ONE tight paragraph (4–6 sentences) "
            "synthesizing the competitive dynamics of a sector: who is leading, "
            "how the field is segmented, and where the white space is. No preamble, "
            "no bullet points, no invented facts."
        ),
        messages=[
            {
                "role": "user",
                "content": "Sector: %s\n\nCompanies:\n%s"
                % (research.sector_name, "\n".join(lines)),
            }
        ],
    )
    text = "".join(
        block.text for block in resp.content if getattr(block, "type", None) == "text"
    ).strip()
    return text or _mock_landscape_summary(research)


def _mock_landscape_summary(research: SectorResearch) -> str:
    companies = research.companies
    if not companies:
        return "No companies were found for this sector."
    leaders = [c.name for c in companies if c.funding_stage in ("growth", "public", "series C")]
    early = [c.name for c in companies if c.funding_stage in ("pre-seed", "seed", "series A")]
    lead_txt = ", ".join(leaders[:3]) if leaders else companies[0].name
    early_txt = ", ".join(early[:3]) if early else "a long tail of earlier-stage entrants"
    return (
        "The %s space is anchored by well-funded leaders such as %s, which set the "
        "pace on capability and distribution. A wave of earlier-stage challengers — "
        "including %s — competes on focused differentiation and specific customer "
        "segments. The main axes of competition are product depth, integration into "
        "existing developer and buyer workflows, and go-to-market motion. White space "
        "remains around underserved verticals and workflows the incumbents treat as "
        "secondary. (This summary is generated from sample data — verify before citing.)"
        % (research.sector_name, lead_txt, early_txt)
    )


# ---------------------------------------------------------------------------
# Offline mock engine (free, no key / SDK required)
# ---------------------------------------------------------------------------

def _mock_research(sector: str, num_companies: int) -> SectorResearch:
    from .models import slugify

    curated = _CURATED_MOCK.get(slugify(sector))
    if curated is not None:
        companies = [Company(**c) for c in curated]
    else:
        companies = _generic_mock_companies(sector, num_companies)

    companies = companies[:num_companies]
    _prune_related(companies)
    return SectorResearch(sector_name=sector, companies=companies, source="mock")


def _generic_mock_companies(sector: str, num_companies: int) -> List[Company]:
    """Clearly-labelled placeholder companies for arbitrary sectors in mock mode.

    Intentionally NOT real names/figures — so offline demos are never mistaken
    for researched facts.
    """
    n = _clamp_num_companies(num_companies)
    names = [
        "Northwind", "Vantage", "Lumen", "Keystone", "Cadence", "Beacon",
        "Meridian", "Aperture", "Halcyon", "Praxis", "Sable", "Orbit",
        "Tessera", "Ridgeline", "Solstice", "Fathom", "Verdant", "Quillon",
        "Ampere", "Corvus", "Marlin", "Zephyr", "Onyx", "Lattice", "Cobalt",
    ]
    stages = ["seed", "series A", "series B", "growth", "seed", "series A"]
    companies: List[Company] = []
    for i in range(n):
        base = names[i % len(names)]
        name = "%s (sample)" % base
        companies.append(
            Company(
                name=name,
                one_line_description="Illustrative sample company #%d in the %s space." % (i + 1, sector),
                founded_year=None,
                funding_stage=stages[i % len(stages)],
                total_funding_disclosed="undisclosed",
                key_differentiator="Placeholder differentiator — replace with real research (run without --mock).",
                target_customer="Sample customer segment.",
                related_companies=[],
                source_urls=[],
            )
        )
    # Give each a couple of neighbours so the graph/wikilinks demo has edges.
    for i, c in enumerate(companies):
        neighbours = []
        if i + 1 < len(companies):
            neighbours.append(companies[i + 1].name)
        if i + 2 < len(companies):
            neighbours.append(companies[i + 2].name)
        c.related_companies = neighbours
    return companies


# Curated, publicly-reported snapshot for the demo sector. Figures are
# approximate and illustrative (flagged source="mock"); verify before citing.
_CURATED_MOCK = {
    "ai-coding-assistants": [
        {
            "name": "Cursor",
            "one_line_description": "AI-native code editor (a VS Code fork) built around an agentic pair-programmer.",
            "founded_year": 2022,
            "funding_stage": "growth",
            "total_funding_disclosed": "~$400M+ (reported)",
            "key_differentiator": "Deep, whole-repo AI editing built directly into the IDE rather than bolted on as a plugin.",
            "target_customer": "Professional software engineers and engineering teams.",
            "related_companies": ["GitHub Copilot", "Windsurf", "Zed", "Augment Code"],
            "source_urls": ["https://cursor.com"],
        },
        {
            "name": "GitHub Copilot",
            "one_line_description": "The AI pair-programmer built into GitHub and popular IDEs, from GitHub/Microsoft.",
            "founded_year": 2021,
            "funding_stage": "public",
            "total_funding_disclosed": "undisclosed (Microsoft-owned)",
            "key_differentiator": "Enormous distribution via GitHub and native Microsoft/VS Code integration.",
            "target_customer": "Individual developers through large enterprises.",
            "related_companies": ["Cursor", "Tabnine", "Windsurf", "Sourcegraph"],
            "source_urls": ["https://github.com/features/copilot"],
        },
        {
            "name": "Windsurf",
            "one_line_description": "Agentic AI IDE (formerly Codeium) focused on autonomous multi-file coding flows.",
            "founded_year": 2021,
            "funding_stage": "growth",
            "total_funding_disclosed": "~$243M (reported)",
            "key_differentiator": "Agent-first 'flows' that plan and execute across a codebase, plus an enterprise self-host story.",
            "target_customer": "Individual developers and security-conscious enterprises.",
            "related_companies": ["Cursor", "GitHub Copilot", "Tabnine"],
            "source_urls": ["https://windsurf.com"],
        },
        {
            "name": "Tabnine",
            "one_line_description": "Enterprise AI code assistant emphasizing privacy and self-hosting.",
            "founded_year": 2018,
            "funding_stage": "series B",
            "total_funding_disclosed": "~$55M (reported)",
            "key_differentiator": "Privacy-first / air-gapped deployments and control over which models and data are used.",
            "target_customer": "Enterprises with strict data-governance requirements.",
            "related_companies": ["GitHub Copilot", "Windsurf", "Sourcegraph"],
            "source_urls": ["https://www.tabnine.com"],
        },
        {
            "name": "Replit",
            "one_line_description": "Browser-based dev environment with an AI Agent that builds and deploys apps.",
            "founded_year": 2016,
            "funding_stage": "series B",
            "total_funding_disclosed": "~$220M (reported)",
            "key_differentiator": "Zero-setup cloud IDE + agent that goes from prompt to deployed app in one place.",
            "target_customer": "Learners, hobbyists, and prototyping teams.",
            "related_companies": ["Cursor", "GitHub Copilot", "Cognition (Devin)"],
            "source_urls": ["https://replit.com"],
        },
        {
            "name": "Sourcegraph",
            "one_line_description": "Code intelligence platform whose Cody assistant reasons over large codebases.",
            "founded_year": 2013,
            "funding_stage": "growth",
            "total_funding_disclosed": "~$225M (reported)",
            "key_differentiator": "Deep code search / graph over huge monorepos powering more grounded AI answers.",
            "target_customer": "Large engineering organizations with big codebases.",
            "related_companies": ["GitHub Copilot", "Tabnine", "Augment Code"],
            "source_urls": ["https://sourcegraph.com"],
        },
        {
            "name": "Augment Code",
            "one_line_description": "Enterprise AI coding assistant tuned for large, complex codebases.",
            "founded_year": 2022,
            "funding_stage": "series B",
            "total_funding_disclosed": "~$252M (reported)",
            "key_differentiator": "Context engine optimized for very large repos and team-scale knowledge.",
            "target_customer": "Enterprise engineering teams.",
            "related_companies": ["Cursor", "Sourcegraph", "GitHub Copilot"],
            "source_urls": ["https://www.augmentcode.com"],
        },
        {
            "name": "Cognition (Devin)",
            "one_line_description": "Maker of Devin, an autonomous AI software engineer that completes tasks end-to-end.",
            "founded_year": 2023,
            "funding_stage": "growth",
            "total_funding_disclosed": "~$196M+ (reported)",
            "key_differentiator": "Fully autonomous agent framed as a teammate that owns tickets, not just autocomplete.",
            "target_customer": "Engineering teams delegating whole tasks.",
            "related_companies": ["Cursor", "Replit", "GitHub Copilot"],
            "source_urls": ["https://cognition.ai"],
        },
        {
            "name": "Zed",
            "one_line_description": "High-performance, collaborative code editor with built-in AI, from ex-Atom authors.",
            "founded_year": 2021,
            "funding_stage": "seed",
            "total_funding_disclosed": "unknown",
            "key_differentiator": "Native, GPU-accelerated speed and real-time collaboration with AI woven in.",
            "target_customer": "Performance-conscious professional developers.",
            "related_companies": ["Cursor", "GitHub Copilot"],
            "source_urls": ["https://zed.dev"],
        },
        {
            "name": "Continue",
            "one_line_description": "Open-source AI code assistant you can point at any model, for VS Code and JetBrains.",
            "founded_year": 2023,
            "funding_stage": "seed",
            "total_funding_disclosed": "undisclosed",
            "key_differentiator": "Fully open-source and model-agnostic — bring your own model and customize deeply.",
            "target_customer": "Developers and teams wanting open, self-controlled tooling.",
            "related_companies": ["Cursor", "Tabnine", "Zed"],
            "source_urls": ["https://www.continue.dev"],
        },
    ]
}
