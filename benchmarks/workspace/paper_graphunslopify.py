"""Actual project.run_project/history/review/reuse, with disclosed direct save capture."""

from __future__ import annotations

import contextlib
import importlib
import json
import runpy
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXECUTION = runpy.run_path(str(HERE / "execution_context.py"))
COMMON = runpy.run_path(str(HERE / "paper_common.py"))
digest, encoded = COMMON["digest"], COMMON["encoded"]


class Session:
    def __init__(self, root, *, execution_context=None):
        self.context = EXECUTION["load"](
            execution_context, repo=HERE.parents[1], track="paper", arm="graphunslopify"
        )
        self.execution = EXECUTION["receipt"](self.context)
        from graphunslopify.project import initialize_project

        # Load the real reuse module before temporarily instrumenting audit._run;
        # its independent environment probe must retain the original runner.
        importlib.import_module("graphunslopify.project_reuse")

        self.paper = COMMON["Paper"](root)
        self.root = self.paper.root
        self.project = initialize_project(self.root)
        code = self.root / "code"
        code.mkdir()
        for name, source in {
            "paper_capture.py": HERE / "paper_capture.py",
            "execution_context.py": HERE / "execution_context.py",
            "measurement.py": HERE / "measurement.py",
            "reference.py": HERE.parent / "papers/reference.py",
            "certified_measurement.py": HERE.parent / "certified/measurement.py",
            "LICENSE": HERE.parents[1] / "LICENSE",
            "NOTICE.md": HERE.parent / "papers/NOTICE.md",
        }.items():
            shutil.copyfile(source, code / name)
        self.sources = {p: digest(p.read_bytes()) for p in code.iterdir()}
        self.records = []
        self.origins = {}
        self.observation_receipts = {}

    @contextlib.contextmanager
    def observed(self):
        module = importlib.import_module("graphunslopify.audit")
        original = module._run

        def run(command, folder, timeout, *, on_start=None):
            script = Path(command[1])
            if (
                command[0] != sys.executable
                or script.name != "figure.py"
                or not script.is_file()
            ):
                return original(command, folder, timeout, on_start=on_start)
            observed = [
                command[0],
                str(self.root / "code/paper_capture.py"),
                "--observations",
                str(folder / "workspace-paper-saves.json"),
                "--script",
                str(script),
                *EXECUTION["arguments"](self.context),
                *command[2:],
            ]
            completed = original(observed, folder, timeout, on_start=on_start)
            observations = folder / "workspace-paper-saves.json"
            if observations.is_file():
                phase = json.loads(observations.read_text(encoding="utf8"))
                phase["native_subprocess_exit_code"] = completed.returncode
                observations.write_bytes(encoded(phase))
            return completed

        module._run = run
        try:
            yield
        finally:
            module._run = original

    def step(self, name):
        from graphunslopify.project import project_status, run_project
        from graphunslopify.project_selection import (
            apply_project_selection,
            review_project_selection,
        )

        for path, expected in self.sources.items():
            if digest(path.read_bytes()) != expected:
                raise ValueError("Owned paper observer source changed")
        if any(
            not p.is_file() or digest(p.read_bytes()) != h
            for p, h in self.observation_receipts.items()
        ):
            raise ValueError("Original paper observation evidence changed")
        started = time.perf_counter_ns()
        self.paper.edit(name)
        review = None
        if name == "selected-output":
            status = project_status(self.root)
            revision = status["revision"]
            settings = {"output": {"dpi": 300}}
            ids = list(COMMON["FIGURES"][:2])
            review = review_project_selection(
                self.root, ids, settings, expected_revision=revision
            )
            apply_project_selection(
                self.root,
                ids,
                settings,
                expected_revision=revision,
                proposal_token=review["proposal_token"],
            )
            self.paper.dpi.update(dict.fromkeys(ids, 300))
        with self.observed():
            native = run_project(
                self.root, selective=name not in {"first", "add-alias", "remove-alias"}
            )
        tool_end = time.perf_counter_ns()
        specs = self.paper.specs()
        # Native history supplies the actual event path; no benchmark simulation.
        audit_root = (
            Path(self.project["config"]).parent / "history" / native["id"] / "audit"
        )
        results = {}
        for row in native["audit"]["figures"]:
            identity = row["id"]
            if not row["outputs"]:
                raise ValueError(
                    "Actual paper figure did not produce outputs: "
                    + json.dumps(row["errors"])
                )
            folder = (audit_root / row["outputs"][0]["path"]).parent
            report = row["report"]
            observation_folder = folder
            if not (folder / "workspace-paper-saves.json").is_file():
                observation_folder = self.origins[
                    (row["execution"]["origin_event"], identity)
                ]
            self.origins[native["id"], identity] = observation_folder
            phase = json.loads(
                (observation_folder / "workspace-paper-saves.json").read_text(
                    encoding="utf8"
                )
            )
            if phase.get("execution_context") != self.execution:
                raise ValueError(
                    "Actual paper observer execution context differs from producer"
                )
            for filename in ("workspace-paper-saves.json", "data.csv", "figure.py"):
                path = observation_folder / filename
                self.observation_receipts[path] = digest(path.read_bytes())
            events = phase["events"]
            png = next(e for e in events if e["format"] == "png")
            spec = specs[identity]
            stem = report["spec"]["output"]["stem"]
            if (
                digest((observation_folder / "figure.py").read_bytes())
                != phase["program_sha256"]
            ):
                raise ValueError("Paper observation program binding changed")
            if (observation_folder / "data.csv").read_bytes() != Path(
                spec["data"]["path"]
            ).read_bytes():
                raise ValueError(
                    "Paper source data differs from the actual subprocess input"
                )
            # Keep evaluation copies outside the SDK's immutable event inventory.
            evaluation_folder = (
                self.root / "comparison" / f"{len(self.records):03d}-{name}" / identity
            )
            evaluation_folder.mkdir(parents=True, exist_ok=False)
            shutil.copyfile(
                observation_folder / "data.csv", evaluation_folder / "data.csv"
            )
            for fmt in spec["output"]["formats"]:
                shutil.copyfile(
                    folder / (stem + "." + fmt), evaluation_folder / (stem + "." + fmt)
                )
            result = {
                "status": report["status"],
                "exit_code": phase["native_subprocess_exit_code"],
                "native_report_present": True,
                "strict": report["policy"]["strict"],
                "fail_on_warning": report["policy"]["fail_on_warning"],
                "spec": report["spec"],
                "retained_observations": report["data"]["counts"]["finite"],
                "artists": png["artists"],
                "labels": png["labels"],
                "save_observations": events,
                "outputs": {
                    stem + "." + fmt: digest((folder / (stem + "." + fmt)).read_bytes())
                    for fmt in spec["output"]["formats"]
                },
                "data_sha256": digest((evaluation_folder / "data.csv").read_bytes()),
                "producer_sha256": phase["program_sha256"],
                "environment": report["environment"],
                "paper_execution": row["execution"],
                "observed_native_pid": phase["pid"],
                "formal_comparison_performed": self.context[
                    "formal_comparison_performed"
                ],
                "execution_context": self.execution,
            }
            results[identity] = {
                "result": result,
                "folder": str(evaluation_folder),
                "native_folder": str(folder),
                "observation_folder": str(observation_folder),
            }
        answer = {
            "step": name,
            "started_ns": started,
            "tool_end_ns": tool_end,
            "native": native,
            "review": review,
            "results": results,
            "specs": specs,
            "formal_comparison_performed": self.context["formal_comparison_performed"],
            "execution_context": self.execution,
        }
        self.records.append(answer)
        return answer
