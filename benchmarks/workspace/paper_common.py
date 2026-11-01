"""Owned copies of the fixed paper inputs and requests, with no numerical producer."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FIGURES = ("penguins-mass", "iris-measurements", "penguins-scatter", "iris-scatter")


def encoded(value):
    return (
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class Paper:
    """A new owned paper; the two Penguin entries really share all344 raw rows."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        if self.root.is_relative_to(ROOT) and not self.root.is_relative_to(
            HERE / "results"
        ):
            raise ValueError(
                "Keep owned evidence outside source or in workspace/results"
            )
        self.root.mkdir(parents=True, exist_ok=False)
        for name in ("inputs", "figures", "shared-inputs"):
            (self.root / name).mkdir()
        for source in (HERE / "inputs").glob("*.csv"):
            (self.root / "inputs" / source.name).write_bytes(source.read_bytes())
        raw = (ROOT / "benchmarks/papers/sources/penguins.csv").read_bytes()
        (self.root / "shared-inputs/penguins.csv").write_bytes(raw)
        self.entries = []
        for name in FIGURES:
            (self.root / "figures" / (name + ".json")).write_bytes(
                (HERE / "figures" / (name + ".json")).read_bytes()
            )
            entry = {"id": name, "spec": "figures/" + name + ".json"}
            if name.startswith("penguins-"):
                entry["data"] = "shared-inputs/penguins.csv"
            else:
                spec = json.loads(
                    (HERE / "figures" / (name + ".json")).read_text(encoding="utf8")
                )
                source = (HERE / "figures" / spec["data"]["path"]).resolve()
                entry["data"] = "shared-inputs/" + source.name
                (self.root / entry["data"]).write_bytes(source.read_bytes())
            self.entries.append(entry)
        self.dpi = {}
        self.save_manifest()

    def save_manifest(self):
        (self.root / "graphunslopify.json").write_bytes(
            encoded({"schema_version": 1, "figures": self.entries})
        )

    def source_spec(self, identity):
        entry = next(e for e in self.entries if e["id"] == identity)
        path = self.root / entry["spec"]
        return path, json.loads(path.read_text(encoding="utf8"))

    def specs(self):
        if json.loads(
            (self.root / "graphunslopify.json").read_text(encoding="utf8")
        ) != {"schema_version": 1, "figures": self.entries}:
            raise ValueError(
                "Owned task manifest changed outside the scripted operation"
            )
        result = {}
        for entry in self.entries:
            path, spec = self.source_spec(entry["id"])
            data = (
                (self.root / entry["data"])
                if "data" in entry
                else (path.parent / spec["data"]["path"])
            )
            spec["data"]["path"] = str(data.resolve())
            if entry["id"] in self.dpi:
                spec["output"]["dpi"] = self.dpi[entry["id"]]
            result[entry["id"]] = spec
        return result

    def edit(self, step):
        """Actual scripted source edits; selected-output review is arm-specific."""
        if step in {"title", "false-claim", "recover"}:
            path, spec = self.source_spec("penguins-mass")
            if step == "title":
                spec["title"] += " — reviewed paper"
            else:
                spec["claims"][0].update(
                    subject="female" if step == "false-claim" else "male",
                    reference="male" if step == "false-claim" else "female",
                )
            path.write_bytes(encoded(spec))
        elif step == "reencoded-data":
            path = self.root / "shared-inputs/penguins.csv"
            path.write_bytes(
                path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            )
        elif step == "add-alias":
            entry = copy.deepcopy(self.entries[0])
            entry["id"] = "penguins-mass-alias"
            self.entries.append(entry)
            self.save_manifest()
        elif step == "remove-alias":
            self.entries = [e for e in self.entries if e["id"] != "penguins-mass-alias"]
            self.save_manifest()
        elif step not in {"first", "unchanged", "selected-output"}:
            raise ValueError("Unknown frozen paper step")
