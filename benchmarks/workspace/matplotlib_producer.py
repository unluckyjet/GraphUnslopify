"""Independent descriptive Matplotlib producer for the frozen workspace tasks.

Only the publication-legibility inspector is shared with GraphUnslopify. CSV
selection, means, sample SD, claims and drawing below use independent stdlib code.
This implements untimed producer conformance; no formal comparison runs here.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.metadata
import json
import math
import platform
import runpy
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

_MEASUREMENT_SOURCE = Path(__file__).with_name("measurement.py")
MEASUREMENT = runpy.run_path(str(_MEASUREMENT_SOURCE))
_REFERENCE_SOURCE = MEASUREMENT["REFERENCE_SOURCE"]
REFERENCE = MEASUREMENT["REFERENCE"]


def encoded(value):
    return (
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def axis_label(axis):
    return axis["label"] + (" (" + axis["unit"] + ")" if axis.get("unit") else "")


def select(spec, body):
    rows = []
    for row in csv.DictReader(body.decode("utf8").splitlines()):
        if any(row[f["field"]] not in f["value"] for f in spec.get("filter", [])):
            continue
        try:
            x = (
                float(row[spec["x"]["field"]])
                if spec["kind"] == "scatter"
                else row[spec["x"]["field"]]
            )
            y = float(row[spec["y"]["field"]])
        except ValueError:
            continue
        if math.isfinite(y) and (not isinstance(x, float) or math.isfinite(x)):
            rows.append((x, row[spec["group"]], y))
    return rows


def summarize(rows):
    cells = defaultdict(list)
    for x, group, y in rows:
        cells[x, group].append(y)
    result = []
    for (x, group), values in sorted(cells.items()):
        mean = statistics.mean(values)
        sd = statistics.stdev(values) if len(values) > 1 else None
        result.append(
            {
                "x": x,
                "group": group,
                "n": len(values),
                "mean": mean,
                "low": mean - sd if sd is not None else None,
                "high": mean + sd if sd is not None else None,
            }
        )
    return result


def science(spec, summary):
    status, findings = "passed", []
    for claim in spec.get("claims", []):
        if claim["kind"] != "beats_everywhere":
            raise ValueError(
                "This frozen-task producer supports descriptive beats_everywhere only"
            )
        mine = {r["x"]: r["mean"] for r in summary if r["group"] == claim["subject"]}
        theirs = {
            r["x"]: r["mean"] for r in summary if r["group"] == claim["reference"]
        }
        if not mine or mine.keys() != theirs.keys():
            if status != "failed":
                status = "incomplete"
            findings.append({"code": "claim_reference_unavailable", "claim": claim})
        elif any(mine[x] <= theirs[x] for x in mine):
            status = "failed"
            findings.append({"code": "descriptive_claim_false", "claim": claim})
    if spec.get("uncertainty") and any(r["n"] < 2 for r in summary):
        if status != "failed":
            status = "incomplete"
        findings.append(
            {
                "code": "sample_sd_unavailable",
                "reason": "Fewer than two real observations in a cell",
            }
        )
    return status, findings


def render(spec, base, output, cache=None, retain=None):
    """Write a new owned result; reuse calculations, never an acceptance decision."""
    from graphunslopify import inspect_figure

    if spec["kind"] not in {"bar", "scatter"}:
        raise ValueError(
            "This comparator is scoped to the four preregistered bar/scatter tasks"
        )
    if (
        spec.get("aggregation", "mean") != "mean"
        or spec.get("uncertainty", {}).get("kind", "std") != "std"
    ):
        raise ValueError("The frozen tasks use descriptive means and sample SD")
    if any(f.get("op") != "in" for f in spec.get("filter", [])):
        raise ValueError("The frozen tasks use explicit in-filters only")
    base, output = Path(base).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = (base / spec["data"]["path"]).resolve()
    data = source.read_bytes()
    (output / "data.csv").write_bytes(data)
    current = copy.deepcopy(spec)
    current["data"]["path"] = "data.csv"
    (output / "spec.json").write_bytes(encoded(current))
    cache = {} if cache is None else cache
    key = digest(
        encoded(
            {
                "data": digest(data),
                "kind": spec["kind"],
                "fields": [spec["x"]["field"], spec["y"]["field"], spec["group"]],
                "filter": spec.get("filter", []),
                "ddof": 1,
                "producer": digest(Path(__file__).read_bytes()),
                "python": platform.python_version(),
            }
        )
    )
    hit = key in cache
    if not hit:
        rows = select(spec, data)
        cache[key] = (rows, summarize(rows) if spec["kind"] == "bar" else [])
    rows, summary = copy.deepcopy(cache[key])
    status, findings = science(spec, summary)
    groups = [
        g
        for g in spec.get("series_order", sorted({r[1] for r in rows}))
        if any(r[1] == g for r in rows)
    ]
    categories = (
        list(dict.fromkeys(r[0] for r in rows)) if spec["kind"] == "bar" else []
    )
    size = spec["output"]["size"]
    width, height = {"single_column": (3.4, 2.6), "double_column": (7.0, 4.2)}[size]
    files, saves = [], []
    with plt.rc_context(
        {
            "font.size": 9,
            "axes.titlesize": 9,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
            "pdf.fonttype": 42,
            "svg.fonttype": "none",
            "text.parse_math": False,
            "text.usetex": False,
        }
    ):
        figure, axes = plt.subplots(figsize=(width, height), layout="constrained")
        try:
            for index, group in enumerate(groups):
                if spec["kind"] == "bar":
                    values = {r["x"]: r for r in summary if r["group"] == group}
                    chosen = [x for x in categories if x in values]
                    bar_width = 0.8 / len(groups)
                    positions = [
                        categories.index(x)
                        + (index - (len(groups) - 1) / 2) * bar_width
                        for x in chosen
                    ]
                    spread = [
                        values[x]["high"] - values[x]["mean"]
                        if values[x]["high"] is not None
                        else math.nan
                        for x in chosen
                    ]
                    axes.bar(
                        positions,
                        [values[x]["mean"] for x in chosen],
                        bar_width,
                        label=group,
                        yerr=spread
                        if spec.get("uncertainty")
                        and any(math.isfinite(s) for s in spread)
                        else None,
                        capsize=2,
                    )
                else:
                    points = [r for r in rows if r[1] == group]
                    axes.scatter(
                        [r[0] for r in points],
                        [r[2] for r in points],
                        label=group,
                        s=12,
                    )
            if categories:
                axes.set_xticks(
                    range(len(categories)),
                    categories,
                    rotation=60 if size == "single_column" else 0,
                )
            axes.set(
                xlabel=axis_label(spec["x"]),
                ylabel=axis_label(spec["y"]),
                title=spec.get("title", ""),
            )
            figure.legend(
                *axes.get_legend_handles_labels(),
                loc="outside lower center",
                ncols=min(len(groups), 2 if size == "single_column" else 3),
            )
            figure.canvas.draw()
            for fmt in spec["output"]["formats"]:
                path = output / ("figure." + fmt)
                figure.savefig(path, dpi=spec["output"]["dpi"])
                files.append(path)
                # Observe this completed save's actual artists; do not rerender.
                saves.append(MEASUREMENT["saved_figure"](figure, path, spec["kind"]))
            inspection = inspect_figure(
                figure, target_width_in=width, min_text_pt=6, export_paths=files
            )
            if not inspection.ok:
                status = "failed"
            report = {
                "status": status,
                "exit_code": 0 if status == "passed" else 2,
                "scientific_findings": findings,
                "inspection": {
                    "ok": inspection.ok,
                    "findings": [f.__dict__ for f in inspection.findings],
                    "measurements": inspection.measurements,
                },
                "spec": current,
                "retained_observations": len(rows),
                "reference": summary,
                "artists": saves[0]["artists"],
                "save_observations": saves,
                "labels": {
                    "title": axes.get_title(),
                    "x": axes.get_xlabel(),
                    "y": axes.get_ylabel(),
                },
                "calculation_cache": {"hit": hit, "key": key},
                "strict": True,
                "fail_on_warning": False,
                "data_sha256": digest(data),
                "producer_sha256": digest(Path(__file__).read_bytes()),
                "measurement_source_sha256": digest(_REFERENCE_SOURCE.read_bytes()),
                "spec_sha256": digest((output / "spec.json").read_bytes()),
                "outputs": {f.name: digest(f.read_bytes()) for f in files},
                "environment": {
                    "python": platform.python_version(),
                    **{
                        n: importlib.metadata.version(n)
                        for n in ("matplotlib", "numpy", "pillow")
                    },
                },
            }
            if retain is not None:
                retain(figure)
        finally:
            plt.close(figure)
    (output / "report.json").write_bytes(encoded(report))
    return report


class Session:
    """A warm calculation session whose executed producer sources are owned copies."""

    def __init__(self, root, *, retain_figures=False):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=False)
        code = self.root / "code"
        code.mkdir()
        self.program = code / "producer.py"
        self.reference = code / "reference.py"
        self.program.write_bytes(Path(__file__).read_bytes())
        self.reference.write_bytes(_REFERENCE_SOURCE.read_bytes())
        (code / "measurement.py").write_bytes(_MEASUREMENT_SOURCE.read_bytes())
        (code / "certified_measurement.py").write_bytes(
            MEASUREMENT["CERTIFIED_SOURCE"].read_bytes()
        )
        license_source = Path(__file__).with_name("LICENSE")
        if not license_source.is_file():
            license_source = Path(__file__).resolve().parents[2] / "LICENSE"
        (code / "LICENSE").write_bytes(license_source.read_bytes())
        (code / "NOTICE.md").write_bytes(
            _REFERENCE_SOURCE.with_name("NOTICE.md").read_bytes()
        )
        self.sources = {path: digest(path.read_bytes()) for path in code.glob("*.py")}
        self.namespace = runpy.run_path(str(self.program))
        self.cache = {}
        self.records = {}
        self.figures = {} if retain_figures else None

    def render(self, spec, base, name):
        for path, expected in self.sources.items():
            if digest(path.read_bytes()) != expected:
                raise ValueError(
                    "Owned producer source changed; acceptance and session reuse are invalid"
                )
        if not name or Path(name).name != name or name in {".", ".."}:
            raise ValueError("Choose a single owned request name")
        report = self.namespace["render"](
            spec,
            base,
            self.root / "runs" / name,
            self.cache,
            (lambda figure: self.figures.update({name: figure}))
            if self.figures is not None
            else None,
        )
        folder = self.root / "runs" / name
        self.records[name] = {
            "report_sha256": digest((folder / "report.json").read_bytes()),
            "spec_sha256": report["spec_sha256"],
            "data_sha256": report["data_sha256"],
            "data_source": str((Path(base) / spec["data"]["path"]).resolve()),
            "outputs": copy.deepcopy(report["outputs"]),
            "sources": {
                str(path.relative_to(self.root)): sha
                for path, sha in self.sources.items()
            },
            "status": report["status"],
        }
        (self.root / "history.json").write_bytes(encoded(self.records))
        return report

    def validate(self, name):
        """Recheck current evidence against the separate immutable run receipt."""
        record = self.records[name]
        folder = self.root / "runs" / name
        reasons = []
        checks = {
            "report_changed": (folder / "report.json", record["report_sha256"]),
            "spec_changed": (folder / "spec.json", record["spec_sha256"]),
            "saved_data_changed": (folder / "data.csv", record["data_sha256"]),
            "input_changed": (Path(record["data_source"]), record["data_sha256"]),
            **{
                "output_changed:" + file: (folder / file, expected)
                for file, expected in record["outputs"].items()
            },
            **{
                "producer_changed:" + file: (self.root / file, expected)
                for file, expected in record["sources"].items()
            },
        }
        for reason, (path, expected) in checks.items():
            if not path.is_file() or digest(path.read_bytes()) != expected:
                reasons.append(reason)
        return {
            "current": not reasons,
            "status": "incomplete" if reasons else record["status"],
            "strict_accepted": not reasons and record["status"] == "passed",
            "reasons": reasons,
        }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--spec", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    report = render(
        json.loads(args.spec.read_text(encoding="utf8")), args.spec.parent, args.out
    )
    print(json.dumps({"status": report["status"], "exit_code": report["exit_code"]}))
    raise SystemExit(report["exit_code"])


if __name__ == "__main__":
    main()
