# Frozen external reference corpus

Status2026-10-29: **72 formal runs complete; all expected outcomes pass**.
See [measured results](certified-benchmark.md), including the invalid paired-authoring-time interpretation.
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

## Frozen measurement protocol

[Protocol v2](../../benchmarks/certified/protocol.json) binds the complete source
manifest and evaluator/worker hashes. Its implementation is
[measurement.py](../../benchmarks/certified/measurement.py); the isolated
[save-time worker](../../scripts/measure-certified-figure.py) records the actual
artists at each PNG/SVG/PDF export, plus final file hashes and process failure.
Sixteen synthetic controls validate this evaluator before any NIST product output is run.
Formal v2 outcomes are in [the measured report](certified-benchmark.md); initial v1 task validations and correction remain below.

The task has one mean marker and one observed sample-SD interval per dataset,
with exact labels and separate original scales. All nine cases, two arms, two
variants (correct task and intentionally missing interval) and two repetitions
are mandatory. Matplotlib uses the same external evaluator as GraphUnslopify;
this is a strong validated comparator. Built-in tool status is recorded separately
from benchmark task acceptance; a deliberately omitted interval may render with
exit0 while failing the external task. Do not credit that as a built-in catch.

Numerical gates use external decimal facts, one last-printed decimal unit for
non-exact reference precision, input float representation error and explicit8/16
coordinate ULP allowances. Record continuous errors and their allowances. Plotted
half-span is derived from the actual endpoints; it does not measure an underlying
SD estimator's full precision. These are declared engineering gates, not NIST
certification or a universal floating-point error proof.

Quality proxies decode the actual three formats, check nontransparent marker/
interval membership and axes coverage,2px interval visibility and6pt text at a
3.4in final width. Actual drawn text is observed through draw calls, avoiding
retained undrawn tick labels. Text-overlap candidates need visual review; proxies
do not establish aesthetic quality or researcher usefulness. Reproduction checks
actual decoded PNG dimensions/pixels within each arm, with missing files explicit.

Development-session clocks will begin before writing each arm-specific producer,
end after the first correct nine-case verification, and retain failures/attempts.
This is one already-familiar, unblinded coding assistant, Matplotlib first and
GraphUnslopify second. Report shared harness/preparation and producer/payload/code
sizes alongside task clocks. This fixed-order single-operator observation cannot
establish a causal productivity benefit or human development time. Machine build,
process, instrumented execution and save timers remain separate; instrumentation
overhead is included and disclosed.

## Measurement contract for execution

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


## Runner and live producer tasks

The [runner](../../scripts/certified-benchmark.py) validates prepared CSVs against
all original pinned observations, then schedules every case. It retains separate
build/execution logs, external numeric/label/quality decisions, native
GraphUnslopify report status, per-file identities and source/environment hashes.
Study-end rechecks reject deleted/changed files; execution failures are distinct
from correctly detecting the deliberately missing-interval sentinel. Repeat
agreement includes process/native statuses, and numerical summaries include the
number of values actually measured.

Both producers are implemented. Their initial task validations exposed the configuration/evaluator issues documented below.
Their interface is `--dataset ID --data CSV --out-dir EMPTY --variant mean_sd`
(or `missing_interval`); they write `figure.py` and optional `spec.json`. Names
are `benchmarks/certified/producers/build-matplotlib.py` and
`build-graphunslopify.py`, avoiding Python's library-module shadowing.

The recorded construction protocol began the Matplotlib task **before** creating
its producer (these are historical study-construction commands, not rerun commands
for the now-existing committed producers):

```sh
python scripts/certified-benchmark.py --begin-development matplotlib
# Implement the producer under the fixed protocol, then verify all nine clean cases.
python scripts/certified-benchmark.py --development matplotlib --out-dir benchmarks/certified/.cache/matplotlib-attempt-1
```

