# Implementation roadmap from the external review

User-authorized scope (2026-10-25): implement the accepted review recommendations in this GitHub repository, push each small milestone, check CI, then explain the completed capabilities in one child-friendly paragraph. Keep the entire scope active until verified.

## Delivery requirements and evidence

- [x] Statistical integrity: singleton intervals, independent repeat handling, table intervals/winner wording, corrected multiple comparisons, numeric reference fixtures, row/sample accounting, explicit failed/untested claim policy.
- [x] Trustworthy figures: complete accessible descriptions/metadata, composition validation and panel checks, embedded PDF fonts, clean example gallery, supported export parity or explicit refusals.
- [x] Distribution: declared license, short quickstart, versioned documentation, clean-install end-to-end test, packaged local translator and clear offline workflow, tagged GitHub releases and installable release artifacts.
- [x] Researcher CI: reusable GitHub workflow/action; regenerate from results; publish machine-readable audit/figure-change reports and reviewable artifacts; meaningful exit status on failures.
- [x] Integrations: working notebook example and agent setup, easy local configuration, broad Python-kind support; supported editor workflow documented and exercised.
- [x] Paper/batch auditing: manifest connecting specs/scripts/data/claims, directory execution, report aggregation, stable figure comparison including claim changes and data hashes. Clearly distinguish supported artifact types from arbitrary image interpretation.
- [x] Visual workflow: working live preview, editable spec, visible diagnostics, selected justified fixes, usable export. Exercise the UI and local preview end to end.
- [x] Independent benchmark/reference validation: known-answer datasets and documented limits, beyond source substring assertions or file-existence checks.
- [x] Naming: rename GitHub repository to GraphUnslopify if available and update repository/dependency/documentation links while preserving existing local checkout and vault identity.
- [x] Final audit: verify each feature against actual code/runtime/artifacts/GitHub state, update Obsidian, and deliver the requested child-friendly paragraph.

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


- Milestone 26 pushed as b532a6e and compatibility follow-up d308f36; general40255756735
  passes all eight jobs and Figure40255756719 passes. Milestone27 resolves the shared identity
  boundary (spec31):62 independent artist/runtime/typed/filter/snapshot controls,215 Node/
  415 Python, all seven local gates, strict gallery15/15 and fresh offline installed artists/
  claims/agent proof. All15 baseline PNGs and both public illustrations have unchanged pixels
  with refreshed code/provenance. Full matrix24, cell annotation contrast32, categorical overlays,
  final exported-width/table context, naming/versioned release and final completion audit remain.


- Milestone28 resolves actual-background cell annotation contrast (spec32):34 independent
  artist/math/normalization/alpha/raster/inspector/runtime/provenance controls;215 Node/449 Python,
  all seven local gates, strict gallery15/15 and522 actual offline browser labels. Fresh installed
  wheel checks real cell artists and an unreadable negative control. Baseline12 and two public
  illustrations are refreshed; their synthetic inputs and fingerprints are committed. Full
  matrix24, categorical overlays/final export width/table context, naming/versioned release and
  final audit remain open. Both GitHub workflows must pass before the next milestone.


- Cell32 provenance follow-up:4245d3c initially stamped CRLF fixture bytes before Git's
  existing LF normalization. Published images are re-stamped from the committed LF CSVs
  without changing any pixels. Explicit LF fixture controls and regeneration guidance prevent
  repeating that mismatch. Seven gates pass again215 Node/449 Python, strict gallery15/15;
  both workflows for the corrected revision must pass before advancing.


- Cell32 corrected revision4c1a8df: General40282733042 passes all eight jobs and
  Figure40282733211 passes. Python3.10/3.12 each448 passed/one TeX skip; render
  separately requires/passes all four TeX cases. Downloaded offline browser proof522 labels
  confirms the measured contrast minima; all four installed-wheel platforms pass.

- Milestone29 resolves supported category overlay coordinates (spec33):44 actual-artist/
  runtime/refusal controls,215 Node/493 Python, all seven gates, strict gallery15/15 and
  three visually reviewed exports. Actual shared facets/repeated metrics use consistent
  positions despite hidden ticks/missing levels. Final fresh offline wheel verifies real
  category/value coordinates and labels, with agent passing. Tracked baseline/public assets
  are unchanged. Both workflows must pass after push. Full21-kind matrix24, remaining
  general categorical contexts, final export width/table context, naming/versioned release
  and final completion audit remain open.


