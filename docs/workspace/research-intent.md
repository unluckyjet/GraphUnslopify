# Project research intent

Keep accepted wording and presentation conventions with an owned paper project.
Each project has its own memory. Changing a preferred unit label leaves the
figure's unit, quantities, data and saved audit unchanged.

Open **Research intent memory** in the paper workspace to add, update or forget
an entry. Review its previous and proposed wording before accepting. Use the
same panel to read accepted entries and their history.

In **Ask a skeptical reviewer**, open **Add accepted research wording** to
copy selected entries into the author context. The text is editable. It
appears in the exact request disclosure and follows the usual explicit consent
step. A prepared request keeps the wording that was disclosed.

Read the current values and revision with `graphunslopify project-intent PAPER`.
Write the entries to add, replace or forget in a JSON file such as `changes.json`.

```json
{
  "terminology": {"holdout": "held-out test set"},
  "model_names": {"sweep-v2": "Ablation model"},
  "units": {"latency": "ms"},
  "figure_conventions": {"legend heading": "Model variants"}
}
```

Review the exact additions and replacements. A value of `null` proposes
forgetting that entry. Leave untouched entries out of the file.

```sh
graphunslopify project-review-intent PAPER --changes changes.json \
  --expected-revision "$CURRENT_MEMORY_REVISION"
graphunslopify project-accept-intent PAPER --changes changes.json \
  --expected-revision "$CURRENT_MEMORY_REVISION" --review-sha256 "$REVIEWED_DIGEST"
```

The digest comes from the review output. If another edit has already been
accepted or the proposal has changed, read the latest revision and review
the exact changes again. Use `project-intent` to read the current entries
and their acceptance history. Forgetting an entry removes it from current
memory and keeps its previous accepted value in local history.
