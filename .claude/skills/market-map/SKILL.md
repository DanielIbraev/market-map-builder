---
name: market-map
description: >-
  Research a startup/tech sector or company and generate an interlinked Obsidian
  vault of the competitive landscape. Use when the user says things like "map the
  market for X", "build a competitive landscape for X", "research the X space",
  "who are the competitors in X", or "make a market map / sector map of X". Runs
  the Market Map Builder CLI (python -m src.main map "<sector>").
---

# Market Map

Build an Obsidian market map for a sector: one linked note per company plus a hub
note with a summary table, a Claude-written landscape summary, and a Mermaid
relationship graph. The tool uses Claude's web search as the research engine and
writes plain markdown — no Obsidian plugins required.

## When to trigger

Any request to map / research a competitive landscape, e.g.:
- "Map the market for AI code review tools"
- "Build a competitive landscape for vector databases"
- "Research the observability startup space"
- "Who are the main players in AI voice agents? Make a vault."

## How to run it

From the project root:

```bash
# Live research (needs ANTHROPIC_API_KEY in .env — see README):
python -m src.main map "<sector>"

# Options:
python -m src.main map "<sector>" --num-companies 15
python -m src.main map "<sector>" --vault-path ./my-vault

# Free offline sample data (no key, no cost — good for a quick demo):
python -m src.main map "<sector>" --mock

# Update an existing map (diffs + appends a changelog to changed notes):
python -m src.main refresh "<sector>"
```

Steps for the assistant:
1. Extract the `<sector>` (or company) from the user's request. Keep it short
   (a few words); the CLI validates and rejects overly long or unusual input.
2. Run the `map` command above. If `ANTHROPIC_API_KEY` is not configured, either
   set it up (see the repo README) or run with `--mock` for offline sample data
   and tell the user it is sample data.
3. Report the hub-note path from the command's summary and tell the user they can
   open the vault folder in Obsidian to see the graph.

## Notes

- Default output directory is `./vault/<sector-slug>/`.
- The tool never fabricates funding figures or dates — unverifiable fields are
  left as "unknown"/"undisclosed".
- The API key is read only inside `src/research.py` and is never printed, logged,
  or written into the vault.