- Overlay33 revision2c5208a: General40285858692 passes all eight jobs and
  Figure40285858808 passes. Both Python3.10/3.12 report492 passed/one TeX skip, with
  all four real TeX cases separately required/passing. All four fresh installed platforms
  verify actual overlay category/value coordinates and lexical labels offline.

- Milestone30 resolves actual exported text size (spec34):37 independent physical-file/
  API/runtime controls,215 Node/530 Python, seven gates, strict gallery15/15 and fresh
  offline wheel. Unknown dimensions and nominal-only/old inspectors cannot certify final
  text size; oversized titles fail strict mode while retaining review artifacts. All19
  baseline/public PNG pixels and dimensions are unchanged, with source/provenance refresh.
  Both workflows must pass after push. Visible table context35, full matrix24/general
  categorical contexts, naming/versioned release and final audit remain open.

- Milestone31 resolves visible table context (spec35):28 independent table controls,
  four real TeX cases,215 Node/558 Python, seven gates, strict gallery15/15 and a fresh
  offline installed wheel with agent. Images/Markdown/LaTeX retain title, row heading,
  metric/unit, interval meaning and bold scope. Percent cells/bounds/descriptions agree;
  fractional confidence labels retain meaning. Public synthetic table inputs and verified
  fingerprints replace untracked inputs. Both workflows must pass before advancing.
  Full21-kind matrix24/general categorical contexts, naming/versioned release and final
  audit remain open.

- Table35 revisiond95c320: General CI40300364215 passes all eight jobs; Figure CI40300364360 passes. Python3.10/3.12 each report557 passed/one TeX skip; render separately requires/passes all four real TeX cases. All four fresh installed platforms pass literal visible context, percentages, actual-width and agent checks offline.

- Milestone32 resolves shared categorical panel identity (spec36):51 complete-workflow
  controls,215 Node/609 Python, seven gates, strict gallery15/15, Ruff and fresh offline
  installed main/agent. Nine presentations preserve values/positions/colours with missing
  categories on physically shared axes. Repeated sorting resets metric state; horizontal
  repeat refusals remain. All20 baseline/public PNG pixels/dimensions stay identical,
  with baseline10 source/provenance refresh. Both workflows require verification after push.
  Matrix24, specialized coordinates/negative-bar domains, naming/versioned release and
  final audit remain open.

- Shared-category36 revisione13f864: General CI40303248511 passes all eight jobs and Figure CI40303248367 passes. Both Python3.10/3.12 report608 passed/one TeX skip; render separately requires/passes all four real TeX cases. All four installed platforms pass actual shared categorical main values/labels offline with agent.

- Milestone33 resolves signed bar visibility (spec37):44 independent controls,
  215 Node/653 Python, zero local skips/warnings, all seven gates, gallery15/15,
  Ruff and fresh offline installed wheel/agent. Automatic bounds preserve full signed
  values; actual container orientation and transformed extents catch clipped bodies.
  Negative/percentage labels are truthful; floating origins remain allowed. All20
  baseline/public PNG pixels/dimensions stay unchanged with three source/provenance
  refreshes. Both workflows require verification after push. Full matrix24,
  naming/versioned release and final audit remain open.

- Signed-bar37 revisiondba728a: General CI40305870292 passes all eight jobs and Figure CI40305870164 passes. Both Python3.10/3.12 report652 passed/one TeX skip; render separately requires/passes all four real TeX cases. All four fresh installed platforms pass actual signed bars/percent labels and the clipped strict negative control offline with agent.

- Milestone34 resolves unused comparison groups and implicit table aggregation (spec38):
  53 independent controls,215 Node/706 Python, zero local skips/warnings, seven gates,
  gallery15/15, Ruff and fresh offline installed wheel/agent. Eight unused group paths,
  including wide-derived groups, refuse explicitly; twelve grouped implementations stay
  accepted. Raw grouped table cells cannot silently acquire a mean; duplicate runtime
  failures exit1. Public table provenance refresh leaves all20 baseline/public PNG pixels
  and dimensions unchanged; all baseline assets remain identical. Both workflows require
  verification after push. Full matrix24, naming/versioned release and final audit remain.

- Comparison-group38 revisionad07ba0: General CI40309430359 passes all eight jobs and Figure CI40309430325 passes. Both Python3.10/3.12 report705 passed/one TeX skip; render separately requires/passes all four real TeX cases. All four installed platforms pass unused-group main refusal and duplicate-table runtime-error evidence offline with agent.

