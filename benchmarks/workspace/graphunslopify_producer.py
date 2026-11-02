"""Actual current native editor pipeline with owned observational capture.

This adapter preserves renderer/compiler/statistics reuse and strict native
reports. It does not supply scientific answers from the benchmark oracle.
"""

from __future__ import annotations

import copy
import hashlib
import json
import runpy
import uuid
from pathlib import Path

from graphunslopify.preview import PreviewState

HERE = Path(__file__).resolve().parent
EXECUTION = runpy.run_path(str(HERE / "execution_context.py"))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf8")


class ObservedPreview(PreviewState):
    def _run_generated(self, command, folder, timeout):
        native = command[3:]
        if self.worker is None or len(native) not in {11, 12}:
            raise ValueError("Use the owned canonical renderer worker")
        context = self.workspace_execution_context
        if context.get("path"):
            program = Path(native[-5])
            if not program.is_absolute():
                program = folder / program
            (folder / "workspace-execution-context.json").write_bytes(
                encoded(
                    {
                        "path": context["path"],
                        "context_sha256": context["context_sha256"],
                        "program_sha256": digest(program.read_bytes()),
                    }
                )
            )
        return self.worker.run(
            [
                *command[:3],
                "--timings",
                str(folder / "phase-timings.json"),
                "--profile-script",
                native[-5],
                *native,
            ],
            folder,
            timeout,
        )


