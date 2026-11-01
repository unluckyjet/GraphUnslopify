# Review paper-wide changes and undo

Current source extends the [paper workspace](project-management.md)
with an explicit review before applying shared settings. Install the source package;
these features are newer than the published 0.8.0 package.

Open **Shared settings for this paper**, edit the existing controls or advanced
JSON, then choose **Review shared changes**. The review shows resolved before/after
values for each source-backed figure, including defaults that return when an
override is removed. **Apply reviewed settings** saves the configuration. Run the
paper audit afterward to check actual computations and exports.

[Selected presentation settings](workspace/selected-presentation.md) take precedence
over shared defaults. The review shows the resulting effective differences;
changing a paper default may leave a selected override unchanged.

| Figure source | What the review establishes |
| --- | --- |
| JSON definition | Canonical intent validation and actual resolved style/output differences. Definitions and observations are preserved. |
| Authored Python | The shared policy and a manual-source-review warning. Review neither executes nor rewrites the program; its actual report must satisfy the policy when audited. |
| Source-free PDF | Explicit exclusion from restyling. The original data, numerical claims and uncertainty remain untested. |

Shared settings support partial `style`, output `size`/`dpi`, and a local
`palette_lock`. Data, claims, units and uncertainty definitions are outside this
patch. Static validation is not scientific acceptance or an output preview.
Warnings and unavailable/invalid figure intent stay visible. Invalid intent blocks
Apply; a successful read can report that no change is available to apply.

## Undo a saved settings change

Choose a **Saved settings change**, then **Review undo**. Inspect the affected
figures and choose **Apply reviewed undo**. The original configuration bytes are
restored from intact history. Later data, definitions and manifest edits are
preserved and included in the new review. A conflicting later shared policy,
changed owner/manifest binding, damaged original configuration or partial history
blocks the undo. The new event retains its `undo_of` ancestry; prior history is
preserved. Undoing an undo can deliberately restore its preceding settings.

Closing a review writes nothing. Reloading saved settings discards the shared
draft. A new explicit review can retain a draft while evaluating current inputs.
Newer drafts and late responses cannot replace the current review. Collection
failures clear Apply until a new review succeeds.

## CLI and API

Use the native revision from `project-status`. Read the proposal, then copy its
`proposal_token` when applying exactly the reviewed settings:

```sh
graphunslopify project-status PAPER
graphunslopify project-review-shared PAPER --settings shared.json --expected-revision REVISION
graphunslopify project-apply-shared PAPER --settings shared.json --expected-revision REVISION --proposal-token PROPOSAL_TOKEN
```

For undo, replace `--settings shared.json` with `--undo SETTINGS_EVENT_ID` in both
commands. A review exits0 when it successfully reads intent; Apply exits0 for a
saved configuration, while refusing stale/invalid requests exits2. Neither exit0
means new scientific verification. The existing `project-shared` command remains
a direct, revision-guarded interface for deliberate scripted configuration edits.

Authenticated local POST routes `/api/shared-review` and `/api/shared-apply` use
the same contract. The review request contains `shared` or `undo_event`, plus
`expected_revision`; Apply additionally requires `proposal_token`. Reads create no
settings/history event. Writes share the paper's operation lock and refuse while
its asynchronous worker is active. Genuine review-only projects have no native
settings and refuse these actions.

The proposal binds the actual owner, current inputs, candidate input hashes,
resolved differences, PDF collection, intact history, compiler/package sources and
target configuration. Candidate palettes are checked even before they become
current inputs. Apply recomputes and rechecks this context before creating history.
Settings/results must fit the existing 20 MiB metadata limit. These cooperative
revision/hash guards are not a filesystem compare-and-swap or author authentication.
