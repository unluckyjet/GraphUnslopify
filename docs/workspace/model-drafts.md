# Model draft backend (82a)

This source checkpoint adds a proposal backend, not an editor feature yet.
Roadmap82 remains in progress. Browser provider configuration, disclosure/consent,
review/apply, shared undo, stale-request fences and installed browser acceptance
remain required before completing it. PyPI0.8.0 predates this work.

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
