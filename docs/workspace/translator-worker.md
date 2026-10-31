# Owned compiler and renderer sessions

The local editor now owns a bounded translator and native renderer per session.
`PreviewServer` enables both by default; direct `PreviewState` retains explicit
reference defaults through `reuse_translator=False` and `reuse_renderer=False`.
Public one-shot translation and standalone generated Python remain unchanged.

The editor routes info/recipes/schema/suggestions/conversion/fix through its
compiler. Model draft plans receive the same explicit request function for
input-schema and canonical validation; other consumers retain their defaults.
The `/api/validate` route deliberately retains its existing `convert` operation.
Provider disclosure, consent, reviewed application and strict native checks remain.
Each render's `translation_execution` belongs to that specific compiler call;
`execution` belongs to its native render. Shutdown joins requests, closes both
workers and removes session files. Native teardown failure still closes Node.

`src/local-worker.ts`, bundled through `src/local.ts`, serves bounded newline JSON
and calls the canonical dispatcher without reading datasets. Application errors
retain their original responses. Invalid UTF-8/JSON/envelopes, oversized or
unterminated frames fail closed. Requests are4MiB, responses16MiB; a process
handles64 requests by default (1–128 allowed). Default stdin-to-EOF mode remains.

`python/graphunslopify/translator_worker.py` owns the actual Node binary, including
its Windows layout and explicit executable override. Startup binds actual PID,
request UUID, bundle SHA256 and limits. Pre/post source/runtime checks, deadlines,
environment-change/crash recovery, recycling and terminal close use the shared
private JsonWorker. Changed loaded source/runtime requires editor restart. This
is a canonical local transport, not an arbitrary-code sandbox or network service.

Foundation e525808 passed exact main41158916220 all nine/Figure41158916126 before
integration. Local integrated controls and full acceptance are tracked in
[84](../../pipeline/done/84-measured-rendering-overhead.md). Run scientific Python
pytest on test_preview_translator.py, test_preview_drafts.py,
test_translator_worker.py and test_preview_worker.py for lifecycle, consent,
concurrency/current traces, strict negatives, framing and source controls.

`scripts/install-smoke.py --require-render-worker --require-translator-worker`
requires actual installed HTTP editor reuse and closure of both processes, plus
the independent compiler max2-recycling/canonical-response gate. The four-platform
CI matrix requires these flags. Older public wheels omit these private gates.
The browser driver records actual compiler/native replies; selected control kinds
are distinct from the dedicated helper's actual21-kind native renders.

The [literal v4 protocol/method](../../benchmarks/rendering/README.md) adds a
three-arm comparison while retaining v3's worker meaning. Constructor/setup,
first-font request, ordinary warm samples and instrumentation are kept separate.
All original inputs, failed outcomes and strict scientific gates remain. Current
integration is under acceptance; full84 and85–89 remain open. Public PyPI0.8.0 at
c3e0619 predates these source changes; this milestone publishes no release.
