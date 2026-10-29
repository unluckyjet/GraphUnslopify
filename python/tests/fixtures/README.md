# Native Excel fixture

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
