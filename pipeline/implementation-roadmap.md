# Implementation roadmap from the external review

User-authorized scope (2026-10-25): implement the accepted review recommendations in this GitHub repository, push each small milestone, check CI, then explain the completed capabilities in one child-friendly paragraph. Keep the entire scope active until verified.

## Delivery requirements and evidence

- [ ] Statistical integrity: singleton intervals, independent repeat handling, table intervals/winner wording, corrected multiple comparisons, numeric reference fixtures, row/sample accounting, explicit failed/untested claim policy.
- [ ] Trustworthy figures: complete accessible descriptions/metadata, composition validation and panel checks, embedded PDF fonts, clean example gallery, supported export parity or explicit refusals.
- [ ] Distribution: declared license, short quickstart, versioned documentation, clean-install end-to-end test, packaged local translator and clear offline workflow, tagged GitHub releases and installable release artifacts.
- [x] Researcher CI: reusable GitHub workflow/action; regenerate from results; publish machine-readable audit/figure-change reports and reviewable artifacts; meaningful exit status on failures.
- [ ] Integrations: working notebook example and agent setup, easy local configuration, broad Python-kind support; supported editor workflow documented and exercised.
- [x] Paper/batch auditing: manifest connecting specs/scripts/data/claims, directory execution, report aggregation, stable figure comparison including claim changes and data hashes. Clearly distinguish supported artifact types from arbitrary image interpretation.
- [ ] Visual workflow: working live preview, editable spec, visible diagnostics, selected justified fixes, usable export. Exercise the UI and local preview end to end.
- [ ] Independent benchmark/reference validation: known-answer datasets and documented limits, beyond source substring assertions or file-existence checks.
- [ ] Naming: rename GitHub repository to GraphUnslopify if available and update repository/dependency/documentation links while preserving existing local checkout and vault identity.
- [ ] Final audit: verify each feature against actual code/runtime/artifacts/GitHub state, update Obsidian, and deliver the requested child-friendly paragraph.

## Milestones

Each completed milestone records its commit and CI result here or in the log. Existing audited specs 04–09 remain contracts, adjusted only where the review identified unsupported inference (overlapping intervals must not be labeled equivalent).

1. Preserve missing intervals across all uncertainty kinds.
2. Implement table uncertainty with honest, uncertainty-aware highlighting (spec 04).
3. Correct significance procedures and test numeric reference answers (spec 05).
4. Account for observations and repeats (spec 08).
5. Export accurate descriptions, composition behavior, fonts, and readable gallery (specs 06/07/09).
6. Add structured runtime reports and strict failure policies for scripts/CLI/Python.
7. Package/install/document the local workflow and license it.
8. Build batch auditing and figure/claim comparison with reference fixtures.
9. Ship reusable Figure CI and notebook/agent/editor integrations.
10. Build and verify live preview/editor and selected repairs.
11. Rename/release, verify all delivery requirements, and explain.

Milestones may be split further as evidence requires. No checklist item is complete merely because a scaffold or plan exists. Publishing to third-party package registries depends on available account authorization; GitHub release artifacts must still be installable and tested.

## Progress

- Milestone 1 pushed as `fac46c0`: singleton intervals fixed; all seven local gates passed. CI run `40210764967` passed all three jobs before milestone 2.

- Milestone 2 pushed as `a9eb61b`; CI `40211285965` passed. Table intervals/highlighting and rendered text-fit checks are complete.
- Split significance work: fix the measured raw permutation defect (spec 11) before spec 05 adjusts multiple p-values.

- Milestone 3 pushed as `99dbfe7`; CI `40211644705` passed. Raw significance now matches exact reference tails.
- Milestone 4 implements audited spec 05 (Holm/BH); observation accounting and runtime strict reports remain next in the reliability workstream.
- Milestone 4 pushed as `e6ec579`; CI `40212145827` passed. Milestone 5 adds composition disclosures (spec 06).
- Milestone 5 pushed as `fcd1cd7`; CI `40212463417` passed. Milestone 6 fixes the broken-axis range-check false positive (spec 07).
- Milestone 6 pushed as `fa686e6`; CI `40212757914` passed. Milestone 7 implements row/sample accounting (spec 08), repairs empty description metadata, and corrects the mislabeled single-run fixture.
- Milestone 7 pushed as `61179c7`; CI `40213912302` passed. Milestone 8 implements embedded TrueType PDF/PostScript settings and a live regression guard (spec 09).
- Milestone 8 pushed as `d775c65`; CI `40214384355` passed. Milestone 9 implements declared repeat units (spec 12); the next workstream is structured runtime/claim failure reporting.
- Milestone 9 pushed as `80c1aab`; CI `40215286630` passed. Milestone 10 adds structured runtime evidence and strict policy (spec 13). Known gallery defects are now machine-detectable; metadata/composition fidelity and presentation cleanup remain next.
- Milestone 10 pushed as `6f469c4`; CI `40217126282` passed. Milestone 11 cleans both known gallery defects and adds a strict gallery/artifact gate (spec 14). Metadata/composition fidelity, distribution, audit/CI workflows, integrations, editor, benchmarks and release remain active.
- Milestone 11 pushed as `a65fe3a`; CI `40218258195` passed. Milestone 12 adds complete recoverable provenance and deterministic accessible exports (spec 15). Composition/export semantics remain before distribution, batch/CI, integrations, editor, reference validation and release.
- Milestone 12 pushed as `121ba01`; CI `40219769007` passed. Milestone 13 implements nested grids, repeat sharing, wide-derived series and explicit composition contracts (spec 16). Interactive export parity and accurate derived descriptions remain before distribution/audit/CI/editor/release.
- Milestone 13 pushed as `ebeafcf`; CI `40221824538` passed. Milestone 14 fixes supported HTML numerical parity, descriptions, weighted confusion counts and singleton visibility (spec 17). Next priority is licensed one-command local distribution, then audit/CI/integrations/editor/reference validation/release; keep the full scope active.

- Milestone 14 pushed as `dcf896e`; CI `40226605900` passed. Milestone 15 packages/licenses the local emitter and runtime, adds offline installation and actual wheel smoke checks (spec 18). Batch audit, reusable CI, integrations, editor, reference validation, naming and release remain active.

- Milestone 15 pushed as `69d79ec`; CI `40229061855` passed all seven jobs, including clean Linux 3.10/3.12, macOS and Windows installs. Milestone 16 adds manifest-driven paper audits, artifact/data verification, stable comparisons and reference cases (spec 19). Reusable researcher CI is next; integrations/editor, broader numeric validation, naming and release remain active.

- Milestone 16 pushed as `bddf5f8`; CI `40231304112` passed all seven jobs. Milestone 17 packages a reusable Figure CI composite action with real consumer/negative-control integration and scoped evidence staging (spec 20). Notebook/agent/editor integrations, broader references, naming/versioned release and final audit remain active.

- Milestone 17 pushed as `49e1d3e`; general CI `40232270424` and real Figure CI integration `40232270444` passed. Both downloaded bundles preserve correct verdicts/artifacts and exclude CSVs; actual comparison separates changed claims/metadata from unchanged data/pixels. Milestone 18 expands all Python kinds and adds an executable packaged notebook (spec 21). Agent and live editor integrations, broader numerical references, naming and release remain active.

- Milestone 18 pushed as `35bd79e`; general CI `40233714277` passed eight jobs including full notebook/kernel suites on Python 3.10/3.12; Figure CI baseline integration `40233714295` passed. Milestone 19 adds the local stdio agent bridge and configuration output (spec 22). Visual editor, broader references, naming/versioned release and completion audit remain active.
