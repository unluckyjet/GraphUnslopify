"""Conservative reuse of intact accepted native figures; never cache authored programs."""

from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

from .audit import _digest, _outputs, _run, _spec, _validate_report
from .build import Figure, _relative_path
from .errors import SpecError
from .project import EVENT, ProjectError, _hash, _inside, _read


def _environment():
    """Observe a fresh figure-like interpreter, not the workspace's mutable rc state."""
    import matplotlib
    import numpy
    import pandas
    import PIL
    from matplotlib import font_manager, ft2font

    for key in ("MPLCONFIGDIR", "MATPLOTLIBRC", "FONTCONFIG_FILE", "FONTCONFIG_PATH"):
        value = os.environ.get(key)
        if value and any(not Path(part).is_absolute() for part in value.split(os.pathsep)):
            raise ValueError("Relative plotting configuration requires fresh figure execution.")
    backend = matplotlib.get_backend()
    if str(backend).lower() != "agg" or matplotlib.rcParams["text.usetex"]:
        raise ValueError("External/non-Agg rendering requires fresh figure execution.")
    packages = {}
    for dist in importlib.metadata.distributions():
        name = dist.metadata.get("Name")
        if name:
            packages.setdefault(name.lower().replace("_", "-"), set()).add(dist.version)
    return {
        "schema_version": 1,
        "python": {
            "version": sys.version,
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
            "executable_sha256": _digest(Path(sys.executable)),
            "prefix": sys.prefix,
            "optimize": sys.flags.optimize,
        },
        "platform": {"system": platform.system(), "machine": platform.machine()},
        "core_versions": {
            "numpy": numpy.__version__,
            "pandas": pandas.__version__,
            "matplotlib": matplotlib.__version__,
            "Pillow": PIL.__version__,
            "freetype": ft2font.__freetype_version__,
        },
        "installed_versions": {k: sorted(v) for k, v in sorted(packages.items())},
        "backend": backend,
        "config_sha256": _digest(Path(matplotlib.matplotlib_fname())),
        "rc": {k: repr(v) for k, v in sorted(matplotlib.rcParams.items())},
        "fonts": {
            str(Path(font.fname).resolve()): _digest(Path(font.fname))
            for font in font_manager.fontManager.ttflist
        },
        "environment": {
            key: os.environ.get(key)
            for key in (
                "MPLCONFIGDIR",
                "MATPLOTLIBRC",
                "FONTCONFIG_FILE",
                "FONTCONFIG_PATH",
                "LANG",
                "LC_ALL",
                "LC_NUMERIC",
                "TZ",
                "PYTHONHASHSEED",
                "SOURCE_DATE_EPOCH",
            )
        },
        "scope": "Observed interpreter bytes, package versions, rc/config and discovered font bytes; not complete third-party binary authentication.",
    }


def _probe(folder):
    try:
        completed = _run(
            [sys.executable, "-m", "graphunslopify.project_reuse", "--context"], folder, 30
        )
        if completed.returncode:
            return None
        value = json.loads(completed.stdout)
        return value if value.get("schema_version") == 1 and value.get("fonts") else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


