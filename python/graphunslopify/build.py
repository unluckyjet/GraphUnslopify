"""Writing a figure spec in Python instead of assembling JSON by hand.

The MCP tool is for an agent. This is for a person sitting in a notebook who
wants the same guarantees without the round trip: one place that owns every
presentation decision, a claim the data has to support, and alt text that comes
out on its own.

    from graphunslopify import Figure

    (
        Figure.line("results.csv")
        .x("epoch", "Training epoch")
        .y("accuracy", "Test accuracy", unit="%")
        .by("model", order=["baseline", "ours"], emphasise="ours")
        .average_over("seed")
        .claim("beats_everywhere", "ours", "baseline")
        .render()
    )

`render` translates locally by default, writes the script beside the data and
runs it, so the artefact on disk is the same script the agent would have got.
Nothing here reimplements the emitter, because two emitters drift.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from typing_extensions import Self

from .errors import SpecError
from .transport import post as _post

Kind = Literal["line", "scatter", "bar", "box", "violin", "heatmap", "table"]


def _relative_path(path: str | Path, where: Path) -> str:
    try:
        return os.path.relpath(path, where)
    except ValueError:
        # Windows cannot express a relative path between different drives.
        return str(Path(path).resolve())


@dataclass
class Figure:
    """A spec under construction. Every method returns self, so calls chain."""

    spec: dict[str, Any] = field(default_factory=dict)

    # --- starting points --------------------------------------------------

    @classmethod
    def of(cls, kind: Kind, path: str | Path = "results.csv") -> Self:
        return cls({"kind": kind, "data": {"path": str(path)}})

    @classmethod
    def line(cls, path: str | Path = "results.csv") -> Self:
        return cls.of("line", path)

    @classmethod
    def scatter(cls, path: str | Path = "results.csv") -> Self:
        return cls.of("scatter", path)

    @classmethod
    def bar(cls, path: str | Path = "results.csv") -> Self:
        return cls.of("bar", path)

    @classmethod
    def box(cls, path: str | Path = "results.csv") -> Self:
        return cls.of("box", path)

    @classmethod
    def violin(cls, path: str | Path = "results.csv") -> Self:
        return cls.of("violin", path)

    @classmethod
    def heatmap(cls, path: str | Path = "results.csv") -> Self:
        return cls.of("heatmap", path)

    @classmethod
    def table(cls, path: str | Path = "results.csv") -> Self:
        return cls.of("table", path)

    @classmethod
    def from_profile(cls, path: str | Path, rank: int = 0, api: str | None = None) -> Self:
        """Start from what the data suggests rather than from a guess.

        Profiles the file, asks the translator to rank candidate designs, and
        takes one. This is the same path an agent takes, available to a person.
        """
        from .describe import profile

        report = profile(path)
        if not report.get("ok"):
            raise SpecError(report.get("error", "the file could not be profiled"))
        candidates = _post("/api/suggest", {"profile": report}, api=api)
        if not candidates:
            raise SpecError("nothing in this file suggests a figure")
        if rank < 0 or rank >= len(candidates):
            raise SpecError(f"rank must be between 0 and {len(candidates) - 1}")
        chosen = dict(candidates[rank]["spec"])
        suffix = Path(path).suffix.lower()
        chosen["data"] = {
            "path": str(path),
            "format": {".parquet": "parquet", ".json": "json"}.get(suffix, "csv"),
        }
        return cls(chosen)

    # --- encoding ---------------------------------------------------------

    def x(self, field_name: str, label: str, **axis: Any) -> Self:
        self.spec["x"] = {"field": field_name, "label": label, **axis}
        return self

    def y(self, field_name: str, label: str, **axis: Any) -> Self:
        self.spec["y"] = {"field": field_name, "label": label, **axis}
        return self

    def value(self, field_name: str, label: str) -> Self:
        """The cell value and its colourbar label, for a heatmap."""
        self.spec["value"] = field_name
        self.spec["value_label"] = label
        return self

    def by(
        self,
        column: str,
        order: list[str] | None = None,
        emphasise: str | None = None,
    ) -> Self:
        self.spec["group"] = column
        if order is not None:
            self.spec["series_order"] = list(order)
        if emphasise is not None:
            self.spec["emphasis"] = {"series": emphasise}
        return self

    # --- summarising ------------------------------------------------------

    def average_over(self, replicate: str | None = None, level: float = 0.95) -> Self:
        """Collapse repeats and show the spread, which is the common case.

        Aggregating without showing the spread throws away the thing a reader
        most needs, so this sets both together rather than letting them drift
        apart.
        """
        self.spec["aggregation"] = "mean"
        uncertainty: dict[str, Any] = {"kind": "ci", "level": level, "display": "band"}
        if replicate:
            uncertainty["over"] = replicate
        self.spec["uncertainty"] = uncertainty
        return self

    def median_over(self, replicate: str | None = None) -> Self:
        self.spec["aggregation"] = "median"
        spread: dict[str, Any] = {"kind": "iqr", "display": "band"}
        if replicate:
            spread["over"] = replicate
        self.spec["uncertainty"] = spread
        return self

    def aggregate(self, how: str) -> Self:
        self.spec["aggregation"] = how
        return self

    def where(self, column: str, op: str, value: Any) -> Self:
        self.spec.setdefault("filter", []).append({"field": column, "op": op, "value": value})
        return self

    # --- marking up -------------------------------------------------------

    def reference(
        self, axis: str, value: float, label: str | None = None, meaning: str = "other"
    ) -> Self:
        line: dict[str, Any] = {"axis": axis, "value": value, "meaning": meaning}
        if label:
            line["label"] = label
        self.spec.setdefault("reference_lines", []).append(line)
        return self

    def note(self, at: str, text: str, series: str | None = None) -> Self:
        """Attach a note somewhere semantic, such as "max" or "crossover"."""
        entry: dict[str, Any] = {"at": at, "text": text}
        if series:
            entry["series"] = series
        self.spec.setdefault("annotate", []).append(entry)
        return self

    def claim(
        self,
        kind: str,
        subject: str,
        reference: str | None = None,
        tolerance: float | None = None,
    ) -> Self:
        """State what the figure is meant to show, so the script can check it."""
        entry: dict[str, Any] = {"kind": kind, "subject": subject}
        if reference:
            entry["reference"] = reference
        if tolerance is not None:
            entry["tolerance"] = tolerance
        self.spec.setdefault("claims", []).append(entry)
        return self

    def layer(self, mark: str, **options: Any) -> Self:
        self.spec.setdefault("layers", []).append({"mark": mark, **options})
        return self

    # --- layout and output ------------------------------------------------

    def facet(self, by: str, columns: int = 2, **options: Any) -> Self:
        self.spec["facet"] = {"by": by, "columns": columns, **options}
        return self

    def repeat(self, fields: list[str], columns: int = 2) -> Self:
        self.spec["repeat"] = {"fields": list(fields), "columns": columns}
        return self

    def zoom(
        self, x: tuple[float, float], y: tuple[float, float], corner: str = "lower_right"
    ) -> Self:
        self.spec["inset"] = {"x": list(x), "y": list(y), "corner": corner}
        return self

    def cut_axis(self, start: float, end: float, axis: str = "y") -> Self:
        self.spec["axis_break"] = {"axis": axis, "from": start, "to": end}
        return self

    def venue(self, name: str) -> Self:
        self.spec.setdefault("style", {})["venue"] = name
        return self

    def wide(self) -> Self:
        self.spec.setdefault("output", {})["size"] = "double_column"
        return self

    def titled(self, title: str, caption: str | None = None) -> Self:
        self.spec["title"] = title
        if caption:
            self.spec["caption"] = caption
        return self

    def context(self, sentence: str) -> Self:
        """Level four of the alt text, which only the author can supply."""
        self.spec["alt_text"] = sentence
        return self

    def lock(self, path: str | Path = "paper.lock.json") -> Self:
        self.spec["palette_lock"] = str(path)
        return self

    def named(self, stem: str) -> Self:
        self.spec.setdefault("output", {})["stem"] = stem
        return self

    def output(self, **options: Any) -> Self:
        self.spec.setdefault("output", {}).update(options)
        return self

    def animate(self, **options: Any) -> Self:
        self.spec["animate"] = {**options}
        return self

    def set(self, **options: Any) -> Self:
        """Anything the builder does not wrap, set directly."""
        self.spec.update(options)
        return self

    # --- producing something ----------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.spec))

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.spec, indent=indent)

    def translate(self, api: str | None = None) -> dict[str, Any]:
        """Use the local translator, or an explicitly selected HTTP API."""
        result = _post("/api/convert", self.spec, api=api)
        if result.get("status") != "translated":
            raise SpecError(json.dumps(result.get("issues", result), indent=2))
        return result

    def check(self, api: str | None = None) -> list[dict[str, Any]]:
        return list(self.translate(api).get("findings", []))

    def render(
        self,
        cwd: str | Path | None = None,
        api: str | None = None,
        strict: bool = False,
        fail_on_warning: bool = False,
    ) -> dict[str, Any]:
        """Translate, write the script beside the data, and run it.

        `strict` rejects static errors, failed claims, unavailable inspection,
        and untested required checks. `fail_on_warning` also rejects warnings.
        Both default off; the JSON report always records the actual verdict.
        """
        # Resolve input paths before moving to the output directory. Keep paths
        # relative to the generated program, and do not mutate the author's spec.
        prepared = self.to_dict()
        data = prepared.setdefault("data", {})
        if not isinstance(data, dict):
            raise SpecError("data must be an object")
        source = data.get("path", "results.csv")
        if not isinstance(source, str):
            raise SpecError("data.path must be text")
        remote = "://" in source
        source_path = Path(source).expanduser().resolve() if not remote else None
        where = (
            Path(cwd).expanduser().resolve()
            if cwd
            else (source_path.parent if source_path else Path.cwd())
        )
        if source_path:
            data["path"] = _relative_path(source_path, where)
        if prepared.get("palette_lock"):
            if not isinstance(prepared["palette_lock"], str):
                raise SpecError("palette_lock must be a file path")
            prepared["palette_lock"] = _relative_path(
                Path(prepared["palette_lock"]).expanduser().resolve(), where
            )
        translator = copy(self)
        translator.spec = prepared
        result = translator.translate(api)
        findings = result.get("findings", [])
        errors = [f for f in findings if f.get("severity") == "error"]
        for finding in findings:
            print(f"{finding['severity'].upper()} [{finding['code']}] {finding['message']}")
        if errors and (strict or fail_on_warning):
            raise SpecError(f"{len(errors)} error(s) in the spec, and strict is on")

        where.mkdir(parents=True, exist_ok=True)
        stem = self.spec.get("output", {}).get("stem", "figure")
        script = where / f"{stem}.py"
        script.write_text(result["code"], encoding="utf8")

        command = [sys.executable, str(script.resolve())]
        if strict:
            command.append("--strict")
        if fail_on_warning:
            command.append("--fail-on-warning")
        report_path = where / f"{stem}.report.json"
        # Do not mistake an earlier run's evidence for this execution.
        report_path.unlink(missing_ok=True)
        completed = subprocess.run(
            command,
            cwd=where,
            capture_output=True,
            text=True,
            encoding="utf8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            check=False,
        )
        if completed.stdout.strip():
            print(completed.stdout.strip())
        report = json.loads(report_path.read_text()) if report_path.exists() else None
        if completed.returncode != 0:
            detail = (
                completed.stderr.strip()
                or completed.stdout.strip()
                or "the generated script failed"
            )
            raise SpecError(detail, report=report)
        return {
            "script": script,
            "findings": findings,
            "output": completed.stdout,
            "report": report,
            "report_path": report_path if report is not None else None,
        }
