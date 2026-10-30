# Model drafts in the local editor (current source)

Current source connects model proposals to the local editor. PyPI0.8.0 predates
this work; use a current source installation. Production6275b8c passed all nine main CI jobs and Figure CI. The final
acceptance/queue checkpoint has its own CI before work advances to83.

## Use it

1. Select your actual dataset or worksheet and open **Ask for a figure draft**
   beneath the central figure. Manual authoring remains available without a model.
2. Open **Model provider**, enter its protocol, full API endpoint and model ID,
   and save. An optional key stays in this server session; the input is cleared.
   Saving again replaces authorization, so re-enter the key if needed. Empty means
   no key. Saving configuration does not transmit a figure request.
3. Describe the figure. Under **Author context**, explicitly declare any required
   measurement units, sampling design and experimental-unit column. Column names
   and row counts cannot establish experimental independence.
4. Choose **Review model request**. Check the selected file/worksheet, provider,
   metadata summary and exact request JSON. Only explicit consent followed by
   **Send reviewed request** contacts the model. Each disclosure has one attempt.
5. Review the unapplied, unverified source choices, assumptions, questions, wording
   and full canonical specification. Invalid output is quarantined; provider
   failure never applies a fallback template.
6. Confirm review and choose **Apply draft and verify**. This shares the existing
   undo history and forces a strict rerender even with live preview disabled.
   Exports belong to the current rendered intent. Save wanted files before ending
   this temporary session.

For a local compatible server, choose Chat Completions and use its full endpoint,
for example `http://127.0.0.1:11434/v1/chat/completions`. For the OpenAI Responses
protocol the endpoint is `https://api.openai.com/v1/responses`; supply a model and
authorization accepted by your account. Live OpenAI account inference is untested.
The source/fresh-installed actual-model evidence uses local Ollama0.40.13 and
Qwen2.5:3b, with no keys or private observations in the recorded examples.

Changes to data, canonical intent, provider or draft context invalidate old
disclosures/proposals. A late response cannot restore an older figure or its
exports. Provider changes never silently reuse a saved key for another endpoint.
The session bounds pending records, expires them after ten minutes, and permits
one model request at a time. Cancellation prevents acceptance of stale results;
it cannot unsend a request already transmitted with consent.

## Boundary

`python/graphunslopify/drafts.py` accepts a configured provider and the selected
immutable upload plus specification prepared by `PreviewState.prepare`. It builds
a reviewable request without calling the provider. `disclosure()` returns the
exact JSON body, provider/model/protocol, byte count and request hash; the API key
is excluded. Only `propose(consent=True)` sends it. A disclosed request gets one
attempt; failures require preparing another request, with no automatic retries.

The context contains real column names/types and present/missing/finite counts,
row count, current intent, author-declared units/design and all21 kinds' canonical
input schemas. It does not automatically add raw observations, category samples,
numeric summaries, source paths, output filenames or palette filenames. Existing
wording/claims may themselves contain sensitive information, so the entire body
must be reviewed. Provider keys use an authorization header and stay out of
disclosures/results. HTTPS or loopback HTTP is required; redirects are refused
without replaying the body or credentials, and provider error bodies are not
echoed to the user.

The model returns an untrusted JSON object containing `patch`, `assumptions` and
`questions`. JSON mode is a syntax aid, **not schema or scientific acceptance**.
Duplicate keys, nonfinite numbers, oversized responses, refusals, incomplete
responses and tool calls are rejected. Patches cannot change owned input/palette
paths or output filenames. Unknown properties are refused rather than silently
discarded by the compiler. The canonical input schema and static compiler must
both accept the candidate. Original claims remain as an unchanged prefix.

New units require author declaration or existing source-field units. New CI/SEM,
experimental-unit summaries, significance tests and paired differences require
matching author context; guessed column roles are not declarations. New scaling
fit intervals, notched boxes and Kaplan–Meier intervals require declared
independent rows because these implementations do not supply clustered/paired
intervals. Declarations are author assertions, not evidence of independence.

A result remains `applied:false, verified:false`. The caller must review it,
explicitly apply it and rerender strictly. Numerical checks do not certify prose,
model assumptions or whether the model followed the natural-language request.
Invalid schema output is quarantined with error paths for explicit review; it is
never automatically repaired into an accepted proposal.

## Schema input and prompt size

`src/local.ts` now exposes `input-schema` alongside the unchanged `schema`
operation. The latter describes compiler output and requires populated defaults;
using it directly would reject valid minimal input. Draft validation uses input
semantics with unknown object properties refused.

`compact_schema` shares identical schema nodes using draft-7 definitions. It
leaves property maps and default/example values intact. Tests expand every new
reference and compare the complete result with the original schema, exercise
all25 recipes and retain all21 branches. The packed schema is less than one
quarter of the original encoded size; this reduces request size, not measured
authoring time or scientific error rates.

## Explicit inference verification

The initial82a records below are historical snapshots at90022f2. The current
browser integration has its own source/fresh-installed records linked afterward.

Ordinary CI uses real local HTTP doubles for protocol, privacy and failure tests;
those tests do not establish real inference. To test an actual configured model:

