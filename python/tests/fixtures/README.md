# Original synthetic editor fixtures

`native-values.xls` is an original synthetic BIFF workbook, not a research dataset.
Sheet `Measurements` contains the literal text IDs `001`, `NA`, `010` and numeric
scores7,11,13. It exercises genuine legacy XLS parsing without shipping xlwt as a
runtime dependency. Generated2026-10-29 using xlwt1.3.0, which is needed only to
regenerate this test input:

```python
import xlwt

book = xlwt.Workbook()
sheet = book.add_sheet("Measurements")
for r, row in enumerate([["subject", "score"], ["001", 7], ["NA", 11], ["010", 13]]):
    for c, value in enumerate(row):
        sheet.write(r, c, value)
book.save("python/tests/fixtures/native-values.xls")
```

`worksheet-experiments.xlsx` is another original synthetic fixture for editor
selection and races. `Control experiment` contains900/910/920; `Measured results`
contains7/11/13, both with literal text IDs001/NA/010. Regenerate using the dev-only
openpyxl writer:

```python
from openpyxl import Workbook

book = Workbook()
book.remove(book.active)
for name, values in [("Control experiment", [900, 910, 920]), ("Measured results", [7, 11, 13])]:
    sheet = book.create_sheet(name)
    sheet.append(["subject", "score"])
    for identity, value in zip(["001", "NA", "010"], values):
        sheet.append([identity, value])
book.save("python/tests/fixtures/worksheet-experiments.xlsx")
```

`drop-profile.csv` is original synthetic CSV text with four rows, one missing score
and one group. The browser checks the actual inferred float64 type and3 present/
1 missing counts. `drop-profile.parquet` contains three complete integer rows;
it verifies native Parquet drop/import/render through the real reader. Regenerate
the latter with the optional pandas/pyarrow dependencies:

```python
import pandas as pd

pd.DataFrame({"epoch": [1, 2, 3], "score": [7, 11, 13]}).to_parquet(
    "python/tests/fixtures/drop-profile.parquet", index=False
)
```

All fixtures are authored test inputs, not observations from people or papers.

`project-review-pages.pdf` is a two-page visual-review fixture created2026-10-31
by copying the single pages of the existing synthetic baseline
`examples/baseline/01-training-curve.pdf` and `02-loss-log.pdf` with pypdf.
It exercises real page selection, different saved PNG bytes and PDF-only review;
its embedded plotting metadata supplies no original data to that review.
Both pages were rendered with Poppler and visually inspected. SHA256:
`48b1e64c6da5a1d449016c385a65faf6d146aae250a2e737944ce53bbc0bb9a7`.
The source PDFs have SHA256 `d338f872a1278b6587f438f8d794497e1a7efb8d2044769d6d658e4b239030c5`
and `1917e98e1cfb8922a1c20d2045f575a0fdf42279c28ea9868684e7d7eb1d69be`.
