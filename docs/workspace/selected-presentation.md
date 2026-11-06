# Edit presentation across selected figures

Current source adds **Edit selected figures** to the local paper workspace.
Install the source package; the published PyPI0.8.0 package predates this feature.

1. Open `graphunslopify project-preview PAPER --open` and expand **Edit selected figures**.
2. Check the figures to change, or choose **Select JSON figures**.
3. Enter a figure title or axis label, or choose a series legend policy,
   layout preset, venue, grid, spines, manuscript width or raster DPI.
   Leave a text field empty or choose **Keep existing** to keep its value.
   Raster DPI must be a whole number from 72 to 1200.
4. Choose **Review selected changes**. Read the resolved before/after differences
   and the explicitly excluded sources, then choose **Apply reviewed changes**.
5. Run **Regenerate changed figures** or **Audit paper** to verify current outputs.

A review validates canonical presentation intent. It executes no figure program
and establishes no new scientific pass. Authored Python and PDFs remain unchanged;
PDF numerical claims stay untested. A selection containing only read-only sources
has no change to apply. A mixed selection shows exactly which JSON figures change.
Figure-specific review notes identify designs without a series legend. Those
figures keep their legend settings and can still receive other selected edits.
Repeated metrics keep their individual Y-axis labels.

Original JSON definitions, manifest bindings, data, claims, transforms and palette
files remain intact. The project saves selected presentation policy in one owned
configuration write and retains its original configuration in history. Precedence
is original definition, then shared paper defaults, then selected settings. Editing
an original definition still shows its source; the workspace notes when selected
settings will override its presentation at audit. No arbitrary font sizes or
manual coordinates are introduced.

**Review return to paper defaults** removes overrides for the selected JSON
figures. Other selected settings survive a partial new edit. Saved overrides use
stable figure IDs; removing a manifest binding retains its configuration/history,
and restoring the same ID retains its policy. A newly duplicated ID starts with
its own original/shared presentation.

Choose a **Saved selection change**, then **Review selection undo**, to inspect
and explicitly apply a reversal. Undo restores the original configuration bytes
while preserving later source/data edits. Conflicting later selected/shared
settings, removed targets, changed inputs or damaged history can require a new
review or make that undo unavailable. Failed writes retain incomplete history;
they never become completed acceptance.

Drafts, active jobs and in-flight saves retain their existing guards. A change to
inputs, the PDF collection, history, selection or proposal invalidates its review.
Source files shared by two bindings remain untouched: selecting one binding can
change its effective presentation without rewriting the other figure's source.
After saving, prior accepted evidence describes its original execution. Strict
scientific checks and current-input export rules still apply. Unknown authored
script dependencies still require execution during selective regeneration.

## Programmatic use

Authenticated local POST `/api/selection-review` accepts `ids`, `settings` and
`expected_revision`. `settings` accepts `title`, `x.label`, `y.label`, the
legend's `show`, `title`, `position` and `style`, canonical `style`, and
`output.size` and `output.dpi`. Axis fields, units and other scientific
settings remain bound to their original definitions.
Use `reset:true` instead of `settings` to remove selected overrides. PDF selection
IDs use `pdf:SOURCE_ID` and are listed as excluded. Apply the same request to
`/api/selection-apply` with the returned `proposal_token`. For undo, replace
`ids`/`settings` with `undo_event` in both calls.

Python callers can use `review_project_selection` and `apply_project_selection`
from `graphunslopify.project_selection`. Config version3 stores selected policy;
existing native version1 and PDF-only version2 projects remain readable. These
cooperative revision/hash guards are not filesystem transactions or signatures.

See [reviewed shared changes](../reviewed-paper-changes.md),
[selective regeneration](../selective-paper-regeneration.md),
[commands](commands.md) and [saved review packets](../paper-review-export.md).