class Session:
    def __init__(self, root, *, execution_context=None):
        self.context = EXECUTION["load"](
            execution_context, repo=HERE.parents[1], arm="graphunslopify"
        )
        self.execution = EXECUTION["receipt"](self.context)
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=False)
        code = self.root / "code"
        code.mkdir()
        sources = {
            "capture_driver.py": HERE / "capture_driver.py",
            "execution_context.py": HERE / "execution_context.py",
            "measurement.py": HERE / "measurement.py",
            "reference.py": HERE.parent / "papers/reference.py",
            "certified_measurement.py": HERE.parent / "certified/measurement.py",
            "LICENSE": HERE.parents[1] / "LICENSE",
            "NOTICE.md": HERE.parent / "papers/NOTICE.md",
        }
        for name, path in sources.items():
            (code / name).write_bytes(path.read_bytes())
        self.sources = {path: digest(path.read_bytes()) for path in code.glob("*.py")}
        self.state = ObservedPreview(
            self.root,
            100 * 1024 * 1024,
            reuse_renderer=True,
            reuse_translator=True,
            cache_statistics=True,
            staged_preview=True,
            profile_driver=code / "capture_driver.py",
        )
        self.state.workspace_execution_context = self.context
        self.uploads, self.records = {}, {}
        self.generation = 0

    def close(self):
        self.state.close()

    def render(self, spec, base, name):
        if (
            name in self.records
            or not name
            or Path(name).name != name
            or name in {".", ".."}
        ):
            raise ValueError("Choose a new single owned request name")
        for path, expected in self.sources.items():
            if digest(path.read_bytes()) != expected:
                raise ValueError("Owned observation source changed")
        source = (Path(base) / spec["data"]["path"]).resolve()
        data = source.read_bytes()
        key = digest(data)
        if key not in self.uploads:
            self.uploads[key] = self.state.upload(source.name, data)["id"]
        self.generation += 1
        answer = self.state.render(
            {
                "client": "workspace-comparison",
                "generation": self.generation,
                "stage_id": uuid.uuid4().hex,
                "data_id": self.uploads[key],
                "spec": copy.deepcopy(spec),
            }
        )
        if (
            not answer.get("run_id")
            and not answer.get("report")
            and answer.get("translation", {}).get("ok") is False
        ):
            # A supported refusal can occur before native execution. Keep the
            # real compiler evidence; do not invent a native report/process exit.
            folder = self.root / "refusals" / name
            folder.mkdir(parents=True)
            (folder / "data.csv").write_bytes(data)
            findings = answer["translation"].get("findings", [])
            unknown_reference = any(
                f.get("code") == "claim_series_unknown" for f in findings
            )
            result = {
                "status": "incomplete" if unknown_reference else "failed",
                "exit_code": 2,
                "exit_code_source": "adapter_strict_refusal_classification",
                "native_exit_code": None,
                "native_report_present": False,
                "preflight_rejected": True,
                "preflight_findings": findings,
                "compiler_response": answer["translation"],
                "translation_execution": answer["translation_execution"],
                "strict": True,
                "fail_on_warning": False,
                "spec": answer["spec"],
                "retained_observations": None,
                "save_observations": [],
                "outputs": {},
                "data_sha256": key,
                "owned_folder": str(folder),
                "formal_comparison_performed": self.context[
                    "formal_comparison_performed"
                ],
                "execution_context": self.execution,
            }
            (folder / "workspace-result.json").write_bytes(encoded(result))
            self.records[name] = {
                "folder": str(folder.relative_to(self.root)),
                "status": result["status"],
                "source": str(source),
                "data_sha256": key,
                "files": {
                    n: digest((folder / n).read_bytes())
                    for n in ("workspace-result.json", "data.csv")
                },
                "observation_sources": {
                    str(p.relative_to(self.root)): h for p, h in self.sources.items()
                },
            }
            (self.root / "history.json").write_bytes(encoded(self.records))
            return result
        if answer.get("stale") or not answer.get("run_id") or not answer.get("report"):
            raise RuntimeError(
                "No current native report: " + json.dumps(answer.get("translation"))
            )
        folder = self.state.runs[answer["run_id"]]["folder"]
        native = answer["report"]
        stem = native["spec"]["output"]["stem"]
        program = folder / (stem + ".py")
        phase = json.loads((folder / "phase-timings.json").read_text(encoding="utf8"))
        if phase.get("execution_context") != self.execution:
            raise ValueError(
                "Actual native observer execution context differs from producer"
            )
        if phase["program_sha256"] != digest(program.read_bytes()):
            raise ValueError("Observation belongs to a different native program")
        events = phase["events"]
        pngs = [e for e in events if e["format"] == "png"]
        if not pngs:
            raise ValueError("The actual current PNG save was not observed")
        formats = native["spec"]["output"]["formats"]
        paths = {stem + "." + fmt: folder / (stem + "." + fmt) for fmt in formats}
        if any(not p.is_file() for p in paths.values()):
            raise ValueError("A required native export is absent")
        if (folder / "data.csv").read_bytes() != data:
            raise ValueError("Native input binding changed")
        counts = native["data"]["counts"]
        result = {
            "status": native["status"],
            "native_report_present": True,
            "native_exit_code": answer["exit_code"],
            "exit_code_source": "actual_native_process",
            "exit_code": answer["exit_code"],
            "strict": native["policy"]["strict"],
            "fail_on_warning": native["policy"]["fail_on_warning"],
            "spec": native["spec"],
            "retained_observations": counts["finite"],
            "artists": pngs[-1]["artists"],
            "labels": pngs[-1]["labels"],
            "save_observations": events,
            "outputs": {n: digest(p.read_bytes()) for n, p in paths.items()},
            "data_sha256": key,
            "producer_sha256": digest(program.read_bytes()),
            "environment": native["environment"],
            "execution": answer["execution"],
            "translation_execution": answer["translation_execution"],
            "native_report_file": stem + ".report.json",
            "native_run_id": answer["run_id"],
            "owned_folder": str(folder),
            "formal_comparison_performed": self.context["formal_comparison_performed"],
            "execution_context": self.execution,
        }
        result_file = folder / "workspace-result.json"
        result_file.write_bytes(encoded(result))
        self.records[name] = {
            "folder": str(folder.relative_to(self.root)),
            "status": result["status"],
            "source": str(source),
            "data_sha256": key,
            "files": {
                n: digest((folder / n).read_bytes())
                for n in [
                    *paths,
                    program.name,
                    result["native_report_file"],
                    "workspace-result.json",
                    "data.csv",
                    stem + ".figure.json",
                ]
            },
            "observation_sources": {
                str(p.relative_to(self.root)): h for p, h in self.sources.items()
            },
        }
        (self.root / "history.json").write_bytes(encoded(self.records))
        return result

    def folder(self, name):
        return self.root / self.records[name]["folder"]

    def validate(self, name):
        record = self.records[name]
        folder = self.root / record["folder"]
        checks = {
            "file_changed:" + n: (folder / n, h) for n, h in record["files"].items()
        }
        checks["input_changed"] = (Path(record["source"]), record["data_sha256"])
        checks.update(
            {
                "observer_changed:" + n: (self.root / n, h)
                for n, h in record["observation_sources"].items()
            }
        )
        reasons = [
            reason
            for reason, (path, expected) in checks.items()
            if not path.is_file() or digest(path.read_bytes()) != expected
        ]
        return {
            "current": not reasons,
            "status": "incomplete" if reasons else record["status"],
            "strict_accepted": not reasons and record["status"] == "passed",
            "reasons": reasons,
        }
