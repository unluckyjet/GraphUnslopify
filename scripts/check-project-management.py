"""Exercise retained paper history and shared settings using the actual installed CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    where = (
        args.work_dir or Path(tempfile.mkdtemp(prefix="gu-project-check-"))
    ).resolve()
    if where.exists() and any(where.iterdir()):
        parser.error("choose a new/empty directory; existing evidence is preserved")
    where.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "GRAPHUNSLOPIFY_API": "local",
        "MPLBACKEND": "Agg",
        "PYTHONIOENCODING": "utf-8",
    }
    exits = []

    def command(*words, expected=0):
        done = subprocess.run(
            [sys.executable, "-m", "graphunslopify.cli", *map(str, words)],
            cwd=where,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf8",
            timeout=120,
            check=False,
        )
        exits.append(done.returncode)
        if done.returncode != expected:
            raise RuntimeError(
                f"{words}: expected {expected}, got {done.returncode}\n{done.stdout}\n{done.stderr}"
            )
        return json.loads(done.stdout)

    def inventory(root):
        return {
            p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*")
            if p.is_file()
        }

    paper = where / "paper ü with spaces"
    command("demo", paper, "--json")
    command("audit-init", paper)
    manifest_path = paper / "graphunslopify.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf8"))
    second = json.loads((paper / "figure.json").read_text(encoding="utf8"))
    second["title"] = "Second figure, same declared inputs"
    second["output"]["stem"] = "second"
    (paper / "second.json").write_text(json.dumps(second), encoding="utf8")
    manifest["figures"].append({"id": "second", "spec": "second.json"})
    manifest_path.write_text(json.dumps(manifest), encoding="utf8")
    sources = inventory(paper)
    folder = Path(command("project-init", paper)["config"]).parent
    assert command("project-status", folder)["status"] == "needs_audit"
    first = command("project-run", folder)
    assert first["status"] == "passed" and first["audit_status"] == "passed"
    old = Path(first["directory"])
    previous = inventory(old)
    state = command("project-status", folder)
    assert state["status"] == "inputs_match_last_run" and len(state["figures"]) == 2
    settings = where / "shared.json"
    settings.write_text(
        json.dumps(
            {"style": {"grid": True}, "output": {"size": "double_column", "dpi": 144}}
        ),
        encoding="utf8",
    )
    saved = command(
        "project-shared",
        folder,
        "--settings",
        settings,
        "--expected-revision",
        state["revision"],
    )
    assert saved["status"] == "settings_saved"
    rejected = command(
        "project-run", folder, "--expected-revision", state["revision"], expected=2
    )
    assert "changed since review" in str(rejected)
    state = command("project-status", folder)
    assert all(f["freshness"] == "changed" for f in state["figures"])
    updated = command("project-run", folder, "--expected-revision", state["revision"])
    assert (
        updated["baseline"] == first["id"] and updated["audit"]["comparison"]["changed"]
    )
    from PIL import Image

    for figure in updated["audit"]["figures"]:
        report = figure["report"]
        assert report["spec"]["style"]["grid"] is True
        assert report["spec"]["output"]["size"] == "double_column"
        output = next(item for item in figure["outputs"] if item["format"] == "png")
        path = Path(updated["directory"]) / "audit" / output["path"]
        embedded = command("provenance", path)["provenance"]
        assert embedded["spec"] == report["spec"]
        with Image.open(path) as image:
            assert abs(image.info["dpi"][0] - 144) < 0.02
            # Tight bounding boxes crop the canvas; check actual physical widening.
            original = next(
                f for f in first["audit"]["figures"] if f["id"] == figure["id"]
            )
            prior = next(
                item for item in original["outputs"] if item["format"] == "png"
            )
            with Image.open(
                Path(first["directory"]) / "audit" / prior["path"]
            ) as before:
                assert (
                    image.width / image.info["dpi"][0]
                    > 1.5 * before.width / before.info["dpi"][0]
                )
            rendering = report["environment"]["rendering"]
            assert rendering["figure_inches"][0] == rendering["target_width_in"] == 7
    path = paper / "figure.json"
    raw = path.read_bytes()
    wrong = json.loads(raw)
    wrong["claims"][0].update(subject="base", reference="ours")
    path.write_text(json.dumps(wrong), encoding="utf8")
    failed = command("project-run", folder, expected=2)
    assert failed["audit_status"] == "failed" and failed["status"] == "failed"
    statuses = {
        r["id"]: r["last_status"] for r in command("project-status", folder)["figures"]
    }
    assert (
        statuses[manifest["figures"][0]["id"]] == "failed"
        and statuses["second"] == "passed"
    )
    path.write_bytes(raw)
    assert command("project-status", folder)["status"] == "needs_audit"
    assert command("project-run", folder)["status"] == "passed"
    history = command("project-history", folder)
    assert history["integrity"] == "verified" and len(history["events"]) == 5
    assert previous == inventory(old) and not list(folder.rglob("*.csv"))
    current = inventory(paper)
    assert sources == {name: current[name] for name in sources}
    moved = where / "moved paper"
    shutil.copytree(paper, moved)
    assert command("project-status", moved)["status"] == "inputs_match_last_run"
    artifact = next(
        (
            moved
            / "graphunslopify-project/history"
            / history["events"][0]["id"]
            / "audit"
        ).rglob("*.png")
    )
    artifact.write_bytes(b"damaged")
    assert command("project-status", moved)["status"] == "needs_audit"
    assert command("project-status", folder)["status"] == "inputs_match_last_run"
    evidence = {
        "status": "passed",
        "figures": 2,
        "completed_events": 5,
        "first_record_unchanged": previous == inventory(old),
        "sources_unchanged": True,
        "moved_project_and_damaged_export_checked": True,
        "command_exits": exits,
        "work_dir": str(where),
    }
    (where / "checks.json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf8"
    )
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
