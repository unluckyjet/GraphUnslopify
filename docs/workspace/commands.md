# Commands and keyboard shortcuts

Choose **Commands** in either local workspace to search actions and see their
shortcuts. This feature requires the current source; published PyPI 0.8.0
predates it.

Search lists unavailable actions with a short explanation. Use the arrow keys
to choose an action and Enter to run it. Escape closes the search and returns
focus to the control you were using.

| Shortcut | Figure workspace | Paper workspace |
| --- | --- | --- |
| Ctrl/⌘ + K | Search commands | Search commands |
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