- Milestone35 resolves ridgeline density evidence (spec39):25 hand/SciPy/artist/domain/
  scoped/runtime/provenance controls,215 Node/731 Python, zero local skips/warnings,
  seven gates/gallery15/15/Ruff/fresh offline wheel/agent. Unavailable automatic densities
  retain observations and visible context; strict reports remain incomplete. Actual h/n/
  nonfinite counts and peak normalization are disclosed. A normal830x493 pixel control
  matches the old emitter exactly. Existing50 docs/baseline PNG blobs stay unchanged;
  one new synthetic intentionally incomplete example has committed LF inputs/fingerprints.
  Both workflows require verification after push. Full matrix24, naming/versioned release
  and final audit remain open.

- Expanded image inventory evidence: the earlier20-image check was a selected baseline/
  fifth-pass subset. All50 tracked docs/baseline PNGs were subsequently checked across
  d95c320→e13f864→dba728a→ad07ba0 using Git blob equality plus RGBA/dimension comparison
  of every changed PNG; no pixels/dimensions changed. Spec39 adds a new51st PNG, rather
  than silently refreshing an untracked-data historical example.

- Density39 revisionf456547: General CI40314165034 passes all eight jobs and Figure CI40314165153 passes. Both Python3.10/3.12 report730 passed/one TeX skip; render separately requires/passes all four real TeX cases. All four fresh installed platforms verify normal density h, unavailable strict status and actual retained5/5/5 points/context offline with agent.

- Milestone36 resolves median/SEM estimator mismatch (spec40):33 controls,215 Node/
  764 Python, zero local skips/warnings, seven gates/gallery15/15/Ruff/fresh offline
  installed wheel/agent. Four summary kinds refuse mean-standard-error widths around
  medians in semantic and direct execution paths. Known mean SEM and median bootstrap
  quantities retain declared unit handling; no estimator is substituted.80 direct literal
  finding codes. Baseline scripts/assets and all51 published PNG blobs remain unchanged.
  Both workflows require verification after push. Full matrix24, naming/versioned release
  and final audit remain open.

- Estimator40 revision58e018f: General CI40317401432 passes all eight jobs and Figure CI40317400977 passes. Both Python3.10/3.12 report763 passed/one TeX skip; render separately requires/passes all four real TeX cases. All four fresh installed platforms independently verify mean SEM, median bootstrap CI and median-SEM refusal offline with agent.

- Milestone37 resolves sparse-panel series appearance and legend identity (spec41):
  32 actual-workflow controls across11 grouped kinds,215 Node/796 Python, zero local
  skips/warnings, seven gates/gallery15/15/Ruff/fresh offline installed wheel/agent.
  Styles follow global names; ordinary shared legends include later groups/overlay
  labels, direct labels stay panel/metric-local, and late dumbbell handles/manual
  colours are corrected. Palette-lock channels/reuse and actual values are verified.
  Baseline scripts/assets and51 published PNG blobs are unchanged. Both workflows
  require verification after push. Full matrix24, naming/versioned release and
  final audit remain open.

- Shared-series41 revision04d04d3: General CI40323489159 passes all eight jobs and Figure CI40323489057 passes. Both Python3.10/3.12 report795 passed/one TeX skip; render separately requires/passes all four real TeX cases. All four installed platforms independently verify actual sparse-panel colours/patterns/values and complete shared legends offline with agent.

- Milestone38 resolves bar interval fidelity/visibility (spec42):41 focused controls;
  215 Node/833 full-suite Python plus4 additional controls, zero local skips/warnings;
  seven gates/gallery15/15/Ruff/fresh offline wheel/agent. True1..9 bounds are retained,
  detached intervals and unimplemented stacked uncertainty fail, and clipped stems
  trigger strict policy with review artifacts. Baselines and51 published PNGs remain
  unchanged. Both workflows require verification after push. Complete numerical/
  domain matrix24, naming/versioned release and final audit remain open.

- Bar-interval42 revisionf644564: General CI40326688015 passes all eight jobs and Figure CI40326687812 passes. Both Python3.10/3.12 report836 passed/one TeX skip; render separately requires/passes all four real TeX cases. All four installed platforms independently verify actual1..9 endpoints, clipped stems and detached/stacked refusal offline with agent. Full local rerun215 Node/837 Python and Ruff check/format52 files pass after correcting the initial one-line formatting miss.

  CI warning accounting for42: Python3.10 additionally reports29 warnings:28 upstream Matplotlib3.10 cbook/NumPy scalar-conversion deprecations for single-bar error arrays, and one pandas2 observed-category default FutureWarning. Actual values pass; the latter also motivated the independently measured unused-category matrix case.

