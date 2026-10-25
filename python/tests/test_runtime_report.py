"""Validate real generated program evidence against the public JSON contract."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "docs/runtime-report.schema.json").read_text())


@pytest.mark.skipif(
    shutil.which("node") is None, reason="Node is needed to execute the real emitter"
)
@pytest.mark.parametrize(
    ("reference", "missing_file", "status", "exit_code"),
    [("base", False, "passed", 0), ("absent", False, "incomplete", 2), ("base", True, "failed", 1)],
)
def test_runtime_report_contract(tmp_path, reference, missing_file, status, exit_code):
    spec = {
        "kind": "line",
        "data": {"path": "missing.csv" if missing_file else "results.csv"},
        "x": {"field": "epoch", "label": "Epoch"},
        "y": {"field": "score", "label": "Score"},
        "group": "model",
        "aggregation": "mean",
        "legend": {"show": False},
        "claims": [{"kind": "beats_everywhere", "subject": "ours", "reference": reference}],
        "output": {"stem": "figure", "formats": ["png"], "dpi": 100},
    }
    generated = subprocess.run(
        [
            "node",
            "--experimental-strip-types",
            "--input-type=module",
            "-e",
            (
                "import {translate} from './src/translate.ts'; import fs from 'node:fs';"
                "process.stdout.write(translate(JSON.parse(fs.readFileSync(0,'utf8'))).code);"
            ),
        ],
        input=json.dumps(spec),
        text=True,
        capture_output=True,
        cwd=ROOT,
        check=True,
    )
    (tmp_path / "figure.py").write_text(generated.stdout)
    (tmp_path / "results.csv").write_text(
        "epoch,score,model\n1,1,base\n2,2,base\n1,4,ours\n2,5,ours\n"
    )
    completed = subprocess.run(
        [sys.executable, "figure.py", "--strict", "--json"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    report = json.loads(completed.stdout)
    Draft202012Validator.check_schema(SCHEMA)
    Draft202012Validator(SCHEMA).validate(report)
    assert report == json.loads((tmp_path / "figure.report.json").read_text())
    assert report["status"] == status
    assert report["exit_code"] == completed.returncode == exit_code
