# Commands and keyboard shortcuts

Choose **Commands** in either local workspace or press **Ctrl/⌘ + K**.
Search by name or combine a category and a term, such as `chart scatter`,
`setting dpi`, `figure second`, or `command render`. Each result shows
its category and any relevant setting or figure context.

- **Chart type** changes the current draft through the workspace's editing
  controls. Paper drafts keep their existing save and audit steps.
- **Setting** opens and focuses the existing control. A setting outside the
  current inspector view opens All settings.
- **Figure** opens a paper figure by manifest ID or an imported PDF by name.
  The standalone editor finds its current figure by title or filename stem.
- **Command** invokes the existing action with its normal eligibility and
  review checks.

Use the arrow keys and Enter to choose a result. Unavailable results give
a short explanation. Escape closes the palette and restores focus.

| Shortcut | Figure workspace | Paper workspace |
| --- | --- | --- |
| Ctrl/⌘ + K | Search the workspace | Search the workspace |
| Ctrl/⌘ + Enter | Render and check outside form fields, or from Advanced JSON | Audit source-backed figures outside text/form fields |
| Ctrl/⌘ + Shift + Enter | — | Regenerate changed figures outside text/form fields |
| Ctrl/⌘ + S | — | Save the definition or manifest draft being edited; shared settings open their review |
| Ctrl/⌘ + Z | Undo a figure control change outside text/form fields | Undo a figure control change outside text/form fields |

Text fields retain their own undo. Unrelated modifier combinations, held-key
repeats and input-method composition do not start workspace operations.

Commands use the current workspace actions. An audit remains unavailable during
another owned operation or while a draft needs saving. A shared settings save
still requires reviewing the affected figures and explicitly applying the
change. External changes still require refreshing current evidence.

Figure bundle downloads retain the **Include source data in ZIP** choice and
current-generation checks. A paper review packet preserves the selected saved
results, including failures, historical evidence and untested PDF claims.
Downloading that evidence does not run the figure programs or turn a rejection
into an accepted result.

See [paper review packets](../paper-review-export.md),
[reviewed shared changes](../reviewed-paper-changes.md) and
[selective regeneration](../selective-paper-regeneration.md).
