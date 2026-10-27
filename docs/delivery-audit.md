# Delivery audit for 0.7.0

Reviewed release: [v0.7.0](https://github.com/unluckyjet/GraphUnslopify/releases/tag/v0.7.0),
commit `7ffa1076494a93b600086054ffc5dcd3c137796c`. This record checks the accepted delivery
roadmap against implementation, real runtime results, published artifacts and GitHub state.
It does not certify a user's experimental design, independence, inference or publisher policy.

| Requirement | Concrete implementation | Reviewed execution evidence |
| --- | --- | --- |
| Statistical integrity | Missing/estimator-specific uncertainty, declared unit weighting, sample/exclusion accounting, exact/seeded permutations, Holm/BH corrections, uncertainty-aware table wording and explicit failed/untested claims. | [Unit tests](../test/repeat-units.test.ts), [permutation references](../test/significance.test.ts), [hand correction vectors](../python/tests/test_significance.py), [SEM/median](../python/tests/test_sem_estimator.py), [true interval endpoints](../python/tests/test_bar_intervals.py), [strict report states](../python/tests/test_runtime_report.py). |
| Trustworthy figures | Literal descriptions/context, recoverable provenance, supported composition/export parity, embedded fonts, measured exported width, contrast and stable group/category/series identity. | [Compiled text](../python/tests/test_text_exports.py), [provenance](../python/tests/test_provenance.py), [physical widths](../python/tests/test_exported_text_size.py), [contrast](../python/tests/test_cell_contrast.py), [HTML quantities](../python/tests/test_interactive.py), shared-category/series suites and strict gallery 15/15. |
| Licensed local/versioned distribution | MIT project and bundled dependency licenses; packaged translator/runtime; short wheel quickstart; tagged source/docs/action references and installable release assets. | Anonymous release downloads, exact digest checks, two independent fresh installs and identical source-to-wheel rebuild, detailed below. |
| Researcher CI | [Reusable composite action](../.github/actions/figure-ci/action.yml) with strict reports/staged evidence, plus [consumer workflow](../.github/workflows/figure-ci-example.yml). | [Actual caller wrapper tests](../python/tests/test_figure_ci.py) inspect passing/failing reports and exclude unrelated CSV; main and tag Figure CI workflows pass. |
| Python/notebook/agent integration | All 21 Python constructors, packaged notebook execution and local stdio MCP/configuration using the installed environment. | [Builder/recipe contracts](../python/tests/test_build.py), [real notebook kernel](../python/tests/test_notebook.py) produces a plot and expected rejected claim; [MCP tests](../python/tests/test_mcpserver.py), installed SDK/agent smoke. |
| Paper/batch auditing | Manifest-driven spec/script/data/claim execution, stable comparison, data/numeric/pixel/claim changes, meaningful failure policy and current review artifacts. | [Audit references](../python/tests/test_audit.py) execute real directories, stable baselines, altered data/claims/pixels, invalid manifests, partial failures and timeouts. Arbitrary image interpretation is not claimed. |
| Visual workflow | Packaged local editor: upload data, edit specs/recipes, strict preview, diagnostic fixes, selected exports and explicit data inclusion. | [Server tests](../python/tests/test_preview.py) and [real browser interaction](../scripts/preview-check.ts) apply fixes, exercise failures, download ZIPs, verify omission/inclusion and rerender exported Python outside checkout. |
| Independent references | [All 21-kind matrix](scientific-validation.md): six specialized estimator suites plus 108 ordinary-kind controls and 11 numeric-view controls. | Hand/SciPy or observation-level quantities reach actual artists/tables/descriptions; missing/invalid data and actual strict workflows are checked. Combined 119 core/numeric controls pass on pandas 2.3.3 and 3.1. |
| Naming | Public [unluckyjet/GraphUnslopify](https://github.com/unluckyjet/GraphUnslopify), default main/history retained; current package/docs/action/source links updated. | Actual GitHub identity/origin and metadata/link inventory verified; existing local checkout/shared-vault names deliberately retained. |
| Project knowledge and audit | Repository AGENTS points to maintained shared project knowledge; current canonical notes replace superseded gaps, history stays in the log and transferable concepts have backlinks. | Vault wiki links resolve, one shared vault/no nested project vault verified, standing preference remains in global guidance; this audit links each original delivery requirement to current evidence. |

## Runtime gates and limits

The exact release source passes all seven required commands:

```sh
npm run typecheck
npm test
npm run test:python
npm run baseline -- --check
npm run render-check
npm run recipe-check
npm run compose-check
```

Local results: 215 Node/956 Python, no local skips/warnings; 15 matching baselines,16 render cases,
25 recipes/seven compositions; strict gallery 15/15 and Ruff check/format 54 files. Actual browser
checks include offline HTML cell labels and editor/export interaction. All 52 prior published PNGs
retain identical decoded pixels/dimensions through the release version/provenance refresh.

[Main checks 40430862411](https://github.com/unluckyjet/GraphUnslopify/actions/runs/40430862411) and
[main Figure CI40430862382](https://github.com/unluckyjet/GraphUnslopify/actions/runs/40430862382)
pass. [Tag checks40431685471](https://github.com/unluckyjet/GraphUnslopify/actions/runs/40431685471)
and [tag Figure CI40431685560](https://github.com/unluckyjet/GraphUnslopify/actions/runs/40431685560)
also pass. Each checks run has all eight jobs green: Python 3.10/3.12 each 955 passed/one TeX skip,
render separately requires/passes all four real TeX cases, and fresh installed-wheel jobs pass
on Linux3.10/3.12, macOS3.12 and Windows3.12. Python 3.10 reports28 upstream Matplotlib/NumPy
single-bar-array deprecations; the previous pandas observed-category warning is resolved.

These are computational/domain references and declared feature checks, not an exhaustive
cross-product of every optional transform/style/composition or a population coverage benchmark.
Strict automation rejects failures/incomplete checks; legacy default exit behavior remains
explicit. Unsupported combinations and unavailable requested estimates are not silently certified.

## Published artifact verification

The release is public/non-draft. Remote tag v0.7.0 points exactly to the reviewed commit.
The source was exported from Git before building, avoiding ignored/untracked checkout files.

| Asset | SHA-256 |
| --- | --- |
| graphunslopify-0.7.0-py3-none-any.whl | `04e44653c40943f0b13ff5b1054e94fca2a8bdd1012e5bc65015ccda9a4bd66d` |
| graphunslopify-0.7.0.tar.gz | `f782bb13989c4e7cb5df6e09722f1521d42da774af22df84e6c1b7b98b2a12fb` |

Anonymous public downloads match SHA256SUMS, pre-upload hashes and GitHub's reported digests.
The downloaded wheel passes the full installation smoke with optional agent in a fresh virtual
environment outside the checkout; external network connections are blocked after installation.
The independently downloaded/extracted sdist builds a wheel with the exact same hash, then passes
a second independent fresh/offline-runtime installation smoke. This byte-identical rebuild was
measured with the reviewed build environment and SOURCE_DATE_EPOCH; it is not a promise about
all future build-tool versions.

The exact documented public-wheel-URL `pip install` also passes in a third fresh environment
outside the checkout; installed `doctor` returns ok/version 0.7.0 and `graphunslopify demo`
produces a passed/checked report and PNG/SVG/PDF files. Dependency installation uses the network;
the two artifact smokes above separately verify offline runtime.

Project and Zod license contents match source. Package/compiler doctor agrees on 0.7.0. Tagged
installation/reference documentation blob IDs match the reviewed source. The live hosted health
endpoint reports 0.7.0/21 kinds/25 recipes and its healthy synthetic translation exactly matches
the local compiler. PyPI/npm registry publication is not required and is not claimed.

See [versioning](versioning.md), [installation](installation.md), [release notes](releases/0.7.0.md),
[reference matrix](scientific-validation.md) and the repository
[delivery checklist](../pipeline/implementation-roadmap.md). Historical per-milestone evidence
remains in pipeline/done and the project investigation log.
