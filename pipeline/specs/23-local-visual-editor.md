---
id: 23
slug: local-visual-editor
status: ready
priority: P1
title: Local live preview editable specs diagnostics fixes and exports
source_idea: accepted visual workflow and supported editor integration roadmap
---

# Local visual editor

Deliver a usable browser editor launched by the installed Python CLI. Keep the canonical compiler
and renderer as owners; do not introduce another chart implementation. Work with local uploads,
all canonical kinds through editable JSON/recipes, visible diagnostics and per-panel claim results,
selected fixes actually offered by the verifier, and useful figure/source/spec/report export.

## Acceptance evidence

- A packaged offline UI and local CLI/server run without a hosted translator or CDN.
- User can choose data, edit intent, see a current preview and readable diagnostics, apply a
  selected justified patch and export artifacts. Invalid/stale requests cannot masquerade as a
  successful current preview. Static errors block generation; failed runtime claims remain visible.
- Local HTTP/file boundaries constrain requests to intentionally supplied data and owned outputs.
  Dataset files are not included in downloads without an explicit selection. Downloaded spec and
  source have usable relative data paths; reports/provenance agree with the generated artifacts.
- Real browser tests exercise data selection, spec editing, findings, fix, preview and export.
  Inspect screenshots, actual artifact contents and failure cases; documentation states the
  supported workflow. Run existing gates and check both repository CI workflows after pushing.
