# Ask a reviewer question about saved figure checks

The current-source reviewer API and CLI combine an initialized paper project's
actual saved checks with separately labelled model advice. Ask “What would a
skeptical reviewer criticize about these figures?” or supply a specific question
and study context. Select up to 20 actual figure keys, including PDF evidence.
The paper workspace and single-figure editor expose session-only reviewer HTTP controls. Visible
paper/editor browser controls remain in development; this core does not complete idea4.
These features are newer than the published PyPI0.8.0 package.

The result has two separate parts:

- `deterministic_evidence` retains the selected claims, declared uncertainty,
  recorded counts and actual inspection findings. Current, historical, failed,
  unavailable and visual-only states remain explicit.
- `qualitative` contains **unverified model suggestions requiring author review**,
  linked to supplied evidence IDs. Valid references prove that an ID exists;
  they do not prove that the model interpreted it correctly.

`status: completed` means the query completed. It does not mean the science
passed. Failed native claims remain failed even if a model's prose disagrees.
No settings are applied and no figures are executed by the reviewer itself.
PDF numerical claims stay untested. No figure images are sent, so the model
cannot inspect their appearance; it can discuss recorded inspection metadata.

## CLI

Initialize and run your paper project's native checks first, or deliberately
review its explicit missing/historical evidence. See [paper projects](../project-management.md).
Configure/start a compatible model provider separately; the tool does not start
a model server or download weights. HTTPS and HTTP loopback endpoints are
supported using Responses or Chat Completions JSON protocols.
By default the request includes a structural JSON Schema to constrain figure keys,
evidence IDs and response fields. Use `--json-mode` at planning time (Python
`structured_output=False`) only when your configured provider lacks schema
support. There is no automatic fallback or second model request; both modes
still use the full local response validator.

```sh
graphunslopify review-agent-plan paper/ \
  --endpoint http://127.0.0.1:11434/v1/chat/completions \
  --protocol chat --model YOUR_INSTALLED_MODEL \
  --question "What would a skeptical reviewer criticize about these figures?" \
  --out reviewer-request.json
```

This creates a new JSON disclosure and makes **zero model calls**. Inspect the
provider destination, complete `disclosure.request`, selected evidence and
question. Repeat `--figure FIGURE_KEY` to select figures; omitted means all
actual collection members, subject to the 20-figure limit. `--event EVENT_ID`
explicitly selects historical evidence. `--author-context TEXT` supplies context
without establishing that it is true.

After review, copy `disclosure.consent_sha256` into the explicit request:

```sh
graphunslopify review-agent-run reviewer-request.json --path paper/ \
  --consent --consent-sha256 "PASTE_CONSENT_SHA256" \
  --out reviewer-result.json
```

An optional API key comes from `GRAPHUNSLOPIFY_DRAFT_API_KEY`; it is an
authorization header and is omitted from saved disclosures/results. Do not put
keys in endpoint URLs, questions or author context. Output files must be new.
Both commands print JSON; errors exit2. A successful query exits0 even when
the unchanged deterministic evidence contains a failed scientific check.

## Python

```python
from graphunslopify.drafts import DraftProvider
from graphunslopify.review_agent import FigureReviewPlan

plan = FigureReviewPlan(
    DraftProvider("http://127.0.0.1:11434/v1/chat/completions",
                  "YOUR_INSTALLED_MODEL", "chat"),
    "paper/",
    figures=["training"],
    question="Which uncertainty assumptions need clarification?",
)
disclosure = plan.disclosure()  # inspect destination and exact payload first
# Explicitly opt in only after the disclosure has been reviewed:
result = plan.request(consent=True,
                      consent_sha256=disclosure["consent_sha256"])
```

`review_document`, `write_document`, `read_document` and `restore_plan` support
saved requests. Restoring recollects actual project evidence and reproduces the
entire disclosure; it never trusts edited saved findings as current evidence.
Fingerprints detect changes; they do not authenticate an author or replace consent.
One plan permits one consented attempt. A later explicit CLI invocation creates
a new plan; provider failures do not trigger automatic retries.

## What is sent and checked

The exact disclosure shows saved claim results, uncertainty/count evidence,
inspection metadata, selected figure IDs, your question and author context.
An explicit `recorded_failures` list repeats actual failed claims/error findings
before optional advice; it does not depend on the model noticing them.
Dataset files, images and executable scripts are not attached. Reproduction file
bindings and complete local environment inventories are omitted. Saved labels,
findings and PDF metadata may contain author wording or filenames; inspect the
request before sending potentially private content to a provider.

