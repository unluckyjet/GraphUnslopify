# Bounded local translator transport

The current source adds a private compiler service and client. This transport
foundation preserves the public one-shot API. The editor continues to use its
existing translation path until a separate integration milestone is verified.
No new rendering-speed or human-productivity claim follows from this component.

`src/local-worker.ts`, bundled through `src/local.ts`, serves framed JSON over an
owned stdin/stdout pair. It calls the canonical dispatcher without reading any
dataset. Application validation errors retain their original responses. Invalid
UTF-8/JSON/envelopes, oversized or unterminated frames fail closed. Requests are
bounded to4MiB, responses16MiB and a process to64 requests by default (1–128 allowed).
The existing default stdin-to-EOF single-request mode is preserved.

`python/graphunslopify/translator_worker.py` owns the actual bundled Node binary,
including its Windows executable layout; it preserves an explicit actual-node
executable override. Its shared JsonWorker binds readiness to the actual PID,
request UUID, loaded bundle SHA256 and matching declared limits. The client checks
source/runtime selection before and after requests, returns a trace with each
specific response, restarts on environment changes/crashes/timeouts, recycles its
bounded process and closes its owned resources. It requires editor restart when
loaded source/runtime selection changes. This private API is not a network service
or an arbitrary-code sandbox.

Run `python -m pytest python/tests/test_translator_worker.py python/tests/test_preview_worker.py -q`
with the scientific interpreter. Compiler tests compare actual one-shot results
across21 conversion kinds and mixed schema/recipe/score/repair/suggestion calls;
conversion alone does not render or verify observations. Other controls cover
invalid-to-clean recovery, reserved names, concurrency, bounded frames, startup
and source/runtime refusal, process recycling and collection/close.

`scripts/install-smoke.py --require-translator-worker` requires actual same-PID
conversion, current response identity/source, max2 recycling and shutdown outside
the checkout with networking blocked after installation. The distribution matrix
requires it on all four supported platform/interpreter combinations. Older public
wheels omit this flag. New exact CI is required before editor integration.

The [rendering protocol/history](../../benchmarks/rendering/README.md) preserves
all earlier scientific gates, raw comparisons and failed outcomes. Full84,
including integrated compiler/native measurement, and85–89 remain open. Public
PyPI0.8.0 predates these source changes; no release is published by this milestone.


Local acceptance:16 compiler plus24 native controls pass in each actual source,
minimum and genuine fresh installed context (40 each). All seven gates pass232
Node/1856 Python, zero skips/one existing upstream warning, full Ruff144 on309
unchanged source/test/fixture files. [Verification](../../benchmarks/rendering/results/translator-worker-foundation/verification.json)
and the actual installed trace retain this evidence. New exact all-nine/Figure
CI, including Windows direct-Node ownership, is required before editor integration.
