"""Native Excel values shared with package-free generated programs.

Keep this module standalone: build:translator embeds it for Excel inputs.
Cells use their stored/cached values; no formulas or macros are executed.
"""

EXCEL_SUFFIXES = {".xlsx", ".xls", ".xlsm"}


class WorksheetSelectionError(ValueError):
    def __init__(self, message, sheets):
        super().__init__(message)
        self.sheets = list(sheets)


def _open_workbook(source):
    import pandas as pd

    try:
        return pd.ExcelFile(source, engine="calamine")
    except ImportError as error:
        raise ValueError(
            "Excel input needs pandas>=2.2 and python-calamine>=0.3.1 "
            "(or the source package's [excel] extra)."
        ) from error
    except Exception as error:
        raise ValueError(f"Could not read Excel workbook: {error}") from error


def workbook_sheets(source):
    with _open_workbook(source) as workbook:
        return list(workbook.sheet_names)


def read_excel_table(source, *, sheet=None, identity_fields=()):
    import pandas as pd

    with _open_workbook(source) as workbook:
        names = list(workbook.sheet_names)
        if sheet is None:
            if len(names) != 1:
                raise WorksheetSelectionError(
                    "Choose a worksheet explicitly with data.sheet (CLI: --sheet). "
                    f"Available worksheets: {names}",
                    names,
                )
            sheet = names[0]
        if not isinstance(sheet, str) or sheet not in names:
            raise WorksheetSelectionError(
                f"Unknown worksheet {sheet!r}; choose from {names}", names
            )
        try:
            # Excel stores types. Preserve strings such as 001 and NA, while
            # treating genuinely blank cells as missing; infer only native objects.
            raw = pd.read_excel(
                workbook, sheet_name=sheet, dtype=object, keep_default_na=False, na_values=[""]
            )
        except Exception as error:
            raise ValueError(f"Could not read worksheet {sheet!r}: {error}") from error
        columns = [str(name) for name in raw.columns]
        if len(columns) != len(set(columns)):
            raise ValueError("Excel column labels collide after conversion to field names")
        raw.columns = columns
        frame = raw.infer_objects()
        frame.attrs["_graphunslopify_identity_rows"] = {
            field: raw[field].tolist() for field in identity_fields if field in raw
        }
        frame.attrs["_graphunslopify_excel_sheet"] = sheet
        frame.attrs["_graphunslopify_excel_engine"] = workbook.engine
        return frame
