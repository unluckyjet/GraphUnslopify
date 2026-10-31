# Staged preview progress and verification

The85b1 backend is accepted at45b4431 with exact all-nine/Figure CI. The working
editor now shows current unverified images under acceptance; the prospective
browser comparison is unfinished.85a numerical reuse is accepted at bbcef49. Public0.8.0 remains
unchanged; no release is published here.

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

All seven local checks pass232 Node/1904 Python/zero skips/one upstream warning,
Ruff151 and411 unchanged source/test/fixture files. Source/minimum/fresh native
checks each pass30 pairs/60 renders/all21 kinds with13 actual assets; source
final-only GUI regression passes101 workflows/91 replies per worker. Fresh103
controls and all59 wheel package files match/test outside the checkout. Minimum
103 distinct controls pass after two fixture-only title errors were corrected.
[Local acceptance records](results/backend-v1/verification.json) retain attempts
and actual scopes. New push/exact main/Figure CI remains required. Source staged GUI passes107 workflows, with six genuine-check-held cases also
passing on minimum Python. Fresh107 GUI and all60 package files pass, along with seven stable checks
232/1904/Ruff152 on419 unchanged files. Push/exact UI CI remains pending;
formal612/108 is unmeasured. Full85 and all86–89 scope stay open. See the [full specification](../../pipeline/specs/85-incremental-staged-preview.md) and the shared Obsidian Staged Preview Lifecycle note.


Actual staged-editor correctness records: [editor-v1](results/editor-v1/verification.json).
The source browser observes91 base native/compiler replies; the fresh browser
observes90. Each separately controls seven additional actual native replies
across six workflows. Minimum Python also passes those six/seven controls.
Counts and original strict failures are retained; no timing result is inferred.
