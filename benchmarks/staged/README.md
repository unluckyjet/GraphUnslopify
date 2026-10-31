# Staged preview progress and verification

85a numerical reuse/bbcef49,85b1 backend/45b4431 and85b2a editor/1d66224
are accepted by exact all-nine/Figure CI. The actual editor displays current
unverified images and preserves the original strict final response. The frozen
browser comparison is under final measurement/acceptance. Public0.8.0 predates
these source changes; no release is published here.

## Backend boundary

An optional unique32-hex stage_id on the existing authenticated /api/render POST
asks for progress. That same original canonical script still runs once with its
original strict policy, math, output order, checks and final response. Its actual
PNG is copied after the existing save/geometry capture; there is no extra draw or
substitute verifier. Unsupported progress does not stop the final strict run.

Authenticated GET /stage/TICKET?client=CLIENT&generation=N waits at most0.2s and
returns pending, unverified, unavailable or stale with verified:false. An available
reply contains the server attempt ID, original input/script/PNG identities and
image bounds. GET /stage/TICKET/png with the same client/generation and attempt
query requires that exact current attempt. Existing X-Preview-Token or image URL
token authorization and origin/host guards apply. These routes provide an image,
with no report, final files, edit/diagnostic maps or scientific acceptance.

Current attempts supersede earlier ones even within the same generation. The
registry bounds metadata to64 records/128 client identities; each copied PNG is
limited to16MiB. These are not total process RSS/disk limits. Existing session
run folders and temporary-root cleanup retain ownership. Sidecar copies stay out
of final allowlisted outputs and bundles. Parent checks actual PNG bytes,
dimensions, embedded provenance, script and original input binding; damage or
wrong ownership cannot provide a current image.

Correctness tests use a controlled driver that holds immediately before the
**genuine** checker, then releases and invokes it unchanged. These prove early
unverified availability and actual strict0/strict2, not measured speed. Other
controls cover damaged metadata/bytes, two same-generation attempts, independent
clients, current source/PID/mode and joined in-flight shutdown.

## Prospective browser comparison

[Literal staged-preview-v1 protocol](protocol.json) SHA
cea35240ac9567bb2df5a93c1f074c645991fe0b78ada431b3cb98e6ca74d53d was
frozen after exact bbcef49 acceptance and before staged implementation/timing.
It keeps all35 original numerical-cache intents/five data hashes and adds a
separate seven-intent PNG-only control. Both arms keep actual warm native/
compiler/numerical workers and16/64 request limits. Formal612 records preserve
510 clean0/102 original false-claim2; smoke108 preserves90/18.

Primary browser Render-click clocks separate first current decoded/mounted image
from the final strict-result DOM. Original negatives get final-failure latency,
never a fictitious verified time. Setup/upload/startup, first-font and instrumented
calls are separate. Preserve actual UI validation and render conversions, bounded
worker recycling, copy/hash/poll/decode overhead, original formats and current
final reports/maps. Per-edit seven ordinary medians/p90s retain failed/partial/
negative/slower and no-early-provisional observations. No artificial timing delay
or pooling changed outputs. PNG-only benefit may be absent.

## Accepted backend and editor evidence

The backend passes seven232/1904/Ruff151 on411 unchanged files; source/minimum/
fresh21-kind30-pair/60-render conformance, source old101 GUI, minimum/fresh103
controls and59 whole installed package files pass. Backend45b4431 exact CI is
accepted. [Backend records](results/backend-v1/verification.json) retain retries
and precise scopes.

The staged editor passes seven232/1904/zero skips/one upstream warning/Ruff152
on419 unchanged files, source/fresh107 browser workflows and minimum6 genuine
checker workflows. Source observes91 base native/compiler replies; fresh and CI
observe90, each with seven additional separately controlled replies. CI's actual
97 native replies match all40 signed Python/bundle Git blobs. The full60 package
members match source in the local installation and all four actual CI wheels.

Exact1d66224 main41178079380 all-nine/Figure41178079403 final metadata/ten
named checks passed2026-10-31 07:19:52UTC. Both original v4/45 and numerical/90
smokes preserve strict negatives/protocols and clean-source12/13 actual assets;
all72 original NIST outcomes/nine datasets also pass. [Editor records](results/editor-v1/verification.json),
[exact acceptance](results/editor-v1/ci-acceptance.json),
[actual CI browser](results/editor-v1/ci-editor.json),
[four complete wheels](results/editor-v1/ci-four-wheel-bindings.json).