- Milestone39 completes core independent reference matrix24:all21 actual kinds are
  documented, six focused estimator suites reused and108 new ordinary-kind value/
  artist/domain/workflow references pass on pandas2.3/3.1. Seven gates215 Node/
  945 Python, zero local skips/warnings; gallery15/15/Ruff53/fresh offline wheel/agent
  pass. Derived waterfall/heatmap, actual shared child axes/context, requested sort,
  observed categories and unknown sums/stacked contributions are corrected. All51
  prior published PNG pixels/dimensions match; one new committed-input sparkline
  adds a current reproducible illustration. Canonical vault is refreshed and old
  milestones archived in the log. Both workflows require verification after push.
  Naming/versioned release and requirement-by-requirement final audit remain active.

- Matrix24 revision2cc1b42: General CI40425926758 passes all eight jobs and Figure CI40425926764 passes. Both Python3.10/3.12 report944 passed/one TeX skip; render separately requires/passes all four real TeX cases. Four fresh installed platforms independently verify actual core quantities, observed categories, unknown sums, shared/log child axes/context and raw-domain refusal offline with agent.

- Milestone40 aligns repository identity (spec43): GitHub rename to public
  unluckyjet/GraphUnslopify succeeds, default main/history/origin are retained and
  current package/docs/action/public links use the new URL. Local JSONTranslator
  and shared-vault JsonTransalter names are preserved. Seven gates215 Node/945 Python,
  zero local skips/warnings; Ruff53, fresh wheel Source metadata and vault97/0 links
  pass. Both workflows require verification after push. Versioned/tagged release
  and the original requirement-by-requirement final audit remain active.

- Naming43 revision3c8f35a: General CI40427095494 passes all eight jobs and Figure CI40427095521 passes. Both Python3.10/3.12 report944 passed/one TeX skip; render separately four required real TeX cases. Four installed platform jobs pass against the renamed repository; metadata/current links are verified. Local checkout/vault identities remain unchanged.

- Milestone41 resolves pre-release numeric-role defect44: Parquet string x1/2/10
  previously became categorical0/1/2 ordered1/10/2 and passed strict; parsed numeric
  views now reach real coordinates and aggregation. Raw filters, lexical IDs,
  unknown extension values and integer precision are preserved.11 controls pass
  on pandas2.3/3.1;215 Node/956 Python, zero local skips/warnings; seven gates,
  Ruff54/gallery15/15/fresh offline wheel/agent. All52 published PNG pixels/dimensions
  match after provenance refresh. Both workflows require verification after push.
  Versioned/tagged release and final full-goal audit remain active.

- Numeric44 revision7873237: General CI40429435553 passes all eight jobs and Figure CI40429435457 passes. Both Python3.10/3.12 report955 passed/one TeX skip; render separately four required real TeX cases. All four fresh installed platforms verify numeric coordinates/string sums/lexical IDs offline with agent. The119 core+numeric controls also pass locally on pandas2.3.3; hosted conversion exactly matches local code for the synthetic healthy spec.

- Release candidate45 synchronizes0.7.0 Python/emitter/Node versions, ships versioned
  docs/quickstart/action pins and refreshes canonical source/provenance. Seven gates
  215 Node/956 Python, zero local skips/warnings; Ruff54/gallery15/15/fresh0.7 offline
  wheel/agent and bundle/license/metadata/doc-link checks pass. All52 published PNG
  pixels/dimensions match. Both candidate workflows, verified Git-snapshot artifact
  builds, actual tag/release publication and genuine downloaded wheel/sdist installs
  remain required before distribution is complete. Full final audit remains active.

- Release45 verified: v0.7.0 targets7ffa1076494a93b600086054ffc5dcd3c137796c. Main General40430862411/Figure40430862382 and tag General40431685471/Figure40431685560 all pass; each General run passes all eight jobs, both Python versions955 passed/one TeX skip, render four required real TeX cases and four installed platforms. Anonymous published assets match SHA256SUMS/GitHub digests; downloaded wheel and published-sdist-built wheel each pass independent clean outside-checkout/offline-runtime/agent tests. The published sdist rebuilds the exact wheel bytes. Hosted0.7 compiler matches local source.

- Release-verification record b4ac69b: General40432740721 passes all eight jobs and Figure40432740734 passes. Final audit46 maps each original requirement to actual implementation, runtime evidence, public release artifacts and maintained project knowledge. The exact public pip URL also passes doctor/demo in a third clean environment. Release source remains v0.7.0/7ffa107; final documentation checks/CI are recorded with the handoff.