Consent binds both provider destination and request/evidence bytes. Changing an
endpoint cannot reuse a digest for the old destination. Actual evidence is
recollected before sending and after the provider returns. Changed data, specs,
exports, runtime sources, environment or history refuse a stale result. Results
record that evidence was unchanged during the request; they do not promise that
the evidence remains current after later edits.

Requests are bounded to1MiB, saved documents4MiB and provider replies1MiB.
Each consented provider call runs in an owned worker with a90s execution deadline,
covering connection, headers, continued body reads and provider-response parsing.
The worker is stopped and reaped before returning a timeout or cancellation;
OS process creation and up to5s of process cleanup add overhead. Credentials and
request bytes pass through stdin, never process arguments or temporary files.
Endpoint settings are limited to8192 characters and optional keys to16384.

Python callers may pass a `threading.Event` as `cancelled=` to `plan.request()`;
set it to discard a pending reply and stop the local provider worker. An already
transmitted request may still be processed remotely. Cancellation consumes the
plan's one attempt, so a retry needs a newly disclosed request and consent.
This API support does not yet provide an editor cancellation interface.
Oversized evidence refuses instead of silently dropping findings. Suggestions
are capped at20, with bounded wording and known figure/evidence references.
Unknown fields, scientific patches, missing citations, malformed/duplicate-key
JSON, nonfinite numbers and incomplete/refused/tool-call replies fail explicitly.
No markup or model code is executed. `InvalidReview.reply` exposes unaccepted
provider text to an explicit diagnostic; it is never accepted advice.

## Paper workspace HTTP sessions

The local `project-preview` server exposes the following token-protected routes.
They use the existing workspace Host/Origin checks and `X-Preview-Token` header.
These are integration APIs; visible browser reviewer controls are still pending.

| Route | Purpose |
| --- | --- |
| `GET /api/reviewer/provider` | Read public provider configuration and whether authorization is configured; the key is never returned. |
| `POST /api/reviewer/provider` | Configure `endpoint`, `model`, `protocol` and optional `api_key`; `{"enabled": false}` clears configuration and cancels prior work. |
| `POST /api/reviewer/disclose` | Collect actual selected evidence and return the exact request/destination and consent digest without making a provider call. |
| `POST /api/reviewer/start` | Explicitly consent to that disclosure; return `202` while one owned inference runs. |
| `POST /api/reviewer/status` | Read its phase and separately labelled result; completed evidence is checked again before it is returned. |
| `POST /api/reviewer/cancel` | Cancel a request or that client's current reviewer context and discard pending advice. |
| `POST /api/reviewer/download` | Download the disclosed request or completed result as JSON after checking freshness again. |

First load `GET /api/review`, optionally with `?event=EVENT_ID` for historical
evidence. Send its `evidence_revision` as `expected_revision`, plus `client`
(a nonsecret session identifier), integer `generation`, `figures` (actual keys),
`question`, optional `event`, `author_context` and `structured_output` to
`/api/reviewer/disclose`. The server recollects the project; a client-supplied
report is refused. An active paper job, changed ownership or changed collection
revision refuses the request.

Subsequent controls use that `client`, `generation` and returned `review_id`.
Start also requires `consent: true` and the exact disclosed `consent_sha256`.
Downloads require `which: "request"` or `which: "result"`. A request download
is the same replayable document accepted by `review-agent-run`; its secret key
must be supplied separately. No result download is available for a failed,
cancelled, incomplete or stale request.

Increment the generation when selection, question, context or other reviewer
inputs change. Older generations cannot cancel newer work. Cancellation without
a `review_id` also invalidates in-progress disclosure preparation. Changing the
provider invalidates all existing disclosures; each plan permits one attempt.
Phases are `disclosed`, `running`, `completed`, `failed`, `cancelled` or `stale`.
Failure clears prior advice; invalid provider reply text is not exported by these
session routes. Cancellation/shutdown joins the owned local inference worker;
it cannot unsend a request already received by a remote provider.

Provider credentials live only in this server session. Controls are limited to
64KiB, retained disclosures expire after ten minutes, and at most eight plans
including preparations and 64 client-generation records are retained. One
inference runs at a time. These bounds do not replace the request/reply limits
or scientific caveats above.

