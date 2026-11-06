"""Read-only report from the generated reader and preparation path."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import os
import runpy
import shutil
import subprocess
import sys
from contextvars import ContextVar
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from .audit import _run

_COLUMNS = 100
_GROUPS = 50
_EXAMPLES = 20
_CURRENT_SELECTION = ContextVar("cleaning_preview_selection", default=None)


class CleaningSelection:
    """Follow source positions through the generated preparation operations."""

    def __init__(self, snapshot, *, record_count, **_):
        self.source_sha256 = hashlib.sha256(snapshot).hexdigest()
        self.positions = np.arange(record_count)
        self.conversions = []
        self.exclusions = []
        self.exclusion_count = 0
        self.identifier_steps = []

    def source_columns(self, frame):
        self.columns = [
            {"field": str(field), "dtype": str(series.dtype), "missing": int(series.isna().sum())}
            for field, series in frame.iloc[:, :_COLUMNS].items()
        ]
        self.column_count = len(frame.columns)
        _CURRENT_SELECTION.set(self)

    def _tagged(self, frame, *names):
        marker = "_graphunslopify_preview_ordinal"
        while marker in frame.columns or marker in names:
            marker += "_"
        tagged = frame.copy(deep=False)
        tagged[marker] = self.positions
        return tagged, marker

    def sort(self, frame, field):
        tagged, marker = self._tagged(frame)
        result = tagged.sort_values(field)
        self.positions = result.pop(marker).to_numpy()
        return result

    def filter(self, frame, mask, step):
        keep = mask.to_numpy(dtype=bool, na_value=False)
        absent = mask.isna().to_numpy()
        self.record_excluded("filter_predicate_false", ~keep & ~absent, "filter", step=step)
        self.record_excluded("filter_predicate_missing", absent, "filter", step=step)
        self.positions = self.positions[keep]
        return frame[mask]

    def identifiers(self, frame, normalize, fields, *, final=True):
        result = normalize(frame, final=final)
        present = [field for field in fields if field in result]
        if present:
            lexical = frame.attrs.get("_graphunslopify_identity_rows", {})
            self.identifier_steps.append(
                {
                    "fields": present,
                    "lexical_fields": [field for field in present if field in lexical],
                }
            )
        return result

    def melt(self, frame, *, id_vars, value_vars, var_name, value_name):
        tagged, marker = self._tagged(frame, var_name, value_name)
        result = tagged.melt(
            id_vars=[*id_vars, marker],
            value_vars=value_vars,
            var_name=var_name,
            value_name=value_name,
        )
        self.positions = result.pop(marker).to_numpy()
        return result

    def conversion(self, field, before, after, stage):
        new_missing = int((before.notna() & after.isna()).sum())
        nonfinite = (
            int(np.isinf(after.to_numpy(dtype=float, na_value=np.nan)).sum())
            if pd.api.types.is_numeric_dtype(after.dtype)
            else 0
        )
        if before.dtype != after.dtype or new_missing or nonfinite:
            self.conversions.append(
                {
                    "field": str(field),
                    "stage": stage,
                    "from_dtype": str(before.dtype),
                    "to_dtype": str(after.dtype),
                    "became_missing": new_missing,
                    "infinite": nonfinite,
                }
            )

    def numeric(self, field, before, after, stage):
        if stage != "numeric_domain":
            self.conversion(field, before, after, stage)
        self.record_excluded("missing_measurement", after.isna(), stage, field)

    def record_excluded(self, reason, mask, stage, field=None, *, step=None):
        excluded = np.asarray(mask, dtype=bool)
        if excluded.shape != self.positions.shape:
            raise ValueError("Preparation exclusion positions differ from the prepared data.")
        if excluded.any():
            self.exclusion_count += 1
            if len(self.exclusions) < _GROUPS:
                omitted = np.unique(self.positions[excluded])
                self.exclusions.append(
                    {
                        "reason": reason,
                        "stage": stage,
                        "count": len(omitted),
                        "field": field,
                        "step": step,
                        "records": (omitted[:_EXAMPLES] + 1).tolist(),
                    }
                )

    def _transform(self, field, before, after, stage):
        self.record_excluded("missing_measurement", before.isna(), stage, field)
        self.record_excluded(
            "missing_transformed_measurement", before.notna() & after.isna(), stage, field
        )

    def cumulative(self, field, before, after, _groups):
        self._transform(field, before, after, "cumulative")

    def normalize(self, field, before, after, _groups, _ranges):
        self._transform(field, before, after, "normalize")

    def baseline(self, frame, field, before, *, display_mask, operation, matched, **_):
        shown = display_mask.to_numpy(dtype=bool, na_value=False)
        self.record_excluded("baseline_hidden_from_display", ~shown, operation, field)
        self.record_excluded("missing_measurement", before.isna() & shown, operation, field)
        self.record_excluded(
            "baseline_unmatched", before.notna() & matched.isna() & shown, operation, field
        )
        self.positions = self.positions[shown]
        return frame[display_mask]

    def finish_preparation(self, frame):
        if len(self.positions) != len(frame):
            raise ValueError("Preparation row positions differ from the prepared data.")

    def measurements(self, field, before, numeric, finite, summarized):
        self.conversion(field, before, numeric, "measurement_check")
        if summarized:
            self.record_excluded("missing_measurement", before.isna(), "summary_input", field)
            self.record_excluded(
                "invalid_numeric_measurement",
                before.notna() & numeric.isna(),
                "summary_input",
                field,
            )
            self.record_excluded(
                "infinite_measurement", numeric.notna() & ~finite, "summary_input", field
            )

    def preview(self, counts):
        return {
            "source_sha256": self.source_sha256,
            "rows": {
                key: counts[key]
                for key in ("read", "after_filter", "prepared", "missing_plot_keys")
                if key in counts
            },
            "columns": self.columns,
            "column_count": self.column_count,
            "conversions": self.conversions[:_GROUPS],
            "conversion_count": len(self.conversions),
            "exclusions": self.exclusions,
            "exclusion_count": self.exclusion_count,
            "identifier_steps": self.identifier_steps,
            "measurements": counts.get("measurements", {}),
            "filters": [
                {key: step[key] for key in ("field", "op", "before", "after", "removed")}
                for step in counts.get("filtering", {}).get("steps", [])
            ],
        }


def inspect_preparation(script: Path):
    namespace = runpy.run_path(str(script), run_name="__cleaning_preview__")
    selection = None
    problem = None
    token = _CURRENT_SELECTION.set(None)
    try:
        frame, selection = namespace["load"]()
        frame = namespace["prepare"](frame, selection)
        namespace["report_counts"](frame, selection)
    except (ValueError, TypeError, KeyError, OSError, SystemExit) as error:
        problem = str(error)[:600]
    finally:
        selection = selection or _CURRENT_SELECTION.get()
        _CURRENT_SELECTION.reset(token)
    report = {"status": "blocked" if problem is not None else "prepared", "error": problem}
    if selection is not None:
        report.update(selection.preview(namespace["ROW_COUNTS"]))
    return report


def preview_preparation(spec, source, translate, *, scratch_root=None):
    spec = copy.deepcopy(spec)
    filename = "input-" + source.name
    spec["data"]["path"] = filename
    translated = translate("convert-cleaning-preview", spec)
    if translated.get("status") != "translated" or not translated.get("ok"):
        details = translated.get("issues") or translated.get("findings") or []
        problem = next(
            (item["message"] for item in details if item.get("severity", "error") == "error"),
            "Correct the specification.",
        )
        return {"status": "blocked", "error": problem}
    with TemporaryDirectory(prefix="gu-cleaning-preview-", dir=scratch_root) as scratch:
        folder = Path(scratch)
        try:
            os.link(source, folder / filename)
        except OSError:
            shutil.copyfile(source, folder / filename)
        script = folder / "prepare.py"
        script.write_text(translated["code"], encoding="utf8")
        try:
            completed = _run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    (
                        f"import sys; sys.path.insert(0, {str(Path(__file__).resolve().parent.parent)!r}); "
                        "from graphunslopify.cleaning_preview import main; main()"
                    ),
                    str(script),
                ],
                folder,
                30,
            )
        except subprocess.TimeoutExpired:
            return {"status": "blocked", "error": "The preparation preview exceeded 30 seconds."}
        if completed.returncode:
            raise ValueError("Could not inspect the generated data preparation.")
        return json.loads(completed.stdout)


def main():
    with contextlib.redirect_stdout(io.StringIO()):
        report = inspect_preparation(Path(sys.argv[1]))
    print(json.dumps(report, allow_nan=False))