## Run the actual frozen browser comparison

From the repository with its Node dependencies, Playwright Chromium (or the
installed macOS Chrome) and the scientific Python environment:

```sh
PYTHON=python npm run benchmark:staged -- --smoke --out-dir /tmp/my-staged-smoke
PYTHON=python npm run benchmark:staged -- --out-dir /tmp/my-staged-formal
```

Use a new output directory. Smoke retains all108 records; the default runs all612.
Both use the literal42 intents and six cases. A new real server/context and fresh
font directory per arm/case retain setup, first-font and last instrumented calls
separately. The original genuine checks are never delayed in this runner.

The click is captured in the actual document. Current image decoding and final
strict DOM/export state have separate timestamps. Source/minimum/fresh package
and dependency roots are explicit. Python proof inspection/hashing/copying happens
through stdin **after** browser clocks stop. Ordinary/negative/partial/failed and
no-provisional observations remain in raw records with per-metric denominators.
The first available image can be final; a missing early preview is not replaced
with an invented earlier timestamp. Final-failure time is separate from verified
time. No hit-rate or speed threshold is used.

All actual compiler operations are retained, including validation outside the
click during intent setup. Recycling that occurs there is included in the
separate intent-setup cost; recycling during the click is included in that clock.
The complete64/16 request epochs are validated from actual worker traces, not
inferred from a fixed number of processes. PNG/script/science/table/map signatures
must match across arms and repeated exact variants. Current ephemeral run IDs are
validated before removal for cross-run map comparison.

## Measured result and remaining acceptance

The corrected v3 source formal run passes **612/612**:510 clean outcomes and102
original strict failures, with433 source/test/fixture files unchanged. A separate
publishing utility rechecks all612 raw proof records and42 signatures. Each
exact edit has seven ordinary median/p90 samples; first-image medians are earlier
in42/42 variants, while final-result medians are slower in31/42 and faster in11/42.
Those are counts of separate comparisons, not pooled latency estimates.

For the same title-b edit in the dense median/bootstrap case, first-image medians
are406.2ms final-only/289.1ms staged; final-result medians are406.2/415.1ms. The
[complete report](results/staged-preview-v1/comparison.md) retains all42 exact
variants, final costs, p90s and original negatives. No general human productivity
or speed conclusion follows from this single-host engineering workload.

Source, minimum Python3.10 and the actual fresh installed wheel each pass the full
108 smoke/90 clean/18 strict-negative outcomes. Minimum/fresh run after the
exclusive source formal measurement, concurrently only with each other; their
secondary timings are not pooled. All current decoded provisional PNGs match final
bytes, current maps/exports bind, actual dependency/package roots match, and owned
workers/root close. Formal sessions retain four actual native and three compiler
epochs with original16/64 limits. Source formal/minimum/fresh433-file guards pass.

[Raw results](results/staged-preview-v1/results.json),
[all raw proof/reference/driver evidence](results/staged-preview-v1/raw-evidence.zip),
[archive integrity binding](results/staged-preview-v1/raw-evidence-binding.json),
[source guard](results/staged-preview-v1/source-receipt.json),
[all612 proof digests](results/staged-preview-v1/raw-proof-manifest.json).
Raw metadata preserves original absolute environment paths; ZIP members provide
portable relative proof/reference paths. Regenerate with the commands above in a
new output directory rather than depending on a former temporary environment.

Initial v1/v2 smoke108 and an initial formal612 all preserve original conformance,
but a test-only observer digest overlapped the live clock. Their exact original
drivers/data are preserved separately in the shared Obsidian project archive
(SHA c7ebaf0b94137b44472ae7f7d927a767766f529167b3d16687dd5b75339a1b74).
The corrected v3 defers all independent response-body retrieval/JSON/digest work
until clocks stop, then repeats the entire612. The earlier result is not selected
as final timing evidence. Literal staged/NIST/numerical/v4 protocols remain intact.

Current local measurement/audit and seven232/1904/Ruff153 checks on446 unchanged
files pass. Push/exact CI are under acceptance. Full85 stays open until that checkpoint is accepted.86–89
retain their full scope. [Acceptance audit](../../docs/workspace/staged-preview-acceptance.md),
[specification](../../pipeline/done/85-incremental-staged-preview.md), shared
Obsidian Staged Preview Lifecycle note.
