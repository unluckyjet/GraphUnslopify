"""Run actual installed CLI audits/comparison and prepare browser review fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    where = (
        args.work_dir or Path(tempfile.mkdtemp(prefix="gu-visual-comparison-"))
    ).resolve()
    if where.exists() and any(where.iterdir()):
        parser.error("choose a new or empty directory; existing evidence is preserved")
    where.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "GRAPHUNSLOPIFY_API": "local",
        "MPLBACKEND": "Agg",
        "PYTHONIOENCODING": "utf-8",
    }

    def command(*words, expected=0):
        result = subprocess.run(
            [args.python, "-m", "graphunslopify.cli", *map(str, words)],
            cwd=where,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf8",
            timeout=120,
            check=False,
        )
        if result.returncode != expected:
            raise RuntimeError(
                f"{words}: expected {expected}, got {result.returncode}\n{result.stdout}\n{result.stderr}"
            )
        return json.loads(result.stdout)

    data = where / "results.csv"
    data.write_text(
        "x,y,model\n1,1,base\n2,2,base\n1,4,ours\n2,5,ours\n", encoding="utf8"
    )
    spec = {
        "kind": "line",
        "data": {"path": "results.csv"},
        "x": {"field": "x", "label": "Training step"},
        "y": {"field": "y", "label": "Measured score"},
        "group": "model",
        "legend": {"show": False},
        "claims": [
            {"kind": "beats_everywhere", "subject": "ours", "reference": "base"}
        ],
        "output": {"stem": "training", "formats": ["png", "svg", "pdf"], "dpi": 100},
    }
    manifest = where / "graphunslopify.json"
    manifest.write_text(
        json.dumps(
            {"schema_version": 1, "figures": [{"id": "training", "spec": spec}]}
        ),
        encoding="utf8",
    )
    audit_dir = where / "audit"
    first = command("audit", manifest, "--out-dir", audit_dir)
    before = where / "before.json"
    before.write_bytes((audit_dir / "audit.report.json").read_bytes())
    data.write_text(
        data.read_text(encoding="utf8").replace("2,5,ours", "2,0,ours"), encoding="utf8"
    )
    second = command(
        "audit",
        manifest,
        "--out-dir",
        audit_dir,
        "--baseline",
        before,
        "--fail-on-change",
        expected=2,
    )
    packet = json.loads(
        (audit_dir / second["visual_comparison"]["report"]).read_text(encoding="utf8")
    )
    assert first["status"] == "passed" and second["status"] == "failed"
    assert packet["after_exit_code"] == 2 and packet["preview_status"] == "complete"
    assert packet["figures"][0]["metrics"]["visible_pixels_changed"] > 0
    evidence = {x["field"]: x for x in packet["figures"][0]["explanations"]}
    assert evidence["claims"]["before"][0]["verdict"] == "holds"
    assert evidence["claims"]["after"][0]["verdict"] == "fails"
    # Saved comparison must work after the dataset is unavailable.
    data.rename(where / "results.parked")
    standalone = command(
        "compare",
        before,
        audit_dir / "audit.report.json",
        "--out-dir",
        where / "standalone",
        expected=2,
    )
    assert (
        standalone["preview_status"] == "complete"
        and standalone["after_status"] == "failed"
    )
    # Passive SVG fixture: attempts at scripts/external images must not execute.
    synthetic = []
    for side in ["before", "after"]:
        root = where / f"svg-{side}"
        root.mkdir()
        path = root / "figure.svg"
        path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="60"><rect width="100" height="60" fill="'
            + ("red" if side == "before" else "blue")
            + '"/><script>window.top.__svg_ran=true;fetch("https://should-not-load.invalid/script")</script><image href="https://should-not-load.invalid/image" width="10" height="10"/></svg>',
            encoding="utf8",
        )
        base = {
            "schema_version": 1,
            "manifest": "synthetic",
            "artifact_root": str(root),
            "status": "passed",
            "counts": {"passed": 1, "failed": 0, "incomplete": 0},
            "policy": {
                "strict": True,
                "fail_on_change": False,
                "fail_on_warning": False,
            },
            "exit_code": 0,
            "comparison": None,
            "figures": [
                {
                    "id": "passive-svg",
                    "status": "passed",
                    "errors": [],
                    "warnings": [],
                    "report": {
                        "alt_text": "<img src=x onerror=alert(1)>"
                        if side == "before"
                        else "Updated text"
                    },
                    "artifacts": [],
                    "outputs": [
                        {
                            "path": "figure.svg",
                            "format": "svg",
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "bytes": path.stat().st_size,
                            "pixels_sha256": None,
                        }
                    ],
                }
            ],
        }
        source = where / f"{side}-svg.json"
        source.write_text(json.dumps(base), encoding="utf8")
        synthetic.append(source)
    svg_packet = command("compare", *synthetic, "--out-dir", where / "svg-review")
    assert svg_packet["figures"][0]["visual_status"] == "preview_only"
    print(
        json.dumps(
            {
                "status": "passed",
                "work_dir": str(where),
                "html": str(audit_dir / second["visual_comparison"]["html"]),
                "svg_html": str(where / "svg-review/index.html"),
                "exit_codes": [0, 2, 2],
                "changed_visible_pixels": packet["figures"][0]["metrics"][
                    "visible_pixels_changed"
                ],
            }
        )
    )


if __name__ == "__main__":
    main()