class FigureReuse:
    def __init__(self, source, snapshot, producer, history, folder, *, selective, fail_on_warning):
        self.source, self.snapshot, self.folder = source, snapshot, folder
        self.selective = selective
        self.context = _probe(folder)
        self.policy = {"strict": True, "fail_on_warning": fail_on_warning}
        self.key = (
            _hash(
                {
                    "environment": self.context,
                    "producer": producer,
                    "root": str(source.parent),
                    "policy": self.policy,
                }
            )
            if self.context
            else None
        )
        self.events = {e["id"]: e for e in history["events"]}
        self.latest = next(
            (e for e in history["events"] if e.get("action") == "run" or not e["integrity"]), None
        )
        self.history_ok = history["integrity"] == "verified"
        self.receipts = {
            e["id"]: _digest(_inside(source.parent, "history/" + e["id"] + "/receipt.json"))
            for e in history["events"]
            if e["integrity"]
        }
        self.checked_files = {}
        self.reasons, self.reused = {}, 0

    def _deny(self, identity, message):
        self.reasons[identity] = message

    def _row(self, event, identity):
        return next(f for f in event["result"]["audit"]["figures"] if f["id"] == identity)

    def _files(self, event, identity):
        guard = event["result"]["reuse_guard"]
        derived = _hash(
            {
                "environment": guard["environment"],
                "producer": event["result"]["execution_source"],
                "root": guard["root"],
                "policy": guard["figure_policy"],
            }
        )
        if (
            guard["schema_version"] != 1
            or guard["key"] != self.key
            or derived != self.key
            or guard["environment_sha256"] != _hash(guard["environment"])
        ):
            raise ProjectError("Prior runtime/environment/policy guard differs.")
        figure = guard["figures"][identity]
        base = _inside(self.source.parent, "history/" + event["id"])
        found = {}
        for item in figure["files"]:
            path = _inside(base, item["path"])
            if path.stat().st_size != item["bytes"] or _digest(path) != item["sha256"]:
                raise ProjectError("Prior figure program/report/export bytes changed.")
            self.checked_files[path] = (item["bytes"], item["sha256"])
            found[item["path"]] = path
        if len(found) != len(figure["files"]):
            raise ProjectError("Prior figure inventory contains duplicate paths.")
        return figure, found

    def __call__(self, entry, root, destination):
        identity = entry["id"]
        if not self.selective:
            return self._deny(identity, "Full audit requested.")
        if "spec" not in entry:
            return self._deny(
                identity,
                "Authored programs always execute; declared data does not cover unknown imports.",
            )
        previous = self.latest
        if not self.context or not self.history_ok or not previous or not previous["integrity"]:
            return self._deny(
                identity, "No complete current environment/intact latest run is available."
            )
        result = previous["result"]
        if result["exit_code"] != 0 or not result.get("audit") or result["audit"]["exit_code"] != 0:
            return self._deny(
                identity, "Latest native run was not accepted; older passes are not reused."
            )
        try:
            current = next(f for f in self.snapshot["figures"] if f["id"] == identity)
            old = next(f for f in result["snapshot"]["figures"] if f["id"] == identity)
            if current["errors"] or old["fingerprint"] != current["fingerprint"]:
                return self._deny(identity, "Figure inputs or shared settings changed.")
            row = self._row(previous, identity)
            if (
                row["status"] != "passed"
                or row["errors"]
                or result.get("policy_errors", {}).get(identity)
            ):
                return self._deny(identity, "Latest figure was not accepted.")
            report = row["report"]
            _validate_report(report)
            if (
                report["status"] != "passed"
                or report["policy"]["strict"] is not True
                or report["policy"]["fail_on_warning"] != self.policy["fail_on_warning"]
            ):
                return self._deny(identity, "Scientific verification policy differs.")
            spec, source_hash = _spec(entry, root)
            if spec.get("animate", {}).get("format") == "mp4":
                return self._deny(identity, "External video encoders require fresh execution.")
            folder = destination / "figures" / identity
            spec["data"]["path"] = _relative_path(spec["data"]["path"], folder)
            compiled = Figure(spec).translate(api="local")
            if not compiled["ok"] or source_hash != row["source_sha256"]:
                return self._deny(identity, "Canonical figure source differs.")
            expected = hashlib.sha256(compiled["code"].encode()).hexdigest()
            guard, files = self._files(previous, identity)
            audit = _inside(self.source.parent, "history/" + previous["id"] + "/audit")
            old_folder = _inside(audit, result["audit"]["run_directory"] + "/figures/" + identity)
            required = {
                "figure.py",
                "input.spec.json",
                "runtime.report.json",
                "stdout.log",
                "stderr.log",
            }
            relative = {path.relative_to(old_folder).as_posix(): path for path in files.values()}
            if (
                not required.issubset(relative)
                or guard["program_sha256"] != expected
                or _digest(relative["figure.py"]) != expected
                or report["script"]["sha256"] != expected
            ):
                raise ProjectError("Saved program differs from current canonical output.")
            if (
                _read(relative["runtime.report.json"]) != report
                or json.loads(relative["stdout.log"].read_text()) != report
            ):
                raise ProjectError("Saved runtime reports disagree.")
            if _outputs(report, old_folder, audit) != row["outputs"]:
                raise ProjectError("Prior export inventory differs.")
            origin = row["execution"].get("origin_event", previous["id"])
            original = self.events[origin]
            if (
                not original["integrity"]
                or original["result"]["exit_code"] != 0
                or self._row(original, identity)["report"] != report
                or self._row(original, identity)["execution"]["mode"] != "executed"
            ):
                raise ProjectError("Original execution ancestry is unavailable.")
            self._files(original, identity)
            payloads = {name: path.read_bytes() for name, path in relative.items()}
            for name, data in payloads.items():
                size, digest = self.checked_files[relative[name]]
                if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
                    raise ProjectError("Prior figure bytes changed while being copied.")
        except (OSError, ValueError, KeyError, StopIteration, TypeError, SpecError):
            return self._deny(
                identity,
                "Prior source/report/runtime/export/ancestry evidence is unavailable or changed.",
            )
        # Only verified explicit figure members enter a new owned directory.
        folder.mkdir(parents=True)
        for name, data in payloads.items():
            target = _inside(folder, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as handle:
                handle.write(data)
        reused = copy.deepcopy(row)
        reused["outputs"] = _outputs(report, folder, destination)
        reused["execution"] = {
            "mode": "reused",
            "source_event": previous["id"],
            "origin_event": origin,
            "original_report_sha256": _hash(report),
            "scope": "Copied intact accepted evidence; no new figure execution.",
        }
        self.reused += 1
        return reused

    def describe(self, report):
        for row in report["figures"]:
            row["execution"].setdefault(
                "reason", self.reasons.get(row["id"], "Intact accepted evidence matched.")
            )

    def finish(self, report):
        """Bind new inventories; recheck everything on which copied acceptance depended."""
        if self.reused:
            history = _inside(self.source.parent, "history")
            ids = {
                p.name
                for p in history.iterdir()
                if EVENT.fullmatch(p.name) and p.name != self.folder.name
            }
            if ids != set(self.events) or any(
                _digest(_inside(history, identity + "/receipt.json")) != digest
                for identity, digest in self.receipts.items()
            ):
                raise ProjectError("Prior history changed during selective auditing.")
            for path, (size, digest) in self.checked_files.items():
                if path.stat().st_size != size or _digest(path) != digest:
                    raise ProjectError("Reused source evidence changed during selective auditing.")
        after = _probe(self.folder)
        if self.reused and after != self.context:
            raise ProjectError("Rendering environment changed during selective auditing.")
        figures = {}
        for row in report["figures"]:
            if row["status"] != "passed" or "source_sha256" not in row:
                continue
            current = next(f for f in self.snapshot["figures"] if f["id"] == row["id"])
            if current["source_type"] != "spec":
                continue
            base = "audit/" + report["run_directory"] + "/figures/" + row["id"]
            names = {
                base + "/" + name
                for name in (
                    "figure.py",
                    "input.spec.json",
                    "runtime.report.json",
                    "stdout.log",
                    "stderr.log",
                )
            }
            names.update("audit/" + output["path"] for output in row["outputs"])
            inventory = [
                {
                    "path": name,
                    "bytes": _inside(self.folder, name).stat().st_size,
                    "sha256": _digest(_inside(self.folder, name)),
                }
                for name in sorted(names)
            ]
            figures[row["id"]] = {
                "program_sha256": row["report"]["script"]["sha256"],
                "files": inventory,
            }
        return {
            "schema_version": 1,
            "key": self.key if after == self.context else None,
            "environment": self.context,
            "environment_sha256": _hash(self.context) if self.context else None,
            "figure_policy": self.policy,
            "root": str(self.source.parent),
            "figures": figures,
            "scope": "Native spec inputs/current producer/observed environment/strict policy/intact evidence. Global baseline/change policies are evaluated anew. Package versions do not authenticate every external binary.",
        }


if __name__ == "__main__":
    if sys.argv[1:] != ["--context"]:
        raise SystemExit("Internal plotting context probe requires --context.")
    print(json.dumps(_environment(), sort_keys=True, allow_nan=False))