Failed attempts stay in fresh output folders; the original session clock keeps
running. A successful nine-case verification appends an end event. Repeat with
`graphunslopify` only after the Matplotlib task finishes. The tracked
`benchmarks/certified/development-sessions.jsonl` and
`benchmarks/certified/development/` metadata preserve live UTC/monotonic events and
all verification reports. Observation data and full local run folders stay in the
ignored cache; metadata contains reference facts/measurements rather than raw rows.
Complete a live session on the same machine/OS boot: monotonic clock origins
are local. Both UTC and monotonic events are retained for audit. These commands
are the implementation protocol, not evidence that sessions ran.

After the current checkpoint passes, reproduce the full72-execution comparison with:

```sh
python scripts/certified-benchmark.py --out-dir benchmarks/certified/.cache/comparison-1
```

Optional `--source-dir`/`--prepared-dir` select other verified local input caches.
Every run requires a fresh output directory and records progress/results without
replacing prior evidence. CI will execute this comparison after the actual
producers/results checkpoint; current runner controls use synthetic fixtures only.


## Initial task validation and protocol revision

The live Matplotlib task completed all nine clean cases on its first attempt:
42.188505542 seconds from implementation begin to accepted nine-case verification.
This is one familiar coding assistant's observation, not a human productivity result.
Its conventional program reads every CSV value and uses Python statistics.mean /
statistics.stdev before plotting, with the same external evaluator as the product.

GraphUnslopify's first attempt failed all nine cases because the author supplied
categorical dataset names to a line's numeric x domain. This is one configuration
error repeated over nine cases, not nine independent scientific defects. The next
producer version retains all observations and generated mean/SD computations;
a small Python presentation adapter adds a constant numeric x position and applies
the dataset tick label. Both unmodified translation and final adapted code are
retained. This workflow requires that explicit adapter; it is not JSON-only.

The second GraphUnslopify attempt produced numerically correct, correctly labelled
exports on all nine cases and native passed reports. It failed v1's byte-only
save/finalization identity check because record_output adds SVG accessibility IDs /
description and normalizes path whitespace after Figure.savefig. PNG/PDF byte
identities and all other physical/visibility checks passed. The evaluator's
intermediate-stage byte rule was an incorrect proxy for this legitimate pipeline.

V2 corrects only that evidence rule. Cases, variants, repeats, external answers,
numerical allowances and physical-size gates are unchanged. Native static SVG
may use graphic-DOM identity that preserves geometry, visible text, styles and
provenance, while allowing the known root accessibility additions and path-space
normalization. Unsupported dynamic/non-native structures do not get that exception.
Raw save/final hashes and identity basis remain visible. Once finalization has
completed, study-end retention requires exact final bytes for every format.
Negative controls reject changed paths/view boxes, visible text, provenance and
styles, as well as metadata-only file changes after finalization.

[The original v1 protocol](../../benchmarks/certified/protocol-v1.json), all27
initial case records, first/all failed attempts and exact producer revisions are
retained in [development evidence](../../benchmarks/certified/development/) and
[the append-only session log](../../benchmarks/certified/development-sessions.jsonl).
V1 evaluator implementation is preserved at commit4b8cb8f. Historical producer
copies match their recorded SHA256; restore their original producer path when
replaying them rather than executing the archive copy directly.

The GraphUnslopify clock continued without reset across an explicit protocol-
revision event. Its elapsed time includes shared evaluator debugging/repair and
waiting; it **cannot support a paired workflow-authoring-speed comparison** with
the42.19s Matplotlib task. Retain that confound rather than subtracting unrecorded
work or retroactively manufacturing a completion time. Fair machine timings and
all formal outcomes are recorded separately under the frozen v2 protocol.
The GraphUnslopify task subsequently passed all nine cases under v2 and closed
its original clock at3171.1415s, still invalid for paired authoring inference.
The formal72-run comparison passed; all36 task-validation executions remain.
Human development time and independent researcher execution are unmeasured.

The durable publication helper is `scripts/publish-certified-results.py`; its
[checked-in report package](../../benchmarks/certified/results/) contains run-level
metadata/representative copied figures, not source observation data.
