# Import an existing Python figure

Current source reads supported Matplotlib and Seaborn scripts and turns their raw
plotted values into editable GraphUnslopify figures. It never runs your script.
It preserves original bytes and reports unsupported behavior with source locations.
The new figure uses canonical presentation and checks; pixel equivalence is not claimed.

This is newer than published PyPI 0.8.0. Use a current local checkout, following
the [repository installation instructions](../../README.md).

## In the local editor

1. Open **Import a Python figure** and choose a UTF8 `.py` or `.pyw` file.
2. For CSV references, upload the intended dataset with the ordinary data picker
   and select **Use the current CSV for references in this script**. Paths in
   source are never opened automatically. Confirm that the mapped data is what
   the original script used.
3. Click **Review source import**. Inspect proposed intent, hashes and unsupported
   statements. The proposal is unapplied and unverified.
4. Acknowledge review. Partial extraction also requires accepting the listed gaps.
   Click **Apply and check imported figure**. Read the actual strict native result
   before exporting.
5. **Undo source import** restores the prior dataset and figure. Later figure edits
   disable this undo until you restore the imported version.

**Save original source** downloads the exact selected bytes. **Save conversion
report** also works when conversion refuses. Applied reports accompany rendered
exports and downloaded bundles. Original Python stays separate and is excluded
from bundles. The ordinary bundle data checkbox controls normalized CSV inclusion.
No network service receives your source or data.

Changing the source, mapping or figure invalidates its pending proposal. Late
responses cannot replace newer editor intent. Proposals expire after ten minutes,
belong to their originating editor and are limited to eight per session.

## Supported patterns

| Pattern | Behavior |
| --- | --- |
| Pyplot, NumPy, Pandas and Seaborn imports/aliases | Recognize current bindings without executing imports |
| Literal one-dimensional vectors or `np.array([...])` | Preserve values; `plot(y)` supplies integer x |
| `fig, ax = plt.subplots()` | One independent axes |
| `plt.plot(x,y)`, `ax.scatter(x,y)`, `ax.bar(categories,y)` | Raw line/scatter/bar; bar categories must be unique strings |
| `df=pd.read_csv('results.csv')`, `df['column']` | Symbolic reference, explicitly mapped CSV, default Pandas CSV interpretation |
| `sns.lineplot(data=df,x='step',y='loss',hue='model',estimator=None,errorbar=None)` | Raw lines and categorical grouping; no inferred estimator or interval |
| `sns.scatterplot(data=df,x='x',y='y',hue='model')` | Raw scatter and categorical grouping |
| Literal labels/title, default linear/log scales, basic legend settings | Map supported settings into canonical intent |

```python
import matplotlib.pyplot as plt
fig, ax = plt.subplots()
ax.plot([0, 1, 2], [3, 2, 1], label='Model A')
ax.set_xlabel('Step')
ax.set_ylabel('Loss')
ax.legend()
```

Missing/nonfinite plotted values, numeric hue, overlapping bar categories, mixed
plot kinds, multiple datasets and unsupported encodings require manual work.
Line x must already increase strictly within each series. Duplicate/reordered
steps are never silently sorted or averaged. Import never cleans, drops or assigns
uncertainty to observations.

Seaborn's default aggregated lines and intervals are unsupported. Use a reviewed
raw-data script with `estimator=None`, or reconstruct intended statistics explicitly.
Loops, functions, mutations, custom style calls, export destinations and exact
`figsize` generate located findings or refusal. Partial extraction requires author
review; it does not mean the original program was fully understood or validated.

## CLI and Python

```sh
graphunslopify import-source original.py --out-dir new-import
graphunslopify import-source original.py --data reviewed.csv --out-dir new-mapped-import
```

Each destination must be new. It receives `original-source.py`, `source-import.json`
and, for accepted conversions, normalized CSV, figure JSON and native outputs.
Inputs remain unchanged. Default CLI rendering is strict. Exit 0 means the requested
operation passed; exit 1 means conversion was refused; exit 2 means an operational
or native verification failure. `--accept-partial` accepts reported gaps explicitly.
`--no-render` materializes an unverified proposal and records `native_status: not_run`,
even when its exit code is zero.

```python
from pathlib import Path
from graphunslopify.source_imports import import_source, save_source_import

proposal = import_source(Path('original.py').read_bytes(), name='original.py')
print(proposal.report)  # review before accepting any partial extraction
result = save_source_import(proposal, 'new-import', render=True)
```

## Bounds and verification scope

Limits: 256 KiB UTF8 source, 50,000 AST nodes, 32 plot calls/series, 100,000 normalized
rows and one explicitly mapped CSV of at most 20 MiB. The owned parser has a
20-second deadline, 512 MiB process-tree RSS budget and 32 MiB output budget.
Two source readers may run concurrently in an editor. This is bounded static
analysis, not a sandbox for executing arbitrary Python.

Tests compare trusted original Matplotlib/Seaborn artists against extracted values
and run strict native renders. HTTP/browser controls cover review, exact original
downloads, explicit mapping, partial acceptance, stale responses and undo.
`npm run sources-check` reruns the browser controls; GitHub Actions retains its
source-import artifact. These checks do not establish arbitrary-script compatibility,
experimental validity or adoption.

See [the local editor](../local-editor.md), [experiment histories](experiment-histories.md)
and [the thirty-idea roadmap](../../pipeline/research-platform-roadmap.md).
