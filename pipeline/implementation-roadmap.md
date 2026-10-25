# Implementation roadmap from the external review

User-authorized scope (2026-10-25): implement the accepted review recommendations in this GitHub repository, push each small milestone, check CI, then explain the completed capabilities in one child-friendly paragraph. Keep the entire scope active until verified.

## Delivery requirements and evidence

- [ ] Statistical integrity: singleton intervals, independent repeat handling, table intervals/winner wording, corrected multiple comparisons, numeric reference fixtures, row/sample accounting, explicit failed/untested claim policy.
- [ ] Trustworthy figures: complete accessible descriptions/metadata, composition validation and panel checks, embedded PDF fonts, clean example gallery, supported export parity or explicit refusals.
- [ ] Distribution: declared license, short quickstart, versioned documentation, clean-install end-to-end test, packaged local translator and clear offline workflow, tagged GitHub releases and installable release artifacts.
- [ ] Researcher CI: reusable GitHub workflow/action; regenerate from results; publish machine-readable audit/figure-change reports and reviewable artifacts; meaningful exit status on failures.
- [ ] Integrations: working notebook example and agent setup, easy local configuration, broad Python-kind support; supported editor workflow documented and exercised.
- [ ] Paper/batch auditing: manifest connecting specs/scripts/data/claims, directory execution, report aggregation, stable figure comparison including claim changes and data hashes. Clearly distinguish supported artifact types from arbitrary image interpretation.
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
