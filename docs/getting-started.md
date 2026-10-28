# Your first checked figure

A five-minute guided tour once Python is ready. Package download time varies.
You will make a complete figure, inspect its report, and see a deliberately false
claim get rejected and corrected. The example is synthetic and needs no account.
These steps work with the published **0.8.0** package.

## 1. Install once

You need **Python 3.10 or newer**. Open a terminal in a folder where you want to
keep your figures. Create and activate a virtual environment:

**macOS / Linux**

```sh
python3 -m venv .venv
source .venv/bin/activate
```

**Windows PowerShell**

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Then, on either platform:

```sh
python -m pip install graphunslopify==0.8.0
graphunslopify doctor
```

Look for `"ok": true` and package/compiler version `0.8.0` in the doctor output.
The package includes the local translator and its Node runtime. npm, a server and
optional extras are not needed for this tour. Translation and local-file rendering
work offline after installation.

If PowerShell blocks activation, use `.\.venv\Scripts\python.exe` in place of
`python` and `.\.venv\Scripts\graphunslopify.exe` in place of `graphunslopify` in
the commands below. This lets you use the environment directly.

## 2. Make the complete example

```sh
graphunslopify demo first-figure --json
```

Open `first-figure/figure.png` in your normal image viewer. It shows the mean scores
of two methods over three epochs, with bootstrap confidence bands over four seed
IDs. In this synthetic dataset, `ours` is two score units above `base` at every
epoch. The checked claim compares those displayed means; it is not a significance
test.

The demo creates the entire editable example for you:

| File in `first-figure/` | Purpose |
| --- | --- |
| `results.csv` | All24 synthetic observations, including method and seed IDs. |
| `figure.json` | Which columns, means, uncertainty and claim to use. |
| `figure.py` | Generated Python that reads the data locally and draws the figure. |
| `figure.png`, `figure.svg`, `figure.pdf` | Raster and vector exports. |
| `figure.report.json` | Checks, findings, claim verdicts and output fingerprints. |

Open the report and find `"status": "passed"`, `"strict": true`, and the claim's
`"verdict": "holds"`. Each method/epoch has four unit IDs; the report's sample
sizes are `[4, 4, 4, 4, 4, 4]`. Read any warnings or interval-overlap caveats too.
A passing report establishes the requested checks for these inputs, not the
validity of an experimental design.

To rerun the saved program:

```sh
graphunslopify run first-figure/figure.py --json
```

To read the evidence embedded in an exported image:

```sh
graphunslopify provenance first-figure/figure.png
```

That prints the effective spec, description, and data/source fingerprints.
Fingerprints identify which inputs produced an artifact; they do not establish
that the inputs are scientifically correct.

## 3. See a failed check, then correct it

Duplicate `first-figure/figure.json` as `first-figure/review.json` using your file
manager or editor. In the copy's `claims` entry, change `subject` from `ours` to
`base` and `reference` from `base` to `ours`. The claim object should read:

```json
{"kind": "beats_everywhere", "subject": "base", "reference": "ours"}
```

This deliberately asks for the opposite of the known result. Run:

```sh
graphunslopify render first-figure/review.json --out-dir first-figure/claim-check --api local --json
```

Expect **exit code2**, `"status": "failed"` and `"verdict": "fails"`. The command
can still write images: their existence is not a verification pass. Inspect
`first-figure/claim-check/figure.report.json` to see the reason. Your original
successful exports stay in `first-figure/`.

In `review.json`, restore `"subject": "ours"` and `"reference": "base"`, then run
the same command again. Expect exit code0 and `"status": "passed"`. In this exercise
we know which claim is true from the synthetic values. For your own results,
inspect the values and intended assertion before making a correction.

## 4. Use your own CSV

Start by profiling it:

```sh
graphunslopify describe path/to/results.csv
```

Copy the example spec beside your data and adapt these fields:

| Spec field | Choose from your dataset |
| --- | --- |
| `data.path` | Your CSV filename, relative to the spec file. |
| `x.field` | For this line example, a numeric input such as epoch. Use the gallery's recipes for date or categorical designs. |
| `y.field` / `y.label` | The measured value and a readable axis label; add its unit when known. |
| `group` / `series_order` | Method names; remove both and set `legend.show` to false for a single ungrouped series. |
| `uncertainty.over` | The column identifying your actual sampling units, if available. Repeated IDs are summarized within each point first. |
| `claims` | An assertion you intend to check. Remove the demo claim while choosing your own. |

Review inferred roles and unit IDs against the study; a row number alone does not
establish independence. If you lack an appropriate unit column, remove `uncertainty`
until you can specify a defensible design. Render the adapted spec with the same command pattern:

```sh
graphunslopify render path/to/figure.json --out-dir figures --api local --json
```

Relative data paths resolve beside the spec, even when exports go elsewhere.
Default strict mode rejects failed or incomplete required checks. Warnings remain
visible; `--fail-on-warning` can require their review too.

Prefer the browser? Run `graphunslopify preview --open` and select your CSV in the
[local editor](local-editor.md). Save wanted outputs before stopping its temporary
session.

## Common first-run problems

| Symptom | Next step |
| --- | --- |
| `graphunslopify` is not found | Activate the environment, or run `python -m graphunslopify.cli` with that environment's Python. |
| Doctor reports a package/compiler mismatch | Check that the active Python environment contains the intended version; see [installation](installation.md). |
| Demo says it would overwrite a file | Choose a fresh directory. After editing demo inputs, use `render` rather than asking `demo` to recreate them. |
| Render fails or is incomplete | Read `status`, `findings`, `claims` and `untested` in the report. Keep the required check and resolve its stated cause. |
| A data file cannot be found | Check `data.path` relative to the JSON spec's folder. |

Next: [installation and extras](installation.md), [runtime report policies](runtime-reports.md),
[example gallery](../examples/README.md), and [documentation versions](versioning.md).
New source-only features are documented separately from the immutable0.8.0 release.