## Single-figure editor HTTP sessions

The local `preview` server uses the same provider, disclosure, start, status,
cancel and download routes and authorization rules above. First obtain a final
`/api/render` response with `review.available: true`. Provisional images are not
review evidence. Send its `run_id`, the original renderer's `client` as
`render_client`, and its `generation` as `render_generation` to
`POST /api/reviewer/collection`. This returns the actual single `figure` key and
an `evidence_revision`.

Disclose using those three render fields, `expected_revision` from the collection,
`figures: ["figure"]`, the question/context options, and a separate reviewer
`client`/`generation`. Changing a reviewer question does not require rerendering
an unchanged figure. A newer rendering attempt, including a same-generation
retry that fails translation, retires the prior render's review context.

The server records full local SHA256 hashes of the original uploads and run
inputs before/after execution, the prepared specification, generated program,
actual renderer exit, saved report/specification, exports and source identity.
The report's data fingerprint is a 16-hex-character producer prefix; it is not
a full SHA256. For palette locks, the native parser observes the same actual
byte snapshot it parses. Normal allocation may extend the owned run copy; the
original upload, observed input hash and final copy remain separately bound.
If the figure does not read a supplied palette, a recorded empty read list is
allowed only when that run copy stayed unchanged; no read is invented.
Later input/palette/program/report/export changes refuse before sending or
returning advice. Recollection also checks runtime/environment evidence.

Failed claims and incomplete native executions retain their actual report and
strict exit status; a completed model response never changes them. Missing
exports stay missing. Evidence that cannot be bound is explicitly unavailable.
An editor render is ephemeral: `matches_latest_accepted_inputs` stays false,
and its public workspace identity is separate from the HTTP authorization token.

Editor request downloads have kind `editor-figure-review-request` and
`replayable: false`. They preserve the disclosure for inspection, but cannot be
restored using the saved-paper `review-agent-run` command. Result downloads keep
the same separation of checked evidence and unverified suggestions.

Shutdown first cancels/joins reviewer work, then waits for active HTTP render
handlers, closes native rendering/compiler tools, and finally removes the owned
temporary directory. If an owner cannot stop, its directory is retained even
if the server object is collected; a later successful close can clean it.

## Verification

`python/tests/test_review_agent.py` uses actual saved native positive/failed
claims, historical/unrun/damaged evidence, PDF inspections, source/export races,
request privacy and real loopback HTTP contracts on both protocols. These
controlled providers are transport/behavior tests, not actual inference.

`python/tests/test_review_sessions.py` adds real paper-server HTTP consent and
download checks, exact provider-body comparison, active/source/history guards,
provider failure/privacy, in-flight cancellation, shutdown, disclosure races and
bounded preparation. Browser usability and actual configured inference through
the forthcoming controls require their own evidence.

`scripts/check-review-agent.py --out-dir NEW_DIRECTORY` creates and audits two
figures from the repository's public Palmer penguins CSV, reverses a declared
comparison to produce a real failed claim, and checks disclosure, API/CLI consent,
source refusal, unchanged project bytes and installed package/source bindings.
CI retains this evidence separately for Python3.10 and3.12.

To make one actual consented model call on that public evidence, explicitly add
`--endpoint URL --model MODEL --protocol chat` (or `responses`). No model is
downloaded or called by ordinary CI. Actual inference outcomes, including
rejected replies, must be retained separately from controlled-provider tests.
Neither route establishes independent scientific judgment, general model
quality, researcher productivity or adoption.

Actual small-model trials also demonstrated this limit: one reply invented an
evidence ID and was rejected; a later schema-valid reply suggested changing
intervals to overlap. That suggestion is scientifically inappropriate and was
never applied. Keep the recorded quantities/checks authoritative and review the
advice rather than treating valid JSON or citations as scientific acceptance.

Wire formats follow the official [Responses/Chat structured-output format](https://developers.openai.com/api/docs/guides/structured-outputs)
and [Ollama's local structured-output support](https://github.com/ollama/ollama/blob/main/docs/capabilities/structured-outputs.mdx).
The provider schema uses structural types/required fields/enums; stricter size,
nonempty text and uniqueness bounds are also enforced locally. Provider support
is configuration-specific; no live OpenAI-account call is claimed.
