# Review improvements: 2026-10-28

User-provided follow-up list after the 0.7.0 delivery and README rewrite.
This is separate from the completed [original roadmap](implementation-roadmap.md).
Commit/push each completed item or coherent implementation milestone and check
both CI workflows before advancing. Source and measured behavior take precedence
over the review's descriptions. Extend existing implementations where present.

## Order and checkpoints

| Phase | Review items | Objective |
| --- | --- | --- |
| Reliability | 1, 2, 4, 5 | Safe execution defaults, defensible checks and feature interactions. |
| Distribution | 6, 13, 14, 15, 16 | Registry distribution, identity and onboarding. |
| Research workflows | 8, 9, 10, 11, 12 | Comparison, integration, project management, diagnostics and environments. |
| Expansion | 3, 7 | Existing-paper inspection and editor usability. |
| Validation | 17, 18, 19, 20 | Measured benchmarks, external feedback, real data and contribution infrastructure. |

The user's subsequent 9.0/10 review explicitly prioritizes adoption evidence over
another feature cycle. Work now starts with items17/18 (measured pilot and external
testing preparation), then13/14,6 and3. The user subsequently deferred volunteers
and requested papers/public datasets: item19 becomes the next validation milestone.
External results remain open until observed.

| Item | Priority | Target | Current state |
| --- | --- | --- | --- |
| 1 | P0 | Strict verification by default across generated scripts, CLI and Python builder. | Implemented: [spec47](done/47-strict-verification-default.md); explicit opt-out preserves reports. |
| 2 | P0 | Broader statistical assumptions, unit/uncertainty and comparison validation. | [Design-aware comparisons](../docs/comparison-design.md), [spec54](done/54-statistical-comparison-design.md): matched t/sign-flip tests, unit/assumption/exclusion records, incompatible estimator/cohort refusals and planned-family correction. IDs do not certify independence. [Large-offset stability follow-up57](done/57-comparison-numerical-stability.md) preserves equivalent test results. Source additions after0.8.0. |
| 3 | P0 | Extract/inspect existing-paper PDF figures with source-free warnings clearly scoped. | [Local PDF review packets](../docs/pdf-review.md): pages/text/explicit crops, scoped incomplete reports and a real14-page manuscript probe. Automated figure interpretation/numerical reconstruction remain outside scope. |
| 4 | P0 | Misleading scaling, omissions, annotations and visual exaggeration checks. | Pending; extend current geometric/semantic inspection. |
| 5 | P0 | Interaction and edge-case regression coverage. | Pending; extend the existing independent reference matrix. |
| 6 | P1 | Publish an installable PyPI release. | [0.8.0 published on PyPI/GitHub](../docs/releases/0.8.0-publication.json); matching hashes, downloaded-source rebuild and genuine fresh registry/agent/PDF/strict-default/offline-runtime installation verified. |
| 7 | P1 | Easier editor controls and clearer explanations. | Pending; preserve existing live preview, strict checks and exports. |
| 8 | P1 | Visual before/after figure comparison reports. | Pending; extend current manifest/baseline comparison. |
| 9 | P1 | Research-environment and experiment-tracking integrations. | Pending; build on current notebook, editor, agent and LaTeX workflows. |
| 10 | P1 | Project-wide figure management and status/history. | Pending; reuse manifests and shared visual identity. |
| 11 | P1 | Actionable problem/consequence/correction diagnostics. | Pending; audit existing messages and repairs. |
| 12 | P1 | Dependency/rendering/execution environment provenance. | Pending; extend current versioned evidence envelope compatibly. |
| 13 | P2 | GitHub repository description. | Branding checkpoint49 updates the live description to scientific figure generation and checks. |
| 14 | P2 | Homepage and deployment branding. | [Branded GitHub Pages homepage](../docs/homepage.md) and current content; legacy Vercel API remains available. Renaming that service requires Vercel access. |
| 15 | P2 | Outdated documentation and installation references. | Current0.8.0 installation/versioned guides and composition/Figure CI progress prose refreshed in release preparation. |
| 16 | P2 | Minimal installation and five-minute complete tutorial. | Pending; build on the existing runnable demo and README. |
| 17 | High | Realistic comparative benchmarks with measured outcomes. | [Synthetic pilot](../docs/validation/benchmark.md),48 executions/three arms, plus [public-paper comparison](../docs/validation/published-papers.md),32 executions/two arms. Independent held-out scientific benchmarking remains open. |
| 18 | Deferred | External researchers testing their own datasets. | User explicitly deferred volunteers; [prepared protocol](../docs/validation/researcher-pilot.md) retained for later. Current route is public papers/datasets. No sessions conducted. |
| 19 | High | Reproducible public research-dataset examples. | [Penguin/Iris paper-linked cases](../docs/validation/published-papers.md), pinned licensed inputs, separate calculations, actual artists and seeded faults. Full paper replication/independent external validation remain outside measured scope. |
| 20 | P2 | Contribution, issue, security and public roadmap infrastructure. | Pending assessment and implementation. |

## Evidence rules

- Record commits, exact CI runs and measured acceptance results at each checkpoint.
- Preserve the published 0.7.0 tag/artifacts. Unreleased main behavior must not be
  attributed to that wheel or its versioned documentation.
- Keep credentials and private datasets out of commits and the Obsidian vault.
- Registry access, domains, human feedback and third-party service access may
  require external input. Prepare concrete artifacts first and report such needs
  without inventing publication, adoption, benchmark or user-study results.

## Progress

- Item1: strict-by-default implementation passes217 Node/1003 Python, seven gates,
  strict gallery15/15, Ruff55 and two independent audits. All52 prior PNGs retain
  identical pixels/dimensions. This is a separate checkpoint; its exact-commit CI
  is checked after push before advancing. This is historical item1 evidence; current states are in the table above.

- Item2/spec54:221 Node/1056 Python, all seven gates, gallery15/Ruff61 and
  all60 existing PNG pixel identities pass. Fresh source-wheel agent/PDF/offline
  smoke and installed paired comparison pass. Source additions remain distinct
  from the immutable0.8.0 registry release. Exact commit CI checked after push.

- Follow-up57 repairs a measured numeric-offset counterexample:221 Node/1064 Python, seven gates/gallery15/Ruff61 and actual installed offline shifted/centered references pass. Exact pushed CI is checked before item4.
