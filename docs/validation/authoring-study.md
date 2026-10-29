# Familiarized agent authoring-time study

Status 2026-10-29: **all four prospective episodes complete;36/36 clean cases accepted**.
Preregistration c98fc52 passed exact main40871787084 all9/Figure40871786787 before
any clock. First-pair7fbe362 exact main40876799302 all9/Figure40876799313 and its
actual18-case replay artifact passed before the reverse pair began. The nine-
dataset task and all original v2 numeric/physical/export gates stayed unchanged.

| Round/order | Matplotlib seconds | GraphUnslopify seconds | Accepted cases |
| --- | ---: | ---: | ---: |
| 1: Graph then Matplotlib | 16.953347625 | 21.744921709 | 18/18 |
| 2: Matplotlib then Graph | 17.439072041 | 22.175923792 | 18/18 |
| Descriptive median,2 episodes per arm | 17.1962 | 21.9604 | 36/36 total |

Matplotlib was faster in both pairs on this task. These are four observations
from **one** already-familiar coding assistant, with model/tool/verification wall
time included and earlier shared preparation excluded. They do not establish
first-use human, causal or general productivity advantage. All four completed on
the first attempt; no outcomes were omitted to obtain this result.

The publication audit reread all108 original final export hashes/36 decoded PNGs,
all source/runtime/input fingerprints, the complete9-case episode sequences and
raw clock math. UTC and monotonic elapsed agree within0.001s. There were no shared
code changes, CI/docs/vault work or recorded interruptions inside any episode.
The full four-producer local replay passes36/36, with `study_complete:true`.
Replay generates fresh outputs and preserves historical clocks; it never creates
new authoring-time observations.

All numerical/physical proxies pass. Minimum measured text at3.4in target is
9.24pt Matplotlib/8.02pt Graph, with zero overlap candidates. All18 PNG pairs from
the two different implementations of each arm/dataset have identical decoded
pixels. These are9 datasets, repeated implementations/exports, not108 independent
scientific experiments or four independent participants.

[Complete audited summary](../../benchmarks/authoring/results/summary.json),
[36-row run metadata](../../benchmarks/authoring/results/runs.csv),
[raw session events](../../benchmarks/authoring/sessions.jsonl),
[first-pair historical summary](../../benchmarks/authoring/round1-summary.json),
[retained full attempts](../../benchmarks/authoring/development/).

The [NIST comparison](certified-benchmark.md) measured numerical errors,
reproducibility, machine timing and physical export proxies. Its first authoring
episodes cannot support a paired speed comparison: one included shared evaluator
repair and CI waiting. Keep those records and their invalid-timing flag.

This follow-up measures fresh reimplementation by one already-familiar coding
assistant, using the same complete nine-dataset task and unchanged NIST v2
verifier. It supplements the first episodes. It does not measure first-use human
learning, independent researchers or causal/general productivity gains.

[Prospective protocol](../../benchmarks/authoring/protocol.json),
[controller](../../benchmarks/authoring/session.py),
[measured preflight receipt](../../benchmarks/authoring/preflight.json).

| Round | First episode | Second episode |
| --- | --- | --- |
| 1 | GraphUnslopify | Matplotlib |
| 2 | Matplotlib | GraphUnslopify |

All four were required regardless of which workflow was faster. Each new producer
starts absent, reads all observations, and implements nine mean/sample-SD figures
with the existing labels, PNG/SVG/PDF exports, numerical allowances, physical-size
checks and exact finalized-file retention. Producers may use documentation/library
APIs and remembered patterns; do not copy an existing producer file or use an
arm-specific prepared generator. The same CSV/statistics/Matplotlib alternative
and real local GraphUnslopify compiler remain the compared workflows.

## Clock and retained evidence

A live UTC/monotonic begin precedes further producer-specific lookup/writing.
A matching machine-boot identity, interpreter/platform, dependency versions and
shared runtime fingerprints must remain stable. A failed subject attempt keeps
the original clock running. All nine cases must verify before it ends; partial,
duplicate, reordered or source-unbound results cannot end an episode. Actual
source snapshots, full case reports and every attempt remain retained.

Format/lint the new source inside its episode before successful verification;
changing it afterward would invalidate its recorded source hash. Finish episodes
before doing CI, documentation, vault maintenance or unrelated work. Disclose
interruptions/shared-harness repairs as confounds without resetting the clock.
Prior shared preparation/familiarity/CI outside episodes is excluded and
unmeasured. Report that cost separately from authored/payload/generated code size.

The source manifest, nine-dataset selection, mean/sample-SD task and existing v2
numeric/physical/export rules remain unchanged. The authoring protocol additionally
binds its controller/CLI/runner implementation hashes. Do not change those files
after clocks start; a changed study needs explicit retained/versioned evidence.
A new producer-path argument lets the existing case worker assess each fresh
implementation without replacing either original producer or its earlier results.

## Run from an editable checkout

Install the checkout with `python -m pip install -e ./python`. Prepare the pinned
public inputs using [the existing source guide](certified-reference.md). Select
fresh output directories throughout:

