---
id: 23
slug: local-visual-editor
status: done
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

## Measured delivery

`graphunslopify preview --open` serves packaged offline HTML/CSS/JS over loopback. The existing
compiler emits strict render jobs in isolated owned folders. Uploaded files bind the data/lock
paths; plain portable stems, Host/Origin/session checks, whitelisted exports and explicit dataset
ZIP consent constrain the filesystem boundary. One bounded worker renders at a time. Input edits
invalidate old evidence, current generation checks skip obsolete queued work, and the browser
ignores delayed older responses. Only currently offered verifier patches can be selected.

Real Chrome exercises a file picker, JSON editing, schema/semantic failures, an offered temporal-y
fix, false claims, mixed score/loss verdicts in two panels, manual/live rendering, and delayed older
responses. An empty-data filter probe caught failure status being overwritten by missing-export
status; failures now retain precedence and a no-output run cannot enable the figure bundle. ZIPs
with/without input data are inspected; extracted Python reproduces outside the checkout with
matching spec/data hashes and verified PNG/SVG/PDF digests and provenance. Desktop/mobile and
failure screenshots were visually inspected; browser external requests and JavaScript errors = 0.

Seven local gates pass: 215 Node (zero skips), 140 Python, 15 matching baselines, 16 renders,
25 recipes and seven composition cases. Ruff passes. A newly built wheel launches the HTTP UI,
serves its packaged assets and renders the 24-row/n=4 sample after fresh installation with external
connections blocked, including optional agent checks. CI runs the real browser test and retains
screenshots/ZIP evidence; all four distribution environments also run the installed editor smoke.
Broader independent numeric validation and versioned public release remain separate roadmap work.
