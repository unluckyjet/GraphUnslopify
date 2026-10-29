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