```sh
python scripts/model-draft-smoke.py \
  --endpoint http://127.0.0.1:11582/v1/chat/completions \
  --protocol chat --model qwen2.5:3b \
  --output /tmp/graphunslopify-model-proof
```

Run this explicitly with a compatible model server already running. The harness
generates public synthetic data, discloses the request, calls the actual provider,
checks the requested source mapping/title, then explicitly renders and checks
strict PNG/SVG/PDF exports and unchanged source bytes. Its optional API key comes
from `GRAPHUNSLOPIFY_DRAFT_API_KEY`, never a command-line argument. It saves
disclosure, proposal or quarantined output, checks and a strict report when one
is produced. It does not download models or run during ordinary CI.

Early local Qwen3:0.6b trials included an invalid embedded JSON string, an invalid
schema and a valid specification with the wrong requested axes. These failures
were blocked before rendering; see [all six exploratory source calls](model-drafts/exploratory-source-trials.json). Such exploratory
trials are not a preregistered model-quality evaluation or evidence of usability,
adoption or authoring-speed gains. No OpenAI account connection is assumed.

The protocol implementations follow [OpenAI JSON-mode documentation](https://developers.openai.com/api/docs/guides/structured-outputs)
and [Ollama's compatibility documentation](https://docs.ollama.com/api/openai-compatibility).
Provider compatibility still needs testing against the actual configured service.

On actual macOS27 ARM64/Python3.12.14 with Ollama0.40.13, the sixth exploratory
call (Qwen2.5:3b, separate context and final task messages) selected epoch/score
and the requested title correctly. Explicit strict rendering passed with all
three exports and unchanged input bytes. [Strict report](model-drafts/source-strict-report.json).
The preceding five failures remain in the same trial record; this is debugging
evidence across changed formats/prompts, not a comparative model-quality sample.

The same actual model task also passed from a fresh wheel installation with
Python/Node external networking denied (loopback inference allowed). The installed
backend and translator bytes match source; request hash matches the final source
call. [Installed proof](model-drafts/fresh-installed-proof.json). The local
compatible-server path is measured; live OpenAI account inference is untested.

All seven required gates passed on stable product hashes:234 Node/1550 Python
(no skips; one existing upstream MLflow/SQLAlchemy warning).39 provider-contract
cases also pass on actual Python3.10.22 and3.12.14.
[Backend verification and hashes](model-drafts/backend-verification.json).

## Current browser integration evidence (82b)

Both [source](model-drafts/source-browser-checks.json) and
[fresh-installed](model-drafts/installed-browser-checks.json) Chrome pass65
workflows including all21 native kind controls and12 model-flow cases. These
ordinary runs use a controlled HTTP provider and are not inference evidence.
The cases cover disclosure/consent, unapplied proposals, manual-mode strict apply,
shared undo, untrusted wording, author units, quarantine, unavailable providers,
late dataset and specification changes, provider/key changes and literal reserved
source-column names. Both runs report zero browser errors/external requests.

Separate actual-model browser runs pass the same12 model cases from
[source](model-drafts/source-real-browser-checks.json) and
[fresh installation](model-drafts/installed-real-browser-checks.json). Their actual
positive inference uses Qwen2.5:3b and request hash
`37ae6bce2456180563a5e4326dac15acb4e3a3766a569cc7d97432e21f1de479`
(65,159 bytes). Each checks requested sources/title, reviews before applying,
strictly renders PNG/SVG/PDF in manual mode, and undoes through shared history.
Negative cases remain controlled in these runs; they are not claims that a live
model produced each injected fault.

A preceding [actual browser trial](model-drafts/browser-exploratory-failure.json)
retained the old title despite valid source bindings and was rejected before
application. Explicit requested-change instructions were then added. This is
exploratory debugging, not evidence of a general model-quality rate or a guarantee
that a valid proposal follows the user's request.

[Installed product hashes](model-drafts/installed-product-matches.json) match
source. Fresh-installed tests deny external Python/Node networking while allowing
loopback inference. Live OpenAI account inference, human usability and
productivity advantages remain untested.

All seven local gates pass on stable product hashes:234 Node/1565 Python,
no skips and one existing upstream MLflow/SQLAlchemy warning.54 related provider
and editor contracts pass on actual Python3.10.22 and within the full3.12.14 suite.
[Editor verification and hashes](model-drafts/editor-verification.json). Exact
commit CI remains required before closing82;83–89 are still pending.

## Final82 acceptance

[Requirement-by-requirement audit](model-draft-acceptance.md) closes the scoped
feature using actual source and fresh-installed66 browser workflows/21 kind
controls, plus13 model cases per actual-provider run. New proof persists the
applied strict runtime report, compares source digest and four row counts,
explicitly downloads a source-inclusive bundle, checks the full CSV SHA256 and
replays the exported script. Actual line marks remain x `[1,2,3,4]`,
y `[51,54,56,59]` with the requested labels/title; original CSV bytes remain
unchanged after replay. This is the measured synthetic example, not a guarantee
of general model quality. [Closing evidence](model-drafts/closing-acceptance.json).
All seven checks were rerun234/1565 on stable source hashes. The closing
checkpoint's exact CI is verified after push before83 implementation.
