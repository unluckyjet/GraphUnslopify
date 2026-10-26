# Implementation roadmap from the external review

User-authorized scope (2026-10-25): implement the accepted review recommendations in this GitHub repository, push each small milestone, check CI, then explain the completed capabilities in one child-friendly paragraph. Keep the entire scope active until verified.

## Delivery requirements and evidence

- [ ] Statistical integrity: singleton intervals, independent repeat handling, table intervals/winner wording, corrected multiple comparisons, numeric reference fixtures, row/sample accounting, explicit failed/untested claim policy.
- [ ] Trustworthy figures: complete accessible descriptions/metadata, composition validation and panel checks, embedded PDF fonts, clean example gallery, supported export parity or explicit refusals.
- [ ] Distribution: declared license, short quickstart, versioned documentation, clean-install end-to-end test, packaged local translator and clear offline workflow, tagged GitHub releases and installable release artifacts.
- [x] Researcher CI: reusable GitHub workflow/action; regenerate from results; publish machine-readable audit/figure-change reports and reviewable artifacts; meaningful exit status on failures.
- [x] Integrations: working notebook example and agent setup, easy local configuration, broad Python-kind support; supported editor workflow documented and exercised.
- [x] Paper/batch auditing: manifest connecting specs/scripts/data/claims, directory execution, report aggregation, stable figure comparison including claim changes and data hashes. Clearly distinguish supported artifact types from arbitrary image interpretation.
- [x] Visual workflow: working live preview, editable spec, visible diagnostics, selected justified fixes, usable export. Exercise the UI and local preview end to end.
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

- Milestone 19 pushed as `21f65e9`; general CI `40235604441` passed eight jobs and Figure CI `40235604402` passed. Milestone 20 adds the installed offline local editor, selected fixes, bounded/stale-safe previews, scoped ZIP exports and real browser/install verification (spec 23). Local gates pass: 215 Node/140 Python. Broader references, naming/versioned release and final completion audit remain active.

- Milestone 20 pushed as `9bbf195`; general CI `40238265672` passed eight jobs and Figure CI `40238265907` passed. Downloaded browser evidence verifies all 13 workflows and actual ZIP/provenance outputs. Milestone 21 fixes confirmed literal-text LaTeX and unknown-origin disclosure defects (spec 25), split from the still-open scientific reference matrix (24). Local gates pass: 215 Node/144 Python, strict gallery 15/15, unchanged gallery pixels and real TeX/PDF round-trip.

- Milestone 21 pushed as `be3649d`; general CI `40240094593` passed eight jobs and Figure CI `40240094542` passed. Downloaded Linux TeX proof preserves the literal characters/numbers. Milestone 22 fixes the independent Kaplan–Meier tie/risk-set defect and related domain/tail/description/derived-claim behavior (spec 26). All seven local gates pass (215 Node/178 Python), strict gallery 15/15 and fresh offline wheel survival render; the complete scientific matrix 24 remains open.


- Milestone 22 pushed as bca31c0; general CI 40243611958 passed eight jobs and Figure CI
  40243611899 passed. Milestone 23 completes calibration's input/binning/error/description/claim
  contract (spec 27), including actual per-panel ECE legends and derived direct labels. Local
  seven gates pass (215 Node/209 Python), strict gallery 15/15, independent hand/scikit-learn
  points and installed offline wheel. Scientific reference matrix 24, naming/versioned release
  and final completion audit remain open.


- Milestone 23 pushed as 6626fb3; general CI 40246520360 passed eight jobs and Figure CI
  40246520307 passed. Milestone 24 completes matched-unit differences and pair-specific
  accounting/descriptions/interval evidence (spec 28): 39 hand/SciPy/artist/runtime cases,
  215 Node/248 Python, all seven local gates, strict gallery 15/15, four visually inspected
  context cases and installed offline wheel. Matrix 24 still needs QQ/scaling, global
  identifiers/overlays and final exported-width/table context, plus naming/versioned release.


- Milestone 24 pushed as 6ca5e26; general CI 40247862553 passed eight jobs and Figure CI
  40247862602 passed. Milestone 25 completes accurate normal/uniform Q-Q quantities and
  population-quartile references (spec 29): 48 hand/SciPy/artist/runtime/provenance cases,
  215 Node/296 Python, all seven local gates, strict gallery 15/15, visually inspected
  variants and refreshed published illustration with committed inputs, plus installed offline
  wheel. The complete 21-kind scientific matrix, identifiers/overlays/export width, naming,
  versioned release and final completion audit remain open.


- Milestone 25 pushed as 87782be; general CI 40250499570 passed eight jobs and Figure CI
  40250499522 passed. Milestone 26 completes validated scaling fits and conditional/point-only
  uncertainty (spec 30): 51 scaling references plus two minor-tick inspector controls, 215 Node/
  349 Python, all seven local gates, strict gallery 15/15, four visually inspected figures and
  fresh offline wheel without optional SciPy. Published inputs and source/data fingerprint
  coverage are committed. The complete 21-kind matrix, CSV identifiers/overlays/final export
  width, naming/versioned release and final audit remain open.

- Scaling compatibility follow-up: b532a6e's Figure CI 40254352440 passed, while general
  40254352436 exposed genuine older-Matplotlib narrow-log labels on Python3.10. Compact
  major ticks with a shared exponent preserve plotted values/log geometry, with four new
  numeric display references. All seven local gates pass again (215 Node/353 Python),
  strict gallery15/15, eight targeted Python3.10/Matplotlib3.10.9 cases and fresh offline
  Python3.12 wheel. The complete roadmap and ready identifier contract31 remain open.
