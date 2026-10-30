# Model draft acceptance (roadmap82)

Production behavior is reviewed at `6275b8c24e7bce32724d915a58176cab61cbe196`.
Its exact main41056713354 (all nine jobs) and Figure41056713193 passed.
This closing checkpoint strengthens evidence without changing production code.
The new checkpoint must pass its own checks/CI before implementation of83.

| Requirement | Authoritative evidence and scope |
| --- | --- |
| Actual configured model, no canned production substitute | Separate source and fresh-installed browser positives use local Ollama0.40.13/Qwen2.5:3b. Model manifest/runtime details are retained in the [closing record](model-drafts/closing-acceptance.json). Ordinary CI/negative cases use explicitly identified HTTP doubles. |
| Selected immutable data/current schema, disclosure before transmission | `PreviewState.prepare` supplies owned input/palette and column bindings; `DraftPlan.disclosure` serializes the exact request. Protected HTTP tests reject client-profile substitution and verify zero provider calls without explicit boolean consent. Input schema contains all21 kinds; expansion equality and25 recipes exercise compaction/input defaults. |
| Explicit units/design, no invented statistical acceptance | Units and new inferential/paired settings need matching author context. Inference cannot treat guessed roles or row counts as independent units. Tests cover missing/mismatched declarations and unsupported paired/clustered interval contexts. The UI provides author declarations without requiring JSON. Model prose is untrusted and not certified. |
| Parse and validate untrusted output; preserve ownership | Envelope checks, duplicate/nonfinite JSON refusal, canonical strict input validation and compiler static checks precede a proposal. Owned input/palette/output paths cannot be patched; existing claims cannot be removed/reordered/weakened. Refusals, incomplete/tool output and invalid schemas do not become accepted intent. |
| Review before apply, original strict renderer, native undo | Actual source/fresh browser flow leaves the current figure unchanged while proposing; requires review; forces strict rerender in manual mode; checks all three exports; and restores prior intent through shared undo while invalidating obsolete exports. |
| Original observations remain original through the actual model workflow | Source/fresh actual-model runs retain complete applied runtime reports, compare their data prefix and four read/prepared rows, explicitly consent to ZIP source inclusion, hash the full downloaded CSV and replay the exported strict script. Actual Matplotlib line marks are x `[1,2,3,4]`, y `[51,54,56,59]`, with requested title and axis labels. CSV bytes are checked again after replay. |
| Original numerical claims remain enforceable | The actual editor HTTP contract applies a model title patch to a false `beats_everywhere` claim; the original claim remains identical and strict rendering still reports failure. This fault-injection case is controlled, not a claim that the live model authored the fault. |
| Data/spec/provider changes and late replies cannot restore old intent | Server client/generation/provider/binding fences and browser epochs are exercised with held HTTP replies, dataset changes, newer canonical edits and provider replacement. Keys are replaced rather than silently reused. Records are bounded/expiring and each disclosure gets one inference attempt. |
| Honest failure and offline manual fallback | Invalid output is quarantined; provider errors do not echo private error bodies or apply templates. Manual authoring remains usable. Fresh installs deny external Python/Node traffic while allowing explicitly configured loopback inference. No provider is auto-configured or auto-called. |
| Actual source and installed browser acceptance | [Source66 workflows](model-drafts/acceptance-source-browser-checks.json) and [fresh-installed66 workflows](model-drafts/acceptance-installed-browser-checks.json), both with21 native kind controls, zero browser errors/external requests and13 model cases. Their default positive provider is a controlled double. Separate [source actual-model13 cases](model-drafts/acceptance-source-real-checks.json) and [installed actual-model13 cases](model-drafts/acceptance-installed-real-checks.json) retain the real-positive distinction. |
| Original data evidence, not just a success flag | Full applied reports: [source](model-drafts/acceptance-source-real-runtime-report.json), [installation](model-drafts/acceptance-installed-real-runtime-report.json). Source SHA256 is `c5f5d597d568b82bd921c2994cbf0ce88229158d91360f9b50321fa2207f0837`; actual positive request SHA256 is `37ae6bce2456180563a5e4326dac15acb4e3a3766a569cc7d97432e21f1de479`. Full bytes, row counts and actual marks are independently checked. |
| Required local checks and exact-commit CI | Production6275b8c passed all seven local checks (234 Node/1565 Python),54 relevant contracts on actual3.10.22/3.12.14 and exact all9/Figure CI. Closing-check receipts accompany this audit; its own exact CI is checked after push. The downloaded production CI artifact12977671629 was digest-verified and actually inspected:65 workflows/21 kinds/12 controlled model cases/zero browser errors or external requests. |

Model assumptions/questions can still be wrong. One real browser trial selected
correct columns but kept the old title; the harness rejected it before applying.
Earlier malformed/schema/task failures also remain in committed records. The
instructions changed during exploration, so these examples establish neither a
model-quality rate nor human productivity or adoption benefits.

Live OpenAI account inference is untested; documented protocol implementation
and controlled contracts are not proof of an account connection. PyPI0.8.0
predates these source features. No new chart kind was added. This closes only the
model-drafting requirement; the full83–89 initiative remains pending, including
spatial diagnostics/layout, measured performance, review integration and evaluation.

Closing local checks also passed all seven gates234 Node/1565 Python (zero skips,
one existing upstream warning) with stable source hashes. The actual source and
installed generated-script replay reports are retained alongside byte/mark
comparisons. No production behavior changed from the already CI-verified6275b8c.
