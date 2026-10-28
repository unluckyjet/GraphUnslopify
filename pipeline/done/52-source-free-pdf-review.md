---
id: 52
slug: source-free-pdf-review
status: done
priority: P1
title: Prepare honest local visual review packets for ordinary manuscript PDFs
source_idea: user 2026-10-28 adoption review item3
---

# Ordinary PDF review preparation

Add optional[pdf] renderer and audit-pdf CLI. Render explicitly selected/all supported
pages, recover text without OCR, and crop manual normalized selections. Preserve
source bytes, old outputs and evidence hashes. Produce offline HTML plus JSON with
renderer/resolution/source/page/text/crop identity and availability. Recognized
embedded provenance never becomes authentication or a scientific pass.

Default exit2/status incomplete even when extraction succeeds: source data,
numerical claims and human interpretation remain untested. Explicit --prepare-only
allows exit0 for successful preparation only, preserving incomplete status. Invalid
PDFs/selections/dependencies/errors remain nonzero. No arbitrary chart/data inference
or automatic figure detection is claimed. Original programs/URLs are not executed.

Measure actual14-page Gorman2014 manuscript, selected page8/Figure3 with axes,
legend/panels/caption retained; SHA256/selection/docs identify exact source. Exercise
source unchanged, actual pixel crop equality, unavailable text, metadata limits,
malformed PDF, missing optional renderer, domain/path/duplicate protections and
separate preparation/verification exits. Full seven gates and independent audit
required; exact-push CI must be green before advancing. Published0.7.0 remains
unchanged and does not claim the new command.

Measured:30 focused controls,217 Node/1042 Python, all seven gates/Ruff60 pass.
Real page8/Figure3 crops were visually checked, pixel hashes/bounds verified, and
HTML packet at1280/390 loads images with no horizontal overflow. First audit
found case-insensitive filename collisions (Figure/figure) overwriting evidence;
fixed via casefold uniqueness before output creation and a portable regression.
Second audit passes focused controls plus exact real-source/artifact/crop identity
and both policies. No remaining findings. Exact-push CI checked after push.
