# Native Excel input

Requires current source after the published 0.8.0 release. Install from the
checkout with:

```sh
python -m pip install "./python[excel]"
```

The extra adds pandas>=2.2 and python-calamine. Native `.xlsx`, `.xlsm` and legacy
`.xls` workbooks remain intact; no intermediate CSV is used. The reader is also
embedded in generated Python, whose environment needs those reader dependencies.
The public 0.8.0 wheel does not contain this feature or extra.

## Select the experiment explicitly

```sh
graphunslopify describe experiments.xlsx
graphunslopify describe experiments.xlsx --sheet "Selected results"
```

A workbook with multiple worksheets requires a name. The first command then
returns an error plus the available worksheet names, rather than assuming the
first experiment is the one intended. A workbook with one worksheet can select
that unique sheet. Worksheet names are exact and case-sensitive.

Use the same selection in JSON:

```json
{
  "kind": "bar",
  "data": {"path": "experiments.xlsx", "format": "excel", "sheet": "Selected results"},
  "x": {"field": "subject", "label": "Subject"},
  "y": {"field": "score", "label": "Score", "unit": "%"},
  "aggregation": "none"
}
```

Or use the Python builder:

```python
from graphunslopify import Figure

figure = (Figure.bar("experiments.xlsx")
          .worksheet("Selected results")
          .x("subject", "Subject")
          .y("score", "Score", unit="%"))
figure.render(cwd="figures")

draft = Figure.from_profile("experiments.xlsx", sheet="Selected results")
```

Suggestions are heuristic drafts; review axes, units, experimental IDs and
uncertainty. Known all-nonfinite measurement columns are excluded from suggested
encodings. No observation count establishes experimental independence.

## Values and evidence

The first row supplies column labels. The native reader preserves stored text
such as `001` and `NA`, infers actual numeric/date objects, and treats genuinely
empty cells as missing. Number formatting is presentation: a numeric cell shown
as `001` still contains the number `1`; use text cells for literal identifiers.
Column names become canonical string field names; collisions are refused.

Stored/cached cell values are read. Formulas and macros are not executed or
recalculated; an unavailable cached result stays missing. Review formula results
in the authoring spreadsheet before using them as observations. Profiles disclose
this reader boundary and actual missing/finite counts.

The whole original workbook contributes to its source hash. Audit numeric
fingerprints and row counts use the selected worksheet. The effective spec
retains the selected name and environment evidence records the installed
python-calamine version. Generated scripts use the same reader implementation as
profiling and auditing.

The browser's workbook upload/worksheet selection is the next submilestone;
this backend checkpoint does not yet enable its file picker. See the
[workspace roadmap](../pipeline/visual-workspace-roadmap.md).
