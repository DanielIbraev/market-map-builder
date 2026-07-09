---
type: sector-map
sector: AI coding assistants
researched_at: 2026-07-09 15:49 UTC
company_count: 10
tags: [sector-map, ai-coding-assistants]
---

# AI coding assistants — Market Map

_10 companies · researched 2026-07-09 · source: mock_

> ⚠️ **Sample data** (offline mock mode) — illustrative only, verify before citing.

## Companies

| Company | Stage | Founded | Last round | One-liner | Verified |
| --- | --- | --- | --- | --- | --- |
| [[cursor|Cursor]] | growth | 2022 | Series B · ~$105M · 2025-01 (illustrative) | AI-native code editor (a VS Code fork) built around an agentic pair-programmer. | 2026-07-09 |
| [[github-copilot|GitHub Copilot]] | public | 2021 | n/a (Microsoft product line) | The AI pair-programmer built into GitHub and popular IDEs, from GitHub/Microsoft. | 2026-07-09 |
| [[windsurf|Windsurf]] | growth | 2021 | Series C · ~$150M · 2024-08 (illustrative) | Agentic AI IDE (formerly Codeium) focused on autonomous multi-file coding flows. | 2026-07-09 |
| [[tabnine|Tabnine]] | series B | 2018 | Series B · ~$25M · 2023-11 (illustrative) | Enterprise AI code assistant emphasizing privacy and self-hosting. | 2026-07-09 |
| [[replit|Replit]] | series B | 2016 | Series B ext. · ~$97M · 2023-04 (illustrative) | Browser-based dev environment with an AI Agent that builds and deploys apps. | 2026-07-09 |
| [[sourcegraph|Sourcegraph]] | growth | 2013 | Series D · ~$125M · 2021-07 (illustrative) | Code intelligence platform whose Cody assistant reasons over large codebases. | 2026-07-09 |
| [[augment-code|Augment Code]] | series B | 2022 | Series B · ~$227M · 2024-04 (illustrative) | Enterprise AI coding assistant tuned for large, complex codebases. | 2026-07-09 |
| [[cognition-devin|Cognition (Devin)]] | growth | 2023 | Series B · ~$175M · 2024-04 (illustrative) | Maker of Devin, an autonomous AI software engineer that completes tasks end-to-end. | 2026-07-09 |
| [[zed|Zed]] | seed | 2021 | — | High-performance, collaborative code editor with built-in AI, from ex-Atom authors. | 2026-07-09 |
| [[continue|Continue]] | seed | 2023 | Seed · undisclosed · 2023 (illustrative) | Open-source AI code assistant you can point at any model, for VS Code and JetBrains. | 2026-07-09 |

## Landscape summary

The AI coding assistants space is anchored by well-funded leaders such as Cursor, GitHub Copilot, Windsurf, which set the pace on capability and distribution. A wave of earlier-stage challengers — including Zed, Continue — competes on focused differentiation and specific customer segments. The main axes of competition are product depth, integration into existing developer and buyer workflows, and go-to-market motion. White space remains around underserved verticals and workflows the incumbents treat as secondary. (This summary is generated from sample data — verify before citing.)

## Relationship graph

```mermaid
graph TD
  cursor["Cursor"]
  github_copilot["GitHub Copilot"]
  windsurf["Windsurf"]
  tabnine["Tabnine"]
  replit["Replit"]
  sourcegraph["Sourcegraph"]
  augment_code["Augment Code"]
  cognition_devin["Cognition (Devin)"]
  zed["Zed"]
  continue["Continue"]
  cursor --> github_copilot
  cursor --> windsurf
  cursor --> zed
  cursor --> augment_code
  github_copilot --> cursor
  github_copilot --> tabnine
  github_copilot --> windsurf
  github_copilot --> sourcegraph
  windsurf --> cursor
  windsurf --> github_copilot
  windsurf --> tabnine
  tabnine --> github_copilot
  tabnine --> windsurf
  tabnine --> sourcegraph
  replit --> cursor
  replit --> github_copilot
  replit --> cognition_devin
  sourcegraph --> github_copilot
  sourcegraph --> tabnine
  sourcegraph --> augment_code
  augment_code --> cursor
  augment_code --> sourcegraph
  augment_code --> github_copilot
  cognition_devin --> cursor
  cognition_devin --> replit
  cognition_devin --> github_copilot
  zed --> cursor
  zed --> github_copilot
  continue --> cursor
  continue --> tabnine
  continue --> zed
```
