---
id: 90
slug: journal-compliance
status: in_progress
priority: P1
title: Inspect exported figures against sourced journal requirements
source_idea: 2026-11-02 research-platform idea5 and top-ranked journal compliance profiles
---

# 90 — Journal compliance

Full initiative: [all thirty requirements](../research-platform-roadmap.md).
Existing style.venue and publication presets are not a compliance checker.

## Acceptance

1. Versioned official-source profiles identify journal,submission stage,checked
   UTC date and freshness. Distinguish requirements from recommendations and
   manual/unavailable checks. Never imply a snapshot is a live policy lookup.
2. Inspect the submitted bytes,not nominal canvas intent: actual raster metadata,
   physical PDF dimensions/pages,declared supported vector metadata,formats,
   density,file size and supported text evidence. Wrong/missing/corrupt evidence
   cannot pass. Never execute EPS,authored programs or remote files to inspect.
3. CLI/API reports bind source bytes and profile rules,retain each check and
   distinguish technical acceptance from unverified science/full submission
   readiness. Requested target dimensions must be checked against the actual file.
4. Public figure/paper workspaces select profiles,show findings/source/freshness,
   retain stale/current-result fences and offer explicit reviewed corrections
   where supported. Supported text legibility and manual review gaps are visible.
5. Real artifact/refusal/boundary/freshness controls,current/minimum/fresh installs,
   actual public browser paths and exact-source CI prove the final scope.
   Preserve benchmark originals/defaults and update docs/shared knowledge.

## Coherent publishing checkpoints

- 90a: sourced technical checker/API/CLI with real file and refusal evidence.
- 90b: editor/project selection,current evidence and complete supported findings.
- Follow-on exact-size export only as a separately tested public behavior.

No milestone is complete merely because profiles can be listed. Keep incomplete
scope explicit and push each verified behavior before advancing.


##90a — technical foundation under verification

Adds journal.py and journal-profiles/journal-check commands with official-source
Nature/PLOS stage/date/rule snapshots. Reads actual raster/PDF/SVG metadata and
nonexecuted EPS headers; explicit author width,missing evidence,changed source,
invalid formats and stale profiles retain rejection/incompleteness. Technical
pass never grants scientific/submission certification; text/content/white-space
review remains explicit. No generator default or old benchmark byte changes.

27 real-file/refusal tests pass current3.12 (34 with existing CLI/diagnostic
regressions) and minimum3.10. Fresh private0.8 wheel517105bytes/SHA
ebe6f3ef71f92a47084d940c8cc37de13fe1ff62626264f2f4f082dfdcd7c8c3
installs outside checkout with27 pinned dependencies; all78 SDK/resource files
match source. Actual API/CLI PDF and TIFF positives plus low-DPI refusal pass,
with external connections blocked and no registry publication. Full required
checks/push/exact14 remain before advancing.90b/full90 remain unfinished.
