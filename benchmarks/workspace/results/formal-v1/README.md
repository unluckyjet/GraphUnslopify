# Public-workflow comparison: formal results

All **436 planned cells** were attempted, completed and retained. GraphUnslopify
does **not** demonstrate a verified-speed advantage on these tasks: its original
exports fail the frozen physical-width requirement. Successful rendering and
native verification do not override that independent task gate.

Both implementations correctly classify the 24 scientific/integrity controls per
arm. This is a project-run comparison on familiar public Penguin and corrected
Iris observations, with a prewritten operational actor. It does not measure human
authoring productivity, independent researcher adoption, blind visual quality or
general natural-language model quality.

## Methods and custody

The [original protocol](../../protocol.json), [protocol-stage README](../../README.md),
37 frozen assets, 37 independent Decimal cases and
[prospective baseline clarification](../../policy-clarification-v2.json) remain
unchanged. The historical protocol-stage wording describes that earlier snapshot;
these files are the completed results. Dataset [attribution](../../../papers/NOTICE.md)
remains in place.

Both complete producers/controllers/evaluator and all 436 untimed preparation
cells were qualified before formal timing. Implementation
[`d9d4b694f54c6f4fd5bb2027090e50c54c0b2cba`](https://github.com/unluckyjet/GraphUnslopify/tree/d9d4b694f54c6f4fd5bb2027090e50c54c0b2cba)
passed all 14 named checks across
[main](https://github.com/unluckyjet/GraphUnslopify/actions/runs/41454996425),
[Figure CI](https://github.com/unluckyjet/GraphUnslopify/actions/runs/41454996404) and
[native preparation](https://github.com/unluckyjet/GraphUnslopify/actions/runs/41454996450).
The actual [qualified seal](implementation-seal.json) was created at
2026-11-02T15:01:51 UTC, before the first clock. Its canonical SHA256 is
`b2b3d5c708e56602925c78f69c43f2714af8396eeb2b952c14b41de65fc8804f`.

The five local tracks ran serially from 15:06:06 to 15:38:52 UTC on November 2,
2026, without concurrent tests, downloads, CI observation, vault work or source
edits on the measurement host. There were no interruptions or replacement
attempts. The subsequent actual
[formal native run](https://github.com/unluckyjet/GraphUnslopify/actions/runs/41473938665)
completed on all four platforms. Every worker retains its formal context, actual
environment, original observations and source/package bindings. All 77 runtime
and 77 SDK files match the sealed source. This is trusted evidence custody,
without authentication against a malicious evidence owner.

## Outcomes

| Track | Retained / planned | Matplotlib + validation, task-correct | GraphUnslopify, task-correct |
| --- | --- | --- | --- |
| Single figures | 192 / 192 | 96 / 96 | 0 / 96 |
| Nine-step paper sessions | 54 / 54 | 24 / 27 | 0 / 27 |
| Reliability controls | 48 / 48 | See classification matrix | See classification matrix |
| Four local environments | 64 / 64 | 32 / 32 | 0 / 32 |
| Four native CI environments | 64 / 64 | 32 / 32 | 0 / 32 |
| Public browser controls | 14 / 14 | Not a baseline browser arm | 0 / 14 |

Every cell completed; no planned cell was omitted or replaced. The three
Matplotlib paper requests without task-correct completion are the deliberately
false-claim steps, not missing observations. Graph width failures remain failures.
None of the 41 task/phase pairs has three verified observations in both arms, so
there is no eligible paired verified-time delta or speed winner.

### What failed

All 96 Graph single-figure requests fail the PNG physical-width gate; all 84
requested SVG and PDF exports also fail their width gates. For example, an
original nominal seven-inch Penguin export is about 6.92 inches after tight
cropping. The independent tolerance remains 0.02 inches. The observed program
and decoded PNG also match the earlier unobserved control: capture did not
introduce this behavior. Nothing was padded, rescaled or given a weaker gate for
the benchmark.

All 14 browser tasks complete their actual public-control interactions, but their
independent task checks retain these width failures. The redundant frozen sex
filter is unavailable through public controls in the first mass-plot task. The
Iris retarget task retains the tool-accepted, wrong-unit intermediate output and
the later visible correction; that intermediate output is never called correct.
No hidden JSON writes substitute for unavailable controls.

### Scientific and integrity controls

Each arm produces the following full confusion matrix. All off-diagonal cells
are zero. Eight clean controls create no scientific false alarms; all 16 seeded
scientific/integrity controls match their expected classification. These familiar,
deliberately seeded cases do not establish general defect-detection superiority.

| Expected / observed | Clean science | Scientific failure | Scientific abstention | Current audit needed |
| --- | ---: | ---: | ---: | ---: |
| Clean science | 8 | 0 | 0 | 0 |
| Scientific failure | 0 | 4 | 0 | 0 |
| Scientific abstention | 0 | 0 | 4 | 0 |
| Current audit needed | 0 | 0 | 0 | 8 |

Physical task correctness is separate. Before fault application, Matplotlib has
16/24 task-correct initial figures; Graph has 0/24 because of physical width.
The remaining baseline initial scientific failures/abstentions are intentional.
The [machine-readable analysis](analysis.json) includes both matrices and all
436 raw cell summaries.

## Timings and real work

[Every paired endpoint median and IQR](timings.md) and the complete
[328-group CSV](timings.csv) preserve all cold and warm tasks. Milliseconds are
reported separately for first current **unverified** PNG, native tool acceptance,
independent task-correct strict acceptance, and terminal completion including
independent checks. Missing verified/image events are unavailable, never zero.
Reuse-only paper updates can finish without a new PNG save event.

There are three sessions per arm/task. Quartiles use linear interpolation at
`(n-1)*p`; this small descriptive sample is not a population estimate. Cold first
requests include startup; warm requests begin at actual parent dispatch. These
are instrumented pipeline times, including evidence checks, not bare `savefig`
or human authoring measurements. The
[30 original startup/handshake/cleanup envelopes](process-envelopes.md) remain
separate. Individual child startup and parent shutdown roundtrip were not
instrumented. Dependency installation and actor authoring are excluded and
unmeasured, not free.

Actual drawing counts are identical across each of the three nine-step sessions:

| Arm | Native figures executed per session | Drawing reuses per session |
| --- | ---: | ---: |
| Matplotlib + validation | 7 | 30 |
| GraphUnslopify | 23 | 14 |

The strong baseline can reuse identical drawings after byte-only data changes or
claim changes while recomputing current science and validation. Its full-match
acceptance reuse is guarded separately. Graph uses the actual documented full
and selective paper APIs, including recovery and membership audits. Neither arm
is forced to follow the other's execution policy. Original saved-figure ancestry,
current evidence and actual execution counts are retained.

## Reproduction

Local profiles cover source Python 3.12.14, minimum Python 3.10.22, the exact fresh
private candidate wheel, and a genuinely SDK-free standalone environment. Native
profiles cover Ubuntu 3.10/3.12, Windows 3.12 and macOS 3.12, with actual worker
versions recorded in [native verification](native-original-verification.json).

All 32 local and 32 native same-environment, same-arm decoded-PNG repeat pairs
reproduce. Both identities must be available. This is not cross-OS or cross-arm
pixel equality. Reproducible Graph images still fail the physical task gate;
reproduction does not establish correctness.

## Recover and inspect every original

The byte-preserving archive contains **13,800 original files**, including all
studies, inputs, actual saves, PNG/SVG/PDF exports, programs, contexts, reports,
logs, native ZIPs and processing metadata. Identical bytes are stored once.
The 153,371,999-byte archive is split into four repository files at most 40 MiB
each, with [part and whole-archive hashes](evidence/parts.json).
Whole-archive SHA256:
`05e779be536a266bbfa1519f0958130a61c91e51cc745dcc3c40833cfa15b0a3`.

From the delivery checkout, restore to a **new** directory:

```sh
python benchmarks/workspace/results/formal-v1/restore-evidence.py \
  --parts benchmarks/workspace/results/formal-v1/evidence/parts.json \
  --out ../workspace-formal-evidence
```

The restorer verifies each part, the combined archive, every object/member and
restored bytes. It executes no archived code. The original measured records keep
their original paths and bytes. `portable-inputs.json` locates their restored
directories without editing those records. Actual round-trip verification
restored all 13,800 files; the portable reader reproduced all statistics under
Python 3.10 after normalizing only evidence-location strings.

Analysis requires a separate checkout at the **measured D9 revision**, with its
Python dependencies. Pass that path explicitly; a later delivery commit is not
the sealed implementation revision:

```sh
python benchmarks/workspace/results/formal-v1/read-results.py \
  --repo /path/to/checkout-at-d9d4b694f54c6f4fd5bb2027090e50c54c0b2cba \
  --inputs ../workspace-formal-evidence/portable-inputs.json \
  --mode formal \
  --seal benchmarks/workspace/results/formal-v1/implementation-seal.json \
  --out ../recomputed-analysis.json
```

The parameterized reader preserves the original pre-clock analysis method. Its
output also exactly matches the original analysis when given the original
locations. It verifies full inventories, fixed plans, all retained cells and
formal receipts before reporting. Original observer/evaluator results remain
with the timed files; no new rendering is presented as an original timed output.

## Limits and delivery

The [complete 78–89 delivery audit](../../../../docs/workspace/workspace-delivery-audit.md)
maps accepted capabilities to source, actual controls and remaining limitations.
The public PyPI 0.8.0 release remains older and immutable; the private candidate
and measured source are distinct. No new release/tag was authorized or created.
The original NIST lineage and four-episode familiarized-agent creation study
remain historical, without merged clocks or relabeling as independent research.
Outside researcher feedback, blind ratings, adoption and general model-quality
evaluation remain user-deferred and unmeasured.
