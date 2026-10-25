# Log

One line per state change, newest last.

2026-09-02 scaffolding built; queue tool verified; research agent started
2026-09-02 20:44 cycle 1: research delivered 8 ideas to inbox; audit running; queue still empty so nothing built
2026-09-02 20:53 cycle 2: audit still running over 9 ideas; no specs yet; nothing built
2026-09-02 21:0x cycle 3: fire landed mid-audit on spec 01; stopped without writing, per the gap now closed in cycle.md
2026-09-02 21:13 cycle 4: spec 01 PASSED audit and shipped as af9fa5e; 3 follow-ups to inbox; next is 02
2026-09-02 21:1x cycles 5-6: skipped, spec 02 audit in flight
2026-09-02 21:38 cycle 7: spec 02 NEEDS_REWORK, disclosure line prints twice; code diff left in place for the rework; 2 ideas filed
2026-09-02 22:01 cycle 9: spec 02 NEEDS_REWORK round 2, draw_with_break and add_inset double-count the accumulator; diff kept for rework
2026-09-02 22:21 cycle 11: spec 02 NEEDS_REWORK round 3, repeat panels share one frame so id() keying undercounts by half; 2 ideas filed
2026-09-02 22:47 cycle 13: spec 02 SHIPPED as d10506c after 4 rounds; audit loop retired as the bottleneck; runbook now fixes on verdict and caps audits at 2
2026-09-02 22:55 spec 03 shipped: claims disclose interval overlap; alt text carries the caveat
2026-10-25 — 10 shipped: all uncertainty kinds preserve absent singleton bounds; seven local checks passed (149 Node / 60 Python).
2026-10-25 — 04 shipped: table intervals reuse the summarizer; honest separation/overlap highlighting; readable cells; seven local gates passed (156 Node / 60 Python).
2026-10-25 — 11 shipped: independent significance permutations and exact small-sample tails; seven local gates passed (161 Node / 60 Python).
2026-10-25 — 05 shipped: default Holm and optional BH/none with reference numeric tests, raw/adjusted reporting, and opt-out warning; seven local gates passed (164 Node / 70 Python).
2026-10-25 — 06 shipped: descriptions disclose breaks, insets, labeled layers, and metric panels; real-render disclosure assertions; seven gates passed (169 Node / 70 Python).
2026-10-25 — 07 shipped: broken-axis halves excluded only from range comparison; real false positives reduced 1 to 0; seven gates passed (169 Node / 74 Python).
2026-10-25 — 08 shipped: row/finite/sample accounting, skipped-pair reasons, embedded descriptions, and true single-run example; seven gates passed (176 Node / 74 Python).
2026-10-25 — 09 shipped: embedded TrueType fonts; 14 PDFs verified; negative guard rejected all 16 Type 3 cases; seven gates passed (176 Node / 74 Python).
2026-10-25 — 12 shipped: one summary per declared repeat unit, finite statistics, shared significance inputs, and unit-count disclosure; seven gates passed (186 Node / 74 Python).
2026-10-25 — 13 shipped: versioned runtime reports, strict failure policies, per-panel claims, CLI/builder propagation, and public JSON schema; seven gates passed (203 Node / 77 Python).
2026-10-25 — 14 shipped: scatter legend outside data, measured categorical tick layout, strict gallery CI/artifacts; negative control 13/15 → 15/15; 204 Node / 77 Python tests pass.