```sh
python scripts/authoring-benchmark.py --preflight --out-dir benchmarks/authoring/.cache/preflight-new
python scripts/authoring-benchmark.py --begin
# Write only the newly named producer from the begin response, then lint/format it.
python scripts/authoring-benchmark.py --attempt --out-dir benchmarks/authoring/.cache/round1-graph-attempt1
```

Begin returns the next declared episode/source path. On failure, retain that
output, fix the subject producer and invoke another `--attempt` with a fresh
output path. On success its end event is appended to
`benchmarks/authoring/sessions.jsonl`; only then begin the next declared episode.
The generic driver never writes the arm-specific producer for the operator.
Raw/derived source observations stay in the ignored persistent cache; Git and CI
artifacts contain metadata, source programs and our generated plots.

## Preflight evidence

Both existing canonical producers passed all nine datasets through the new
producer-path route: 18 runs/54 final PNG/SVG/PDF exports. This is validation of
shared machinery before authoring clocks, not four completed implementation
sessions. Full local reports are retained in the ignored
`benchmarks/authoring/.cache/preflight-final/`; the committed receipt records their
hashes, original producer hashes and the unchanged v2 verifier identity.
CI repeats the actual 18-case preflight and uploads its complete artifacts.

Clock guards and a real synthetic producer/PNG/SVG/PDF test cover restart,
clock-origin/protocol/runtime mutation, partial/duplicate/reordered success,
changed-source retention and preservation of failed attempts. Current results
and exact pushed CI are recorded in the project knowledge and implementation spec.

## Reporting limits

Retain all four elapsed times, the two pairings and any failures rather than
stopping on a favorable result. Both tools have already been studied by this
assistant; the order is balanced across pairs but there are no independent
subjects or blinded judgments. Warm caches and tool latency are part of the
recorded conditions. A completed unamended study would support these bounded
agent-task observations; it would not establish human productivity or adoption.
Numerical/physical proxies do not substitute for human aesthetic ratings.


## Replay completed implementations

```sh
python scripts/replay-authoring.py --out-dir benchmarks/authoring/.cache/replay-new
```

The replay verifies historical event/report/producer identities and runs every
completed producer through all nine original tasks without creating new clocks.
Historical authoring seconds remain historical values. A partial completed prefix
can pass replay while `study_complete` remains false; it does not finish the
mandatory four episodes. CI retains actual replay outputs alongside preflight
artifacts. This separate postprocessing script changes no frozen acceptance code.


## First-pair original exports

Unmodified actual PNGs; Mavro is observed filter transmittance, NumAcc4 is a
generated numerical challenge. Selected Mavro Matplotlib and NumAcc4 Graph images
were visually inspected; the1e7 offset means the displayed0.2 is10000000.2.

| Case | Matplotlib | GraphUnslopify |
| --- | --- | --- |
| Mavro | ![Mavro Matplotlib](../../benchmarks/authoring/figures/round1-Mavro-matplotlib.png) | ![Mavro GraphUnslopify](../../benchmarks/authoring/figures/round1-Mavro-graphunslopify.png) |
| NumAcc4 | ![NumAcc4 Matplotlib](../../benchmarks/authoring/figures/round1-NumAcc4-matplotlib.png) | ![NumAcc4 GraphUnslopify](../../benchmarks/authoring/figures/round1-NumAcc4-graphunslopify.png) |


## Code footprint and retained original evidence

| Episode | Authored nonblank lines | Median generated lines | Median parameter bytes |
| --- | ---: | ---: | ---: |
| Round1 Matplotlib | 62 | 27 | 365 |
| Round2 Matplotlib | 56 | 23 | 358 |
| Round1 GraphUnslopify | 72 | 823 | 611 |
| Round2 GraphUnslopify | 73 | 825 | 615 |

The Matplotlib payload is plotting configuration; the GraphUnslopify payload is
a semantic FigureSpec. The latter's generated code includes runtime/provenance
work. Each Graph implementation retains its unmodified translator output and
adds only a presentation-coordinate/dataset-tick adapter, preserving every source
row/value and generated mean/sample-SD calculation. Generated lines are output
footprint, not authored effort. Six pinned shared helpers contain1826 nonblank
lines; their prior development/familiarity cost is unmeasured/excluded.

The original42.19s/3171.14s implementation episodes and their invalid paired-time
flag remain in [the earlier study](certified-benchmark.md). This prospective
follow-up does not overwrite/reclassify them or reconstruct an earlier end time.
Human quality/usability/adoption and independent researcher execution remain
unmeasured; volunteer sessions remain user-deferred.

On the original retained local cache, audit/publish with a fresh directory:

```sh
python scripts/publish-authoring-results.py --out-dir benchmarks/authoring/.cache/publication-new
```

Original publication needs the original locally retained output paths. On a new
machine use the replay command after pinned data preparation to generate fresh
scientific outputs; historical agent times remain observations from this run.
`results/runs.csv` is run metadata, not source observations. Raw source data is
not committed or uploaded. Per-dataset numerical errors retain their own units;
no pooled mixed-unit accuracy ranking is inferred.
