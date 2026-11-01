"""Independent paper updates with actual warm figures and explicit reuse ancestry.

Scientific calculations are the independent csv/statistics producer. Current
acceptance and reused drawing bytes are separate caches with separate guards.
"""

from __future__ import annotations

import copy
import importlib.metadata
import runpy
import shutil
import time
from pathlib import Path

import matplotlib
from matplotlib import font_manager
from matplotlib.backends.backend_agg import FigureCanvasAgg

HERE = Path(__file__).resolve().parent
COMMON = runpy.run_path(str(HERE / "paper_common.py"))
PRODUCER = runpy.run_path(str(HERE / "matplotlib_producer.py"))
digest, encoded = COMMON["digest"], COMMON["encoded"]


class Session:
    def __init__(self, root):
        self.paper = COMMON["Paper"](root)
        self.root = self.paper.root
        self.core = PRODUCER["Session"](self.root / "producer", retain_figures=True)
        self.drawings, self.previous, self.records = {}, {}, []
        self.last_passed, self.members = False, ()
        self.receipts = {}
        code = self.root / "operator-code"
        code.mkdir()
        self.sources = {
            HERE / "paper_matplotlib.py": digest(Path(__file__).read_bytes()),
            HERE / "paper_common.py": digest((HERE / "paper_common.py").read_bytes()),
        }
        for source in self.sources:
            shutil.copyfile(source, code / source.name)
        self.operator_copies = {p: digest(p.read_bytes()) for p in code.iterdir()}

    def environment(self):
        font = Path(font_manager.findfont("DejaVu Sans"))
        return {
            "versions": {
                n: importlib.metadata.version(n)
                for n in ("matplotlib", "numpy", "pillow", "pypdf")
            },
            "font_sha256": digest(font.read_bytes()),
            "rc": {k: repr(v) for k, v in matplotlib.rcParams.items()},
        }

    def intact(self, drawing):
        """Old immutable custody, deliberately separate from changed current inputs."""
        receipt = self.core.records[drawing["name"]]
        folder = self.core.root / "runs" / drawing["name"]
        checks = {
            folder / "report.json": receipt["report_sha256"],
            folder / "spec.json": receipt["spec_sha256"],
            folder / "data.csv": receipt["data_sha256"],
            **{folder / n: h for n, h in receipt["outputs"].items()},
            **self.core.sources,
        }
        if any(
            not p.is_file() or digest(p.read_bytes()) != h for p, h in checks.items()
        ):
            raise ValueError("Original drawing custody changed; reuse is invalid")

    def step(self, name):
        from graphunslopify import inspect_figure

        if any(
            digest(p.read_bytes()) != h
            for p, h in {**self.sources, **self.operator_copies}.items()
        ):
            raise ValueError("Independent paper operator source changed")
        if any(
            not p.is_file() or digest(p.read_bytes()) != h
            for p, h in self.receipts.items()
        ):
            raise ValueError(
                "Saved paper history changed; old acceptance is unavailable"
            )
        started = time.perf_counter_ns()
        self.paper.edit(name)
        review = None
        if name == "selected-output":
            before = self.paper.specs()
            review = {
                "ids": list(COMMON["FIGURES"][:2]),
                "settings": {"output": {"dpi": 300}},
                "before_sha256": digest(encoded(before)),
            }
            # A real bounded plan/save, not a claimed native project review.
            if digest(encoded(self.paper.specs())) != review["before_sha256"]:
                raise ValueError("Independent selection review became stale")
            self.paper.dpi.update(dict.fromkeys(review["ids"], 300))
            (self.root / "selected-output.json").write_bytes(encoded(self.paper.dpi))
        specs = self.paper.specs()
        membership = tuple(specs)
        can_reuse_acceptance = self.last_passed and membership == self.members
        environment = self.environment()
        results, current = {}, {}
        counts = {
            "executed": 0,
            "reused": 0,
            "acceptance_reused": 0,
            "fresh_validation": 0,
        }
        event = self.root / "history" / f"{len(self.records):03d}-{name}"
        event.mkdir(parents=True, exist_ok=False)
        for identity, spec in specs.items():
            raw = Path(spec["data"]["path"]).read_bytes()
            full_key = digest(
                encoded(
                    {
                        "spec": spec,
                        "data_sha256": digest(raw),
                        "environment": environment,
                        "sources": {
                            str(p): h
                            for p, h in {**self.sources, **self.core.sources}.items()
                        },
                    }
                )
            )
            prior = self.previous.get(identity)
            accepted_reuse = can_reuse_acceptance and prior and prior["key"] == full_key
            if accepted_reuse:
                drawing = self.drawings[prior["drawing_key"]]
                self.intact(drawing)
                result = copy.deepcopy(prior["result"])
                counts["acceptance_reused"] += 1
            else:
                selected = self.core.namespace["select"](spec, raw)
                visual = copy.deepcopy(spec)
                visual.pop("data")
                visual.pop("claims", None)
                drawing_key = digest(
                    encoded(
                        {
                            "rows": selected,
                            "visual": visual,
                            "environment": environment,
                            "producer_sha256": digest(self.core.program.read_bytes()),
                        }
                    )
                )
                drawing = self.drawings.get(drawing_key)
                if drawing is None:
                    run_name = f"paper-{len(self.records):03d}-{identity}"
                    result = self.core.render(spec, self.root, run_name)
                    drawing = {
                        "name": run_name,
                        "key": drawing_key,
                        "result": copy.deepcopy(result),
                    }
                    self.drawings[drawing_key] = drawing
                    counts["executed"] += 1
                else:
                    self.intact(drawing)
                    result = copy.deepcopy(drawing["result"])
                    summary = (
                        self.core.namespace["summarize"](selected)
                        if spec["kind"] == "bar"
                        else []
                    )
                    status, findings = self.core.namespace["science"](spec, summary)
                    original = self.core.root / "runs" / drawing["name"]
                    figure = self.core.figures[drawing["name"]]
                    FigureCanvasAgg(figure)
                    inspection = inspect_figure(
                        figure,
                        target_width_in={"single_column": 3.4, "double_column": 7.0}[
                            spec["output"]["size"]
                        ],
                        min_text_pt=6,
                        export_paths=[original / n for n in result["outputs"]],
                    )
                    if not inspection.ok:
                        status = "failed"
                    result.update(
                        status=status,
                        exit_code=0 if status == "passed" else 2,
                        scientific_findings=findings,
                        inspection={
                            "ok": inspection.ok,
                            "findings": [f.__dict__ for f in inspection.findings],
                            "measurements": inspection.measurements,
                        },
                        reference=summary,
                        retained_observations=len(selected),
                    )
                counts["fresh_validation"] += 1
            source = self.core.root / "runs" / drawing["name"]
            self.intact(drawing)
            folder = event / identity
            folder.mkdir()
            (folder / "data.csv").write_bytes(raw)
            actual_spec = copy.deepcopy(spec)
            actual_spec["data"]["path"] = "data.csv"
            (folder / "spec.json").write_bytes(encoded(actual_spec))
            for file in result["outputs"]:
                shutil.copyfile(source / file, folder / file)
            reused_drawing = (
                accepted_reuse
                or source.name != f"paper-{len(self.records):03d}-{identity}"
            )
            counts["reused"] += int(bool(reused_drawing))
            result.update(
                spec=actual_spec,
                spec_sha256=digest((folder / "spec.json").read_bytes()),
                data_sha256=digest(raw),
                execution={
                    "mode": "reused-acceptance"
                    if accepted_reuse
                    else "reused-drawing-fresh-validation"
                    if reused_drawing
                    else "executed",
                    "origin_run": drawing["name"],
                    "original_save_data_sha256": drawing["result"]["data_sha256"],
                    "original_report_sha256": self.core.records[drawing["name"]][
                        "report_sha256"
                    ],
                    "current_acceptance_source_sha256": self.sources[
                        HERE / "paper_matplotlib.py"
                    ],
                },
                formal_comparison_performed=False,
            )
            (folder / "report.json").write_bytes(encoded(result))
            receipt = {
                p.name: digest(p.read_bytes()) for p in folder.iterdir() if p.is_file()
            }
            (folder / "receipt.json").write_bytes(encoded(receipt))
            results[identity] = {"result": result, "folder": str(folder)}
            current[identity] = {
                "key": full_key,
                "drawing_key": drawing["key"],
                "result": copy.deepcopy(result),
            }
        status = (
            "passed"
            if all(r["result"]["status"] == "passed" for r in results.values())
            else "failed"
        )
        self.previous, self.members, self.last_passed = (
            current,
            membership,
            status == "passed",
        )
        answer = {
            "step": name,
            "started_ns": started,
            "tool_end_ns": time.perf_counter_ns(),
            "native": {
                "status": status,
                "exit_code": 0 if status == "passed" else 2,
                "audit": {"execution_counts": counts},
            },
            "review": review,
            "results": results,
            "specs": specs,
            "formal_comparison_performed": False,
        }
        (event / "paper.json").write_bytes(encoded(answer))
        self.receipts.update(
            {p: digest(p.read_bytes()) for p in event.rglob("*") if p.is_file()}
        )
        self.records.append(answer)
        return answer
