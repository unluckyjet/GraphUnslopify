# Public roadmap

Status reviewed2026-10-29. This roadmap describes direction and evidence, not
release dates or promises. The detailed [20-item review](pipeline/review-roadmap-2026-10-28.md)
tracks individual checkpoints, commits, verification and open dependencies.
[Focused specs](pipeline/README.md) describe implementation acceptance criteria;
[future ideas](docs/future.md) are proposals.

## Available now

The published [0.8.0 release](docs/releases/0.8.0.md) includes semantic figure
generation, strict verification defaults, local editing, paper/source audits and
ordinary-PDF review preparation. It is available on PyPI; its
[publication evidence](docs/releases/0.8.0-publication.json) records tested installs.

Current source adds design-aware comparisons, data-view/annotation checks,
cross-feature regressions, environment provenance, visual comparison packets,
research workspace/MLflow integration, broader editor controls, paper-wide history
and shared settings, actionable diagnostics, and source-free PDF text-size/raster-resolution measurements. See the review table for each
measured scope. Install from source for these additions; they are not changes to
the immutable0.8.0 distribution.

The [current PDF inspection](docs/pdf-review.md) measures supported visual properties
in pages and selected crops. Numerical claims, raster-only text, complex clipping
and general chart interpretation remain unverified; it is not automatic figure
recognition or a scientific certificate.

## Remaining work

| Priority | Work | What would establish progress |
| --- | --- | --- |
| High | Broader external scientific benchmarking. | Realistic tasks, independently established answers, fair Matplotlib comparators, measured errors, timing, reproducibility and defined figure-quality checks. Current synthetic/public-paper comparisons are author-run; no independent evaluation or human development-time advantage is established. |
| Deferred by user | Researchers testing their own projects. | Actual external sessions and recorded feedback when this work is resumed. The prepared protocol is not a completed user study; the current requested route uses public papers/datasets. |

The [frozen external-reference corpus](docs/validation/certified-reference.md) adds
all nine NIST univariate datasets and independent certified answers for the next
comparison. Initial task validations and a versioned SVG-evidence correction are recorded;
all prior outcomes remain visible. The formal comparative benchmark is pending.

The existing [public-data examples](docs/validation/published-papers.md) reproduce
bounded descriptive quantities from Penguin/Iris data and test seeded faults.
They do not reproduce the full papers or establish adoption. The
[synthetic pilot](docs/validation/benchmark.md) records what was measured and what
remains unanswered.

## Help shape the next change

Use the [contribution guide](CONTRIBUTING.md) and
[issue forms](https://github.com/unluckyjet/GraphUnslopify/issues/new/choose).
Suggest a concrete research task, available public data, the question to answer
and what would prove success. Report vulnerabilities through [SECURITY.md](SECURITY.md).
Measured results and current source take precedence over ratings or a count of
closed implementation specs.
