# Frozen external reference corpus

Status2026-10-29: **source preparation measured; product benchmark not run yet**.
This checkpoint freezes externally established answers before GraphUnslopify or
Matplotlib outputs are evaluated. It advances review17 without turning source
preparation into an accuracy, timing or adoption result.

## Selection and independent answers

Use the complete nine-dataset
[NIST StRD univariate collection](https://www.itl.nist.gov/div898/strd/univ/homepage.html),
in publisher order. Keep all difficulty levels and all outcomes. The frozen
[manifest](../../benchmarks/certified/sources.json) records original-byte SHA256,
size, row count, certified decimal strings and exactness flags. NIST selected the
datasets and established the reference values; this project selects the supported
mean/sample-SD plotting workload and conducts the evaluation.

| Stratum | Datasets | Observations |
| --- | --- | --- |
| Lower | PiDigits, Lottery, Lew, Mavro, Michelso, NumAcc1 | 5,571 |
| Average | NumAcc2, NumAcc3 | 2,002 |
| Higher | NumAcc4 | 1,001 |

There are8,574 observations in102,474 source bytes. The publisher's observed/
generated labels are retained; PiDigits and Lottery are not laboratory studies.
The three measurement datasets and four generated challenges support different
questions. [NIST explains](https://www.nist.gov/itl/sed/statistical-reference-datasets/strd-background-information/univariate-summary-statistics)
why near-constant values and accumulation can expose numerical problems.

Only mean/sample-SD and their plotted endpoints are planned accuracy targets.
Lag1 autocorrelation is retained as publisher metadata and remains outside this
workload; this is not the whole StRD method collection or software certification.
See the [source notice](../../benchmarks/certified/NOTICE.md).

## Reproduce preparation

```sh
python scripts/prepare-certified-data.py --source-dir benchmarks/certified/.cache/sources --out-dir benchmarks/certified/.cache/prepared --download
python scripts/prepare-certified-data.py --source-dir benchmarks/certified/.cache/sources --out-dir benchmarks/certified/.cache/prepared-offline
```

The first command explicitly downloads missing files. The second runs offline.
Run from the repository root. This ignored cache persists locally for reuse;
the original inputs and observation views are not committed or uploaded.
Use fresh/empty output directories; changed cache entries and prior output are
never overwritten. A descriptive, honest research-client User-Agent is recorded
in the manifest. In this environment NIST returned Cloudflare1010/403 to the
default urllib client; the identified GraphUnslopify research client succeeded.

The standard-library importer validates every raw hash/size, identity, header
reference, sample-SD denominator and exactness flag, row count and finite decimal
token before creating derived output. CSVs preserve decimal token precision and
observation order; row IDs are bookkeeping, not proof of sampling independence.
All inputs are validated before output creation. `preparation.json` binds source/
manifest/CSV hashes and declares `status: prepared`, without product metrics.
Source files/observation CSVs stay local; CI retains preparation metadata only.

## Preparation evidence (2026-10-29)

All nine actual publisher files passed the pinned raw/header checks. Fresh online
and cached offline preparations produced identical metadata and CSV bytes. A
separate comparison checked every one of8,574 output value strings, row IDs and
observation order against the original source lines. Eleven automated negative/
repeatability controls pass. These measurements cover preparation only.

## Measurement contract for the next benchmark checkpoint

Before evaluating product outputs, implement and freeze the following task and
measurement definitions. Preserve all nine datasets, failures and repeat
disagreements; do not tune a gate after seeing its outcomes.

- Produce a separate mean/observed-SD figure per dataset in its supplied units.
  Mixing their physical quantities on one shared value axis would be misleading.
  SD describes spread; it is not a confidence interval or evidence of independence.
- Compare a conventional Matplotlib workflow and GraphUnslopify against the same
  external reference facts. Retain a validated Matplotlib alternative; do not
  count normal rendering as scientific checking or claim superiority over a weak
  comparator without stating the difference.
- Measure actual drawn mean/interval endpoints against the publisher answers.
  Record decimal deviations and float representability/ULP context separately;
  recovering a small SD by subtracting large plotted coordinates can lose digits.
  Do not present a renderer's rounding floor as newly detected scientific error.
- Freeze numerical gates, artist extraction, case variants and figure-quality
  proxies before the first evaluation. Keep continuous errors and unsupported
  quantities visible; changing a gate requires a new protocol revision with the
  earlier result retained.
- Repeat each workflow twice, alternate execution order, retain logs/statuses,
  source/environment fingerprints and decoded-PNG reproduction results. A missing
  figure is not a successful reproduction. Do not require pixel equality between
  different renderers.
- Record machine execution/startup/export timings separately from authoring
  payload size and shared helper code. These are not measured human development
  time. Any timed agent construction task must be separately defined and reported
  as such; no human results are inferred from an automatic timer.
- Define objective quality proxies at the final export size and distinguish them
  from blinded human quality/usefulness judgments. User trials remain deferred.

The wider item17 requirement remains open until the actual benchmark is executed
and its required metrics have evidence. This frozen corpus is an independent
reference, while study design/execution remain project-authored. The existing
[synthetic pilot](benchmark.md) and [public-paper comparison](published-papers.md)
retain their own scopes and measured results.
