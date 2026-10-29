"""Install a built wheel in a fresh venv and exercise it outside the checkout."""

from __future__ import annotations

import argparse
import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile
import venv
from email.parser import BytesParser
from pathlib import Path
from zipfile import ZipFile


def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf8",
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"{command}:\n{completed.stdout}\n{completed.stderr}")
    return completed.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path, nargs="?")
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument(
        "--registry-version",
        help="install this exact version from public PyPI instead of the supplied wheel; require strict defaults",
    )
    parser.add_argument(
        "--keep-environment",
        action="store_true",
        help="retain the temporary venv for debugging",
    )
    parser.add_argument(
        "--agent",
        action="store_true",
        help="also install/test the optional stdio agent bridge",
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="also exercise optional manuscript PDF review",
    )
    parser.add_argument(
        "--require-environment",
        action="store_true",
        help="require current-source runtime environment provenance; older releases may omit it",
    )
    parser.add_argument(
        "--require-comparison",
        action="store_true",
        help="require current-source visual audit comparison; older releases may omit it",
    )
    parser.add_argument(
        "--require-workflow",
        action="store_true",
        help="require current-source research workspace integration; older releases may omit it",
    )
    parser.add_argument(
        "--tracking",
        action="store_true",
        help="install the tracking extra and retrieve real local MLflow audit evidence",
    )
    parser.add_argument(
        "--require-editor-controls",
        action="store_true",
        help="require current-source schema-backed editor assets; older releases may omit them",
    )
    parser.add_argument(
        "--require-project",
        action="store_true",
        help="require current-source project history and shared settings; older releases may omit them",
    )
    args = parser.parse_args()
    if args.wheel is None:
        candidates = list(Path("dist").glob("graphunslopify-*-py3-none-any.whl"))
        if len(candidates) != 1:
            parser.error("pass one wheel path, or build exactly one wheel in dist/")
        args.wheel = candidates[0]
    wheel = args.wheel.resolve()
    with ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "graphunslopify/_translator.mjs" in names
        assert "graphunslopify/ZOD-LICENSE.txt" in names
        assert any(name.endswith("/licenses/LICENSE") for name in names)
        metadata = BytesParser().parsebytes(
            archive.read(
                next(name for name in names if name.endswith(".dist-info/METADATA"))
            )
        )
        if args.registry_version and metadata["Version"] != args.registry_version:
            parser.error("registry version must match the supplied reference wheel")
    where = (args.work_dir or Path(tempfile.mkdtemp(prefix="gu-install-"))).resolve()
    where.mkdir(parents=True, exist_ok=True)
    virtual = where / "fresh environment"
    if virtual.exists():
        parser.error(
            "the test environment already exists; choose a fresh work directory"
        )
    if not args.keep_environment:
        atexit.register(shutil.rmtree, virtual, ignore_errors=True)
    venv.EnvBuilder(with_pip=True).create(virtual)
    python = virtual / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("GRAPHUNSLOPIFY_NODE", None)
    env["GRAPHUNSLOPIFY_API"] = "local"
    env["PYTHONIOENCODING"] = "utf-8"
    extra = ",".join(
        name
        for name, enabled in (
            ("agent", args.agent),
            ("pdf", args.pdf),
            ("tracking", args.tracking),
        )
        if enabled
    )
    extra = f"[{extra}]" if extra else ""
    requirement = (
        f"graphunslopify{extra}=={args.registry_version}"
        if args.registry_version
        else str(wheel) + extra
    )
    run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            requirement,
            *(
                ["--index-url", "https://pypi.org/simple"]
                if args.registry_version
                else []
            ),
        ],
        cwd=where,
        env=env,
    )

    # Block external calls after installation; asyncio may use local socket pairs.
    hooks = where / "offline hooks"
    hooks.mkdir()
    (hooks / "sitecustomize.py").write_text(
        "import socket, ipaddress\n"
        "def denied(*a, **k): raise RuntimeError('network disabled for installation smoke test')\n"
        "def local(host):\n"
        "    if host == 'localhost': return True\n"
        "    try: return ipaddress.ip_address(host).is_loopback\n"
        "    except ValueError: return False\n"
        "original_connect, original_ex = socket.socket.connect, socket.socket.connect_ex\n"
        "original_create = socket.create_connection\n"
        "def allowed(sock, address):\n"
        "    return local(address[0]) if isinstance(address, tuple) else sock.family == getattr(socket, 'AF_UNIX', None)\n"
        "def connect(sock, address):\n"
        "    return original_connect(sock, address) if allowed(sock, address) else denied()\n"
        "def connect_ex(sock, address):\n"
        "    return original_ex(sock, address) if allowed(sock, address) else denied()\n"
        "def create(address, *a, **k):\n"
        "    return original_create(address, *a, **k) if local(address[0]) else denied()\n"
        "socket.socket.connect, socket.socket.connect_ex = connect, connect_ex\n"
        "socket.create_connection = create\n",
        encoding="utf8",
    )
    node_hook = hooks / "offline.cjs"
    node_hook.write_text(
        "const denied = () => { throw new Error('network disabled for installation smoke test'); };\n"
        "require('node:net').Socket.prototype.connect = denied;\n"
        "require('node:http').request = denied; require('node:https').request = denied;\n"
        "require('node:dns').lookup = denied; globalThis.fetch = denied;\n",
        encoding="utf8",
    )
    env["PYTHONPATH"] = str(hooks)
    env["NODE_OPTIONS"] = "--require=" + json.dumps(node_hook.as_posix())
    env["MPLBACKEND"] = "Agg"
    env["MPLCONFIGDIR"] = str(where / "matplotlib")
    cli = [str(python), "-m", "graphunslopify.cli"]
    doctor = json.loads(run([*cli, "doctor"], cwd=where, env=env))
    assert doctor["ok"] and len(doctor["translator"]["kinds"]) == 21
    if args.registry_version:
        assert doctor["python_package"] == args.registry_version
    assert doctor["translator"]["node"].startswith(("v22.", "v24."))
    demo = where / "paper with spaces" / "data"
    report = json.loads(run([*cli, "demo", str(demo), "--json"], cwd=where, env=env))
    assert report["status"] == "passed" and report["policy"]["strict"]
    assert report["data"]["counts"]["read"] == 24
    assert report["data"]["counts"]["sample_sizes"] == [4] * 6
    assert report["claims"][0]["verdict"] == "holds"
    assert "ours is highest at 56.5" in report["alt_text"]
    if args.require_environment:
        assert report["environment"]["schema_version"] == 1
        assert report["environment"]["capture_stage"] == "before_export"
        assert report["environment"]["execution"]["strict"]
        assert report["environment"]["python"]["version"] == sys.version.split()[0]
    if args.registry_version:
        bad_spec = json.loads((demo / "figure.json").read_text())
        bad_spec["claims"] = [
            {"kind": "beats_everywhere", "subject": "base", "reference": "ours"}
        ]
        bad_spec["data"]["path"] = str(demo / "results.csv")
        bad = where / "false-claim.json"
        bad.write_text(json.dumps(bad_spec))
        rejected = subprocess.run(
            [
                *cli,
                "render",
                str(bad),
                "--out-dir",
                str(where / "default rejection"),
                "--json",
            ],
            cwd=where,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        verdict = json.loads(rejected.stdout)
        assert (
            rejected.returncode == 2
            and verdict["status"] == "failed"
            and verdict["policy"]["strict"]
        )
    if args.pdf:
        for prepare_only in (False, True):
            packet = where / ("pdf preparation" if prepare_only else "pdf strict")
            command = [
                *cli,
                "audit-pdf",
                str(demo / "figure.pdf"),
                "--pages",
                "1",
                "--out-dir",
                str(packet),
            ]
            result = subprocess.run(
                command + (["--prepare-only"] if prepare_only else []),
                cwd=where,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            evidence = json.loads(result.stdout)
            assert (
                result.returncode == evidence["exit_code"] == (0 if prepare_only else 2)
            ), result.stderr
            assert (
                evidence["status"] == "incomplete"
                and (packet / "pdf-review.html").is_file()
            )
            assert all(check["status"] == "untested" for check in evidence["checks"])
    for suffix in ("png", "svg", "pdf"):
        provenance = json.loads(
            run(
                [*cli, "provenance", str(demo / f"figure.{suffix}")], cwd=where, env=env
            )
        )
        assert provenance["ok"]
        if args.require_environment:
            assert provenance["provenance"]["environment"] == report["environment"]
        assert (
            provenance["provenance"]["data_sha256_prefix"]
            == report["data"]["sha256_prefix"]
        )
    # Derived survival needs no placeholder y column or optional SciPy runtime.
    (where / "survival.csv").write_text("time,event\n1,0\n1,1\n2,1\n", encoding="utf8")
    survival_spec = where / "survival.json"
    survival_spec.write_text(
        json.dumps(
            {
                "kind": "kaplan_meier",
                "data": {"path": "survival.csv"},
                "x": {"field": "time", "label": "Follow-up"},
                "y": {"field": "survival", "label": "Surviving fraction"},
                "event": "event",
                "legend": {"show": False},
                "output": {"stem": "survival", "formats": ["png", "svg"]},
            }
        ),
        encoding="utf8",
    )
    survival = json.loads(
        run(
            [
                *cli,
                "render",
                str(survival_spec),
                "--out-dir",
                str(where / "survival output"),
                "--strict",
                "--json",
            ],
            cwd=where,
            env=env,
        )
    )
    assert survival["status"] == "passed"
    assert survival["data"]["counts"]["read"] == 3
    assert (
        "3 observations" in survival["alt_text"] and "2 events" in survival["alt_text"]
    )
    assert "Median survival is 2" in survival["alt_text"]
    assert len(survival["outputs"]) == 2
    # Calibration likewise derives frequencies from probabilities/binary outcomes.
    (where / "calibration.csv").write_text(
        "prob,flag\n0.1,0\n0.2,1\n0.6,1\n0.9,0\n", encoding="utf8"
    )
    calibration_spec = where / "calibration.json"
    calibration_spec.write_text(
        json.dumps(
            {
                "kind": "calibration",
                "data": {"path": "calibration.csv"},
                "x": {"field": "prob", "label": "Predicted probability"},
                "y": {"field": "frequency", "label": "Observed frequency"},
                "outcome": "flag",
                "bins": 3,
                "legend": {"show": False},
                "output": {"stem": "calibration", "formats": ["png", "svg"]},
            }
        ),
        encoding="utf8",
    )
    calibration = json.loads(
        run(
            [
                *cli,
                "render",
                str(calibration_spec),
                "--out-dir",
                str(where / "calibration output"),
                "--strict",
                "--json",
            ],
            cwd=where,
            env=env,
        )
    )
    assert (
        calibration["status"] == "passed" and calibration["data"]["counts"]["read"] == 4
    )
    assert "expected calibration error is 0.5" in calibration["alt_text"]
    assert "4 observations in 3 of 3 bins" in calibration["alt_text"]
    assert len(calibration["outputs"]) == 2
    (where / "paired.csv").write_text(
        "unit,condition,score\nA,base,10\nA,new,14\nB,base,20\nB,new,26\nC,base,100\nD,new,1000\n",
        encoding="utf8",
    )
    paired_spec = where / "paired.json"
    paired_spec.write_text(
        json.dumps(
            {
                "kind": "paired_difference",
                "data": {"path": "paired.csv"},
                "x": {"field": "condition", "label": "Condition"},
                "y": {"field": "score", "label": "Score"},
                "pair": "unit",
                "baseline": "base",
                "legend": {"show": False},
                "output": {"stem": "paired", "formats": ["png", "svg"]},
            }
        ),
        encoding="utf8",
    )
    paired = json.loads(
        run(
            [
                *cli,
                "render",
                str(paired_spec),
                "--out-dir",
                str(where / "paired output"),
                "--strict",
                "--json",
            ],
            cwd=where,
            env=env,
        )
    )
    assert paired["status"] == "passed"
    assert "mean difference is 5 over 2 matched pairs" in paired["alt_text"]
    comparison = paired["data"]["counts"]["pairing"][0]
    assert comparison["n"] == 2 and comparison["mean"] == 5
    assert comparison["baseline_only"] == 1 and comparison["candidate_only"] == 1
    assert len(paired["outputs"]) == 2
    (where / "qq.csv").write_text("value\n1\n2\n3\n4\n", encoding="utf8")
    qq_spec = where / "qq.json"
    qq_spec.write_text(
        json.dumps(
            {
                "kind": "qq",
                "data": {"path": "qq.csv"},
                "x": {"field": "theory", "label": "Theoretical quantile"},
                "y": {"field": "value", "label": "Sample quantile"},
                "legend": {"show": False},
                "output": {"stem": "qq", "formats": ["png", "svg"]},
            }
        ),
        encoding="utf8",
    )
    qq = json.loads(
        run(
            [
                *cli,
                "render",
                str(qq_spec),
                "--out-dir",
                str(where / "qq output"),
                "--strict",
                "--json",
            ],
            cwd=where,
            env=env,
        )
    )
    assert qq["status"] == "passed" and "normal" in qq["alt_text"]
    sample = qq["data"]["counts"]["qq"][0]
    assert sample["observations"] == 4 and sample["median"] == 2.5
    assert sample["q1"] == 1.75 and sample["q3"] == 3.25
    assert sample["reference_line"] == "population_quartiles"
    assert len(qq["outputs"]) == 2
    # The core wheel has no SciPy: explicit point fits work and requested CIs stay unknown.
    scipy_present = run(
        [
            str(python),
            "-c",
            "import importlib.util; print(importlib.util.find_spec('scipy') is not None)",
        ],
        cwd=where,
        env=env,
    ).strip()
    assert scipy_present == "False", (
        "base installation unexpectedly includes the optional statistics dependency"
    )
    (where / "scaling.csv").write_text("scale,loss\n1,3\n2,6\n", encoding="utf8")
    scaling_spec = where / "scaling.json"
    point_spec = {
        "kind": "scaling_fit",
        "interval": "none",
        "show_points": False,
        "data": {"path": "scaling.csv"},
        "legend": {"show": False},
        "x": {"field": "scale", "label": "Scale", "scale": "log"},
        "y": {"field": "loss", "label": "Loss", "scale": "log"},
        "output": {"stem": "scaling", "formats": ["png", "svg"]},
    }
    scaling_spec.write_text(json.dumps(point_spec), encoding="utf8")
    point_fit = json.loads(
        run(
            [
                *cli,
                "render",
                str(scaling_spec),
                "--out-dir",
                str(where / "point fit"),
                "--strict",
                "--json",
            ],
            cwd=where,
            env=env,
        )
    )
    assert point_fit["status"] == "passed" and len(point_fit["outputs"]) == 2
    actual = point_fit["data"]["counts"]["scaling_fits"][0]
    assert abs(actual["slope"] - 1) < 1e-12 and actual["stderr"] is None
    assert actual["interval"]["status"] == "not_requested"
    (where / "scaling.csv").write_text(
        "scale,loss\n1,1\n10,10\n100,1000\n", encoding="utf8"
    )
    point_spec["interval"] = "t95"
    scaling_spec.write_text(json.dumps(point_spec), encoding="utf8")
    missing = subprocess.run(
        [
            *cli,
            "render",
            str(scaling_spec),
            "--out-dir",
            str(where / "requested interval"),
            "--strict",
            "--json",
        ],
        cwd=where,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf8",
        check=False,
    )
    unknown = json.loads(missing.stdout)
    assert missing.returncode == 2 and unknown["status"] == "incomplete"
    interval = unknown["data"]["counts"]["scaling_fits"][0]["interval"]
    assert interval["low"] is None and interval["status"] == "unavailable"
    assert "statistics" in interval["reason"] and unknown["outputs"]
    # Installed source must preserve lexical cohort IDs and verify the actual comparison.
    (where / "identifiers.csv").write_text(
        "step,score,model\n1,10,01\n2,12,01\n1,20,1\n2,22,1\n", encoding="utf8"
    )
    identity_spec = where / "identifiers.json"
    identity_spec.write_text(
        json.dumps(
            {
                "kind": "line",
                "data": {"path": "identifiers.csv"},
                "x": {"field": "step", "label": "Step"},
                "y": {"field": "score", "label": "Score"},
                "group": "model",
                "series_order": ["1", "01"],
                "legend": {"position": "outside_bottom"},
                "claims": [
                    {"kind": "beats_everywhere", "subject": "1", "reference": "01"}
                ],
                "output": {"stem": "identifiers", "formats": ["png", "svg"]},
            }
        ),
        encoding="utf8",
    )
    identity_dir = where / "identity output"
    identity = json.loads(
        run(
            [
                *cli,
                "render",
                str(identity_spec),
                "--out-dir",
                str(identity_dir),
                "--strict",
                "--json",
            ],
            cwd=where,
            env=env,
        )
    )
    assert (
        identity["status"] == "passed" and identity["claims"][0]["verdict"] == "holds"
    )
    assert identity["data"]["counts"]["read"] == 4 and len(identity["outputs"]) == 2
    # Extract real marks from the installed emitter, independently of its claim narrative.
    driver = identity_dir / "artists.py"
    driver.write_text(
        "import identifiers, matplotlib.pyplot as plt, json\n"
        "frame = identifiers.prepare(identifiers.load())\n"
        "fig, ax = plt.subplots(); identifiers.draw_panel(ax, frame)\n"
        "print(json.dumps([[line.get_label(), list(map(float,line.get_ydata()))] for line in ax.lines]))\n"
        "plt.close(fig)\n",
        encoding="utf8",
    )
    artists = json.loads(run([str(python), str(driver)], cwd=identity_dir, env=env))
    assert artists == [["1", [20, 22]], ["01", [10, 12]]]
    # The installed translator and inspector must both honor actual cell colours.
    (where / "cells.csv").write_text(
        "column,row,value\n01,a,1\n1,a,2\n01,b,3\n1,b,4\n", encoding="utf8"
    )
    cell_spec = where / "cells.json"
    cell_spec.write_text(
        json.dumps(
            {
                "kind": "heatmap",
                "data": {"path": "cells.csv"},
                "x": {"field": "column", "label": "Column"},
                "y": {"field": "row", "label": "Row"},
                "value": "value",
                "value_label": "Value",
                "annotate_cells": True,
                "output": {"stem": "cells", "formats": ["png", "svg"]},
            }
        ),
        encoding="utf8",
    )
    cell_dir = where / "cell output"
    cell_report = json.loads(
        run(
            [
                *cli,
                "render",
                str(cell_spec),
                "--out-dir",
                str(cell_dir),
                "--strict",
                "--json",
            ],
            cwd=where,
            env=env,
        )
    )
    assert cell_report["status"] == "passed" and len(cell_report["outputs"]) == 2
    physical = cell_report["inspection"]["measurements"]
    assert physical["basis"] == "exports" and len(physical["widths_in"]) == 2
    assert physical["evaluated_width_in"] == max(physical["widths_in"].values())
    # A nominally readable canvas can export too wide for the requested column.
    wide_spec = where / "wide-title.json"
    wide = json.loads(cell_spec.read_text(encoding="utf8"))
    wide["title"] = "A very long scientific title " * 8
    wide["output"]["stem"] = "wide-title"
    wide_spec.write_text(json.dumps(wide), encoding="utf8")
    too_wide = subprocess.run(
        [
            *cli,
            "render",
            str(wide_spec),
            "--out-dir",
            str(where / "wide output"),
            "--strict",
            "--json",
        ],
        cwd=where,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf8",
        check=False,
    )
    rejected_width = json.loads(too_wide.stdout)
    assert too_wide.returncode == 2 and rejected_width["status"] == "failed"
    assert rejected_width["inspection"]["measurements"]["text_scale"] < 0.5
    assert any(f["code"] == "text_too_small" for f in rejected_width["findings"])
    assert len(rejected_width["outputs"]) == 2
    driver = cell_dir / "cell_artists.py"
    driver.write_text(
        "import cells, matplotlib.pyplot as plt, matplotlib.colors as colors, json\n"
        "from graphunslopify import inspect_figure\n"
        "fig, ax = plt.subplots(); cells.draw_panel(ax, cells.prepare(cells.load()))\n"
        "image = ax.images[0]; ratios = []\n"
        "def luminance(rgb):\n"
        "    v = [c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4 for c in rgb]\n"
        "    return sum(c*w for c,w in zip(v,[.2126,.7152,.0722]))\n"
        "for text in ax.texts:\n"
        "    column,row = map(int,text.get_position())\n"
        "    a,b = sorted([luminance(colors.to_rgb(text.get_color())),\n"
        "                  luminance(image.to_rgba(image.get_array()[row,column])[:3])])\n"
        "    ratios.append((b+.05)/(a+.05))\n"
        "ax.texts[0].set_color(image.to_rgba(image.get_array()[0,0]))\n"
        "bad = [f.code for f in inspect_figure(fig).findings if f.code == 'cell_text_low_contrast']\n"
        "print(json.dumps({'ratios':ratios,'negative':bad})); plt.close(fig)\n",
        encoding="utf8",
    )
    cell_artists = json.loads(run([str(python), str(driver)], cwd=cell_dir, env=env))
    assert len(cell_artists["ratios"]) == 4 and min(cell_artists["ratios"]) >= 4.5
    assert cell_artists["negative"] == ["cell_text_low_contrast"]
    overlay_spec = where / "overlay.json"
    overlay_spec.write_text(
        json.dumps(
            {
                "kind": "bar",
                "aggregation": "mean",
                "data": {"path": "cells.csv"},
                "x": {"field": "column", "label": "Category"},
                "y": {"field": "value", "label": "Value"},
                "category_order": ["1", "01"],
                "legend": {"show": False},
                "layers": [
                    {"mark": "line", "y": "value", "label": "Raw", "recede": False}
                ],
                "output": {"stem": "overlay", "formats": ["png", "svg"]},
            }
        ),
        encoding="utf8",
    )
    overlay_dir = where / "overlay output"
    overlay_report = json.loads(
        run(
            [
                *cli,
                "render",
                str(overlay_spec),
                "--out-dir",
                str(overlay_dir),
                "--strict",
                "--json",
            ],
            cwd=where,
            env=env,
        )
    )
    assert overlay_report["status"] == "passed" and len(overlay_report["outputs"]) == 2
    driver = overlay_dir / "overlay_artists.py"
    driver.write_text(
        "import overlay, matplotlib.pyplot as plt, json\n"
        "frame = overlay.prepare(overlay.load())\n"
        "fig, ax = plt.subplots(); overlay.draw_panel(ax, frame); overlay.draw_layers(ax, frame)\n"
        "print(json.dumps({'x':list(map(float,ax.lines[-1].get_xdata(orig=False))),\n"
        "                  'y':list(map(float,ax.lines[-1].get_ydata())),\n"
        "                  'labels':[t.get_text() for t in ax.get_xticklabels()]}))\n"
        "plt.close(fig)\n",
        encoding="utf8",
    )
    overlay_artists = json.loads(
        run([str(python), str(driver)], cwd=overlay_dir, env=env)
    )
    assert overlay_artists == {
        "x": [0, 0, 1, 1],
        "y": [2, 4, 1, 3],
        "labels": ["1", "01"],
    }
    # Shared categories must remain associated with actual values without overlays.
    (where / "shared.csv").write_text(
        "category,value,site\nB,30,first\n01,10,first\n1,20,second\n01,11,second\n",
        encoding="utf8",
    )
    shared_spec = where / "shared.json"
    shared_spec.write_text(
        json.dumps(
            {
                "kind": "bar",
                "data": {"path": "shared.csv"},
                "x": {"field": "category", "label": "Category"},
                "y": {"field": "value", "label": "Value"},
                "aggregation": "mean",
                "legend": {"show": False},
                "facet": {"by": "site", "columns": 1, "share_x": True, "share_y": True},
                "output": {
                    "stem": "shared",
                    "formats": ["png"],
                    "size": "double_column",
                },
            }
        ),
        encoding="utf8",
    )
    shared_dir = where / "shared output"
    shared_report = json.loads(
        run(
            [
                *cli,
                "render",
                str(shared_spec),
                "--out-dir",
                str(shared_dir),
                "--strict",
                "--json",
            ],
            cwd=where,
            env=env,
        )
    )
    assert shared_report["status"] == "passed" and len(shared_report["outputs"]) == 1
    driver = shared_dir / "shared_artists.py"
    driver.write_text(
        "import shared, matplotlib.pyplot as plt, json, contextlib, io, math\n"
        "captured=[]; close=plt.close; plt.close=captured.append\n"
        "with contextlib.redirect_stdout(io.StringIO()): shared.main()\n"
        "fig=captured[-1]\n"
        "print(json.dumps({'labels': fig.axes[-1].xaxis.get_major_formatter().format_ticks(fig.axes[-1].get_xticks()),\n"
        "'bars': [[[p.get_x()+p.get_width()/2,p.get_height()] for p in ax.patches if math.isfinite(p.get_height())] for ax in fig.axes]}))\n"
        "plt.close=close; close(fig)\n",
        encoding="utf8",
    )
    shared_artists = json.loads(
        run([str(python), str(driver)], cwd=shared_dir, env=env)
    )
    assert shared_artists == {
        "labels": ["B", "01", "1"],
        "bars": [[[0, 30], [1, 10]], [[1, 11], [2, 20]]],
    }
    # Negative/percent bar magnitudes must survive export; clipped lengths fail strict.
    (where / "signed.csv").write_text(
        "category,value\nB,-0.02\n01,0.08\n", encoding="utf8"
    )
    signed_raw = {
        "kind": "bar",
        "data": {"path": "signed.csv"},
        "x": {"field": "category", "label": "Category"},
        "y": {"field": "value", "label": "Change", "percent": True},
        "aggregation": "mean",
        "value_labels": True,
        "output": {"stem": "signed", "formats": ["png"], "size": "double_column"},
    }
    signed_spec = where / "signed.json"
    signed_spec.write_text(json.dumps(signed_raw), encoding="utf8")
    signed_dir = where / "signed output"
    signed_report = json.loads(
        run(
            [
                *cli,
                "render",
                str(signed_spec),
                "--out-dir",
                str(signed_dir),
                "--strict",
                "--json",
            ],
            cwd=where,
            env=env,
        )
    )
    assert (
        signed_report["status"] == "passed" and signed_report["inspection"]["checked"]
    )
    driver = signed_dir / "signed_artists.py"
    driver.write_text(
        "import signed, matplotlib.pyplot as plt, json, contextlib, io\n"
        "captured=[]; close=plt.close; plt.close=captured.append\n"
        "with contextlib.redirect_stdout(io.StringIO()): signed.main()\n"
        "fig=captured[-1]; ax=fig.axes[0]\n"
        "print(json.dumps({'limits': ax.get_ylim(), 'heights': [p.get_height() for p in ax.patches],\n"
        "'labels': [t.get_text() for t in ax.texts]}))\n"
        "plt.close=close; close(fig)\n",
        encoding="utf8",
    )
    signed_artists = json.loads(
        run([str(python), str(driver)], cwd=signed_dir, env=env)
    )
    assert signed_artists["limits"][0] <= -0.02 and signed_artists["limits"][1] >= 0.08
    assert signed_artists["heights"] == [-0.02, 0.08] and signed_artists["labels"] == [
        "-2%",
        "8%",
    ]
    signed_raw["y"]["limits"] = [-0.01, 0.1]
    signed_spec.write_text(json.dumps(signed_raw), encoding="utf8")
    clipped = subprocess.run(
        [
            *cli,
            "render",
            str(signed_spec),
            "--out-dir",
            str(where / "clipped output"),
            "--strict",
            "--json",
        ],
        cwd=where,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    clipped_report = json.loads(clipped.stdout)
    assert clipped.returncode == 2 and clipped_report["status"] == "failed"
    assert clipped_report["outputs"] and any(
        f["code"] == "bar_mark_clipped" for f in clipped_report["findings"]
    )
    (where / "context.csv").write_text(
        "dataset,method,score\nA,Base,0.2\nA,Base,0.3\nA,Ours,0.8\nA,Ours,0.9\n",
        encoding="utf8",
    )
    context_spec = where / "table-context.json"
    context_spec.write_text(
        json.dumps(
            {
                "kind": "table",
                "title": "Installed table context",
                "data": {"path": "context.csv"},
                "x": {"field": "dataset", "label": "Dataset"},
                "y": {
                    "field": "score",
                    "label": "Accuracy",
                    "unit": "%",
                    "percent": True,
                },
                "group": "method",
                "uncertainty": {"kind": "range"},
                "highlight": "best_per_row",
                "output": {
                    "stem": "context",
                    "formats": ["png", "pdf"],
                    "size": "double_column",
                },
            }
        ),
        encoding="utf8",
    )
    context_dir = where / "table context output"
    context_report = json.loads(
        run(
            [
                *cli,
                "render",
                str(context_spec),
                "--out-dir",
                str(context_dir),
                "--strict",
                "--json",
            ],
            cwd=where,
            env=env,
        )
    )
    assert context_report["status"] == "passed" and len(context_report["outputs"]) == 4
    assert context_report["inspection"]["measurements"]["basis"] == "exports"
    markdown = (context_dir / "context.md").read_text(encoding="utf8")
    assert "Installed table context" in markdown and "Accuracy (%)" in markdown
    assert "**85.00% [80.00%, 90.00%]**" in markdown
    driver = context_dir / "context_text.py"
    driver.write_text(
        "from pypdf import PdfReader\n"
        "text = ''.join(p.extract_text() for p in PdfReader('context.pdf').pages)\n"
        "compact = ''.join(text.split())\n"
        "assert 'Installedtablecontext' in compact and 'Dataset' in compact\n"
        "assert 'Accuracy(%)' in compact and '85.00%[80.00%,90.00%]' in compact\n"
        "print('installed visible table context passed')\n",
        encoding="utf8",
    )
    run([str(python), str(driver)], cwd=context_dir, env=env)
    # A raw table must not silently average duplicate cells from the installed emitter.
    duplicate_raw = json.loads(context_spec.read_text(encoding="utf8"))
    duplicate_raw["aggregation"] = "none"
    duplicate_raw.pop("uncertainty")
    context_spec.write_text(json.dumps(duplicate_raw), encoding="utf8")
    duplicate = subprocess.run(
        [
            *cli,
            "render",
            str(context_spec),
            "--out-dir",
            str(where / "duplicate cells"),
            "--strict",
            "--json",
        ],
        cwd=where,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    duplicate_report = json.loads(duplicate.stdout)
    assert duplicate.returncode == 1 and duplicate_report["status"] == "failed", (
        duplicate.returncode,
        duplicate_report,
    )
    assert any(
        "Duplicate table cell" in f["message"] for f in duplicate_report["findings"]
    )
    driver = where / "group_refusal.py"
    driver.write_text(
        "from graphunslopify.transport import local_request\n"
        "r=local_request('convert', {'kind':'forest','data':{'path':'absent.csv'},\n"
        "'x':{'field':'category','label':'Category'},'y':{'field':'value','label':'Value'},\n"
        "'group':'method','uncertainty':{'kind':'range'}})\n"
        "assert not r['ok'] and any(f['code']=='unsupported_grouping' for f in r['findings'])\n"
        "ns={'__name__':'refused','__file__':'refused.py'}; exec(r['code'],ns)\n"
        "try: ns['main']()\n"
        "except ValueError as problem: assert 'Unsupported grouping' in str(problem)\n"
        "else: raise AssertionError('refused projection ran')\n"
        "print('installed grouping refusal passed')\n",
        encoding="utf8",
    )
    run([str(python), str(driver)], cwd=where, env=env)
    density_spec = where / "density.json"
    density_spec.write_text(
        json.dumps(
            {
                "kind": "ridgeline",
                "data": {"path": "density.csv"},
                "x": {"field": "category", "label": "Category"},
                "y": {"field": "value", "label": "Measurement"},
                "legend": {"show": False},
                "output": {
                    "stem": "density",
                    "formats": ["png"],
                    "size": "double_column",
                },
            }
        ),
        encoding="utf8",
    )
    (where / "density.csv").write_text(
        "category,value\nA,0\nA,1\nA,2\n", encoding="utf8"
    )
    density = json.loads(
        run(
            [
                *cli,
                "render",
                str(density_spec),
                "--out-dir",
                str(where / "density normal"),
                "--strict",
                "--json",
            ],
            cwd=where,
            env=env,
        )
    )
    record = density["data"]["counts"]["densities"][0]
    assert (
        density["status"] == "passed"
        and record["status"] == "available"
        and record["n"] == 3
    )
    assert abs(record["bandwidth"] - 0.9 / 1.349 * 3 ** (-0.2)) < 1e-12
    (where / "density.csv").write_text(
        "category,value\nA,5\nA,5\nA,5\n", encoding="utf8"
    )
    density_dir = where / "density unavailable"
    unavailable = subprocess.run(
        [
            *cli,
            "render",
            str(density_spec),
            "--out-dir",
            str(density_dir),
            "--strict",
            "--json",
        ],
        cwd=where,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    unknown = json.loads(unavailable.stdout)
    record = unknown["data"]["counts"]["densities"][0]
    assert unavailable.returncode == 2 and unknown["status"] == "incomplete"
    assert unknown["outputs"] and record["bandwidth"] is None and record["n"] == 3
    assert "density unavailable" in unknown["alt_text"].lower()
    driver = density_dir / "density_artists.py"
    driver.write_text(
        "import density, matplotlib.pyplot as plt, contextlib, io, json\n"
        "captured=[]; close=plt.close; plt.close=captured.append\n"
        "with contextlib.redirect_stdout(io.StringIO()): density.main()\n"
        "fig=captured[-1]; ax=fig.axes[0]\n"
        "points=[list(map(float,line.get_xdata())) for line in ax.lines if line.get_marker()=='|']\n"
        "assert points==[[5.,5.,5.]] and min(ax.get_xlim())<=5<=max(ax.get_xlim())\n"
        "assert any('density unavailable' in t.get_text().lower() for t in ax.texts)\n"
        "plt.close=close; close(fig); print('installed unavailable density retains observations')\n",
        encoding="utf8",
    )
    run([str(python), str(driver)], cwd=density_dir, env=env)
    driver = where / "sem_estimator.py"
    driver.write_text(
        "from graphunslopify.transport import local_request\n"
        "import pandas as pd, math\n"
        "frame=pd.DataFrame({'category':[1]*3,'value':[1,2,9]})\n"
        "base={'kind':'table','data':{'path':'unused.csv'},'x':{'field':'category','label':'Category'},\n"
        "'y':{'field':'value','label':'Value'},'aggregation':'mean','uncertainty':{'kind':'sem'}}\n"
        "def module(raw):\n"
        "    r=local_request('convert',raw); ns={'__name__':'estimator','__file__':'estimator.py'}; exec(r['code'],ns); return r,ns\n"
        "r,m=module(base); assert r['ok']; row=m['summarise'](frame).iloc[0]\n"
        "assert row['value']==4 and abs(row['_low']-(4-math.sqrt(19/3)))<1e-12\n"
        "base['aggregation']='median'; r,m=module(base)\n"
        "assert not r['ok'] and any(f['code']=='median_sem_unsupported' for f in r['findings'])\n"
        "try: m['summarise'](frame)\n"
        "except ValueError as problem: assert 'SEM' in str(problem) and 'mean' in str(problem)\n"
        "else: raise AssertionError('median received mean SEM')\n"
        "base['uncertainty']['kind']='ci'; r,m=module(base); assert r['ok']; row=m['summarise'](frame).iloc[0]\n"
        "assert row['value']==2 and row['_low']==1 and row['_high']==9\n"
        "print('installed estimator-specific uncertainty passed')\n",
        encoding="utf8",
    )
    run([str(python), str(driver)], cwd=where, env=env)
    (where / "cohorts.csv").write_text(
        "step,value,method,site\n1,3,1,first\n2,4,1,first\n1,1,01,second\n2,2,01,second\n1,3,1,second\n2,4,1,second\n",
        encoding="utf8",
    )
    cohorts_spec = where / "cohorts.json"
    cohorts_spec.write_text(
        json.dumps(
            {
                "kind": "line",
                "data": {"path": "cohorts.csv"},
                "x": {"field": "step", "label": "Step"},
                "y": {"field": "value", "label": "Value"},
                "group": "method",
                "aggregation": "mean",
                "series_order": ["01", "1"],
                "facet": {"by": "site", "columns": 2},
                "legend": {"position": "outside_bottom"},
                "output": {
                    "stem": "cohorts",
                    "formats": ["png"],
                    "size": "double_column",
                },
            }
        ),
        encoding="utf8",
    )
    cohorts_dir = where / "cohort styles"
    cohorts = json.loads(
        run(
            [
                *cli,
                "render",
                str(cohorts_spec),
                "--out-dir",
                str(cohorts_dir),
                "--strict",
                "--json",
            ],
            cwd=where,
            env=env,
        )
    )
    assert cohorts["status"] == "passed" and cohorts["inspection"]["checked"]
    driver = cohorts_dir / "cohort_artists.py"
    driver.write_text(
        "import cohorts, matplotlib.pyplot as plt, contextlib, io\n"
        "captured=[]; close=plt.close; plt.close=captured.append\n"
        "with contextlib.redirect_stdout(io.StringIO()): cohorts.main()\n"
        "fig=captured[-1]; first,second=fig.axes\n"
        "def lines(ax): return {line.get_label():line for line in ax.lines if line.get_label() in {'01','1'}}\n"
        "a,b=lines(first),lines(second)\n"
        "assert a['1'].get_color()==b['1'].get_color() and a['1'].get_linestyle()==b['1'].get_linestyle()\n"
        "assert list(a['1'].get_ydata())==[3,4] and list(b['01'].get_ydata())==[1,2]\n"
        "assert [t.get_text() for t in first.get_legend().get_texts()]==['01','1']\n"
        "assert second.get_legend() is None\n"
        "plt.close=close; close(fig); print('installed shared series identity passed')\n",
        encoding="utf8",
    )
    run([str(python), str(driver)], cwd=cohorts_dir, env=env)
    driver = where / "bar_intervals.py"
    driver.write_text(
        "from graphunslopify.transport import local_request\n"
        "from graphunslopify.inspect import inspect_figure\n"
        "import pandas as pd, matplotlib.pyplot as plt\n"
        "from matplotlib.container import BarContainer\n"
        "base={'kind':'bar','data':{'path':'unused.csv'},'x':{'field':'category','label':'Category'},\n"
        "'y':{'field':'value','label':'Value'},'aggregation':'median','uncertainty':{'kind':'ci'}}\n"
        "def module(raw):\n"
        "    r=local_request('convert',raw); ns={'__name__':'bounds','__file__':'bounds.py'}; exec(r['code'],ns); return r,ns\n"
        "r,m=module(base); assert r['ok']; fig,ax=plt.subplots()\n"
        "m['draw_panel'](ax,pd.DataFrame({'category':['A']*3,'value':[1,2,9]}))\n"
        "bar=next(c for c in ax.containers if isinstance(c,BarContainer))\n"
        "assert list(bar.errorbar.lines[2][0].get_segments()[0][:,1])==[1,9]\n"
        "ax.set_ylim(0,5); assert any(f.code=='bar_interval_clipped' for f in inspect_figure(fig).findings)\n"
        "base['aggregation']='mean'; base['uncertainty']['kind']='iqr'; r,m=module(base)\n"
        "try: m['draw_panel'](ax,pd.DataFrame({'category':['A']*5,'value':[0,0,0,0,100]}))\n"
        "except ValueError as problem: assert 'bounds exclude the estimate' in str(problem)\n"
        "else: raise AssertionError('detached bar interval was reflected')\n"
        "base.update(stacked=True,group='method'); r,m=module(base)\n"
        "assert not r['ok'] and any(f['code']=='stacked_uncertainty_unsupported' for f in r['findings'])\n"
        "plt.close('all'); print('installed true bar bounds, clipping and stacked refusal passed')\n",
        encoding="utf8",
    )
    run([str(python), str(driver)], cwd=where, env=env)
    driver = where / "core_references.py"
    driver.write_text(
        "from graphunslopify.transport import local_request\n"
        "import pandas as pd, numpy as np, matplotlib.pyplot as plt\n"
        "base={'data':{'path':'unused.csv'},'x':{'field':'category','label':'Category'},'y':{'field':'value','label':'Value'}}\n"
        "def module(**extra):\n"
        "    r=local_request('convert',{**base,**extra}); assert r['ok'],r\n"
        "    ns={'__name__':'core','__file__':'core.py'}; exec(r['code'],ns); return ns\n"
        "m=module(kind='waterfall',start=10,category_order=['add','remove'])\n"
        "frame=m['prepare'](pd.DataFrame({'category':['add','add','remove'],'value':[2,3,-1]}))\n"
        "assert list(m['waterfall_estimate'](frame)[2])==[10,15,14]\n"
        "assert 'final total 14' in m['describe_figure'](frame).lower() and 'add: +5' in m['describe_figure'](frame).lower()\n"
        "m=module(kind='bar',aggregation='sum')\n"
        "frame=m['prepare'](pd.DataFrame({'category':pd.Categorical(['A'],categories=['A','unused']),'value':[3]}))\n"
        "assert m['summarise'](frame)['category'].tolist()==['A']\n"
        "m=module(kind='table',aggregation='sum')\n"
        "frame=m['prepare'](pd.DataFrame({'category':['missing','zero'],'value':[np.nan,0]}))\n"
        "table,lo,hi=m['build_table'](frame); assert m['table_cell'](table,lo,hi,'missing','value')=='-' and table.loc['zero','value']==0\n"
        "m=module(kind='sparkline_grid',group='method',x={'field':'category','label':'Category','scale':'log'})\n"
        "frame=m['prepare'](pd.DataFrame({'category':[1,2,10,20],'value':[1,2,10,20],'method':['a','a','b','b']}))\n"
        "fig,ax=plt.subplots(); m['draw_panel'](ax,frame); m['decorate_panel'](ax,frame,None,True,True)\n"
        "a,b=ax.child_axes; assert a.get_xlim()==b.get_xlim() and a.get_ylim()==b.get_ylim()\n"
        "assert a.get_xscale()==b.get_xscale()=='log' and ax.axison and ax.get_xlabel()=='Category'\n"
        "m=module(kind='ecdf')\n"
        "try: m['prepare'](pd.DataFrame({'category':[1,float('inf')]}))\n"
        "except ValueError as problem: assert 'finite numeric' in str(problem)\n"
        "else: raise AssertionError('unplottable ECDF value accepted')\n"
        "m=module(kind='line')\n"
        "frame=m['prepare'](pd.DataFrame({'category':['1','2','10'],'value':['3','11','7']}))\n"
        "fig,ax=plt.subplots(); m['draw_panel'](ax,frame)\n"
        "assert list(ax.lines[0].get_xdata(orig=False))==[1,2,10] and list(ax.lines[0].get_ydata(orig=False))==[3,11,7]\n"
        "m=module(kind='bar',aggregation='sum')\n"
        "frame=m['prepare'](pd.DataFrame({'category':['01','01'],'value':['2','3']}))\n"
        "assert m['summarise'](frame)['value'].iloc[0]==5 and frame['category'].tolist()==['01','01']\n"
        "plt.close('all'); print('installed independent core quantities/domains/scales passed')\n",
        encoding="utf8",
    )
    run([str(python), str(driver)], cwd=where, env=env)
    run([*cli, "audit-init", str(demo)], cwd=where, env=env)
    audited = json.loads(
        run(
            [*cli, "audit", str(demo), "--out-dir", str(where / "audit")],
            cwd=where,
            env=env,
        )
    )
    assert audited["status"] == "passed"
    assert audited["figures"][0]["report"]["claims"][0]["verdict"] == "holds"
    generated_script = (
        where / "audit" / audited["figures"][0]["outputs"][0]["path"]
    ).parent / "figure.py"
    script_manifest = where / "script-manifest.json"
    script_manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "figures": [{"id": "script", "script": str(generated_script)}],
            }
        ),
        encoding="utf8",
    )
    script_audit = json.loads(
        run(
            [
                *cli,
                "audit",
                str(script_manifest),
                "--out-dir",
                str(where / "script audit"),
            ],
            cwd=where,
            env=env,
        )
    )
    assert script_audit["status"] == "passed"
    copied = json.loads(
        run(
            [*cli, "notebook", "--output", str(where / "quickstart.ipynb")],
            cwd=where,
            env=env,
        )
    )
    assert copied["ok"] and not copied["executed"]
    assert len(json.loads((where / "quickstart.ipynb").read_text())["cells"]) == 10
    config = json.loads(run([*cli, "mcp-config"], cwd=where, env=env))
    assert config["mcpServers"]["graphunslopify"]["command"] == str(python)
    if args.agent:
        agent_script = where / "agent-check.py"
        agent_script.write_text(
            "import asyncio, os, sys\nfrom mcp import Client, StdioServerParameters\n"
            "async def main():\n"
            "    params = StdioServerParameters(command=sys.executable, args=['-m','graphunslopify.cli','mcp'], env=dict(os.environ))\n"
            "    async with Client(params) as client:\n"
            "        tools = await client.list_tools()\n"
            "        assert len(tools.tools) == 7\n"
            "        schema = await client.call_tool('get_figure_schema', {})\n"
            "        assert len(schema.structured_content['oneOf']) == 21\n"
            "        bad = await client.call_tool('figure_to_matplotlib', {'spec':{'kind':'unknown'}})\n"
            "        assert bad.is_error and bad.structured_content['status'] == 'invalid_spec'\n"
            "asyncio.run(main())\n",
            encoding="utf8",
        )
        run([str(python), str(agent_script)], cwd=where, env=env)
    # Exercise the installed HTTP UI and static assets outside the checkout.
    editor_script = where / "editor-check.py"
    editor_script.write_text(
        "import json, threading, urllib.request\n"
        "from graphunslopify.preview import PreviewServer\n"
        "with PreviewServer(0) as server:\n"
        "    thread=threading.Thread(target=server.serve_forever, daemon=True);thread.start()\n"
        "    try:\n"
        "        url=f'http://127.0.0.1:{server.server_address[1]}'\n"
        "        with urllib.request.urlopen(url) as response: html=response.read()\n"
        "        assert b'Make the figure' in html and server.state.token.encode() in html\n"
        f"        assets={['/app.js', '/app.css', *(['/controls.js'] if args.require_editor_controls else [])]!r}\n"
        "        for asset in assets:\n"
        "            with urllib.request.urlopen(url+asset) as response: assert len(response.read())>1000\n"
        + (
            "        request=urllib.request.Request(url+'/api/info',headers={'X-Preview-Token':server.state.token})\n"
            "        with urllib.request.urlopen(request) as response: info=json.load(response)\n"
            "        assert len(info['schema']['oneOf'])==21 and b'Figure settings' in html\n"
            if args.require_editor_controls
            else ""
        )
        + "        request=urllib.request.Request(url+'/api/demo',data=b'{}',headers={'X-Preview-Token':server.state.token})\n"
        "        with urllib.request.urlopen(request) as response: demo=json.load(response)\n"
        "        assert demo['data']['rows']==24\n"
        "        payload={'spec':demo['spec'],'data_id':demo['data']['id'],'client':'wheel','generation':1}\n"
        "        request=urllib.request.Request(url+'/api/render',data=json.dumps(payload).encode(),headers={'X-Preview-Token':server.state.token})\n"
        "        with urllib.request.urlopen(request,timeout=120) as response: result=json.load(response)\n"
        "        assert result['report']['status']=='passed'\n"
        "        assert any(f['format']=='png' for f in result['files'])\n"
        "    finally:\n"
        "        server.shutdown();thread.join(5)\n",
        encoding="utf8",
    )
    run([str(python), str(editor_script)], cwd=where, env=env)
    # The SDK resolves nested relative input paths and separate output directories.
    sdk = where / "sdk.py"
    sdk.write_text(
        "import json\nfrom pathlib import Path\nimport graphunslopify\n"
        "from graphunslopify import Figure\n"
        "from graphunslopify.transport import local_request\n"
        "assert 'site-packages' in str(Path(graphunslopify.__file__))\n"
        "assert local_request('info')['version'] == graphunslopify.__version__\n"
        "f = Figure.line('paper with spaces/data/results.csv').x('epoch', 'Epoch').y('score', 'Score')\n"
        "f.by('model').average_over('seed').set(legend={'position':'outside_bottom'})\n"
        "before = f.to_dict()\nr = f.render(cwd='separate output', strict=True)\n"
        "assert r['report']['status'] == 'passed'\nassert f.to_dict() == before\n"
        "candidate = Figure.from_profile('paper with spaces/data/results.csv')\n"
        "assert candidate.spec['data']['path'] == 'paper with spaces/data/results.csv'\n"
        "assert candidate.translate()['status'] == 'translated'\n"
        "print(json.dumps({'package':graphunslopify.__file__, 'sdk':'passed'}))\n",
        encoding="utf8",
    )
    run([str(python), str(sdk)], cwd=where, env=env)
    # Ensure the network hooks themselves work, rather than merely claiming offline mode.
    blocked = subprocess.run(
        [
            str(python),
            "-c",
            "import socket; socket.create_connection(('example.com', 443))",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert blocked.returncode and "network disabled" in blocked.stderr
    blocked_node = subprocess.run(
        [
            str(python),
            "-m",
            "nodejs_wheel",
            "-e",
            "require('node:https').get('https://example.com')",
        ],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf8",
        check=False,
    )
    assert blocked_node.returncode and "network disabled" in blocked_node.stderr
    getting_started = None
    if tuple(map(int, doctor["python_package"].split(".")[:2])) >= (0, 8):
        getting_started = json.loads(
            run(
                [
                    str(python),
                    str(Path(__file__).resolve().with_name("check-getting-started.py")),
                    "--work-dir",
                    str(where / "guided tour"),
                ],
                cwd=where,
                env=env,
            )
        )
        assert getting_started["status"] == "passed"
    visual_comparison = None
    if args.require_comparison:
        visual_comparison = json.loads(
            run(
                [
                    str(python),
                    str(
                        Path(__file__).resolve().with_name("check-visual-comparison.py")
                    ),
                    "--work-dir",
                    str(where / "visual comparison"),
                ],
                cwd=where,
                env=env,
            )
        )
        assert visual_comparison["status"] == "passed"
    research_workflow = None
    if args.require_workflow:
        research_workflow = json.loads(
            run(
                [
                    str(python),
                    str(
                        Path(__file__).resolve().with_name("check-research-workflow.py")
                    ),
                    "--work-dir",
                    str(where / "research workflow"),
                ],
                cwd=where,
                env=env,
            )
        )
        assert research_workflow["status"] == "passed"
    experiment_tracking = None
    if args.tracking:
        experiment_tracking = json.loads(
            run(
                [
                    str(python),
                    str(
                        Path(__file__)
                        .resolve()
                        .with_name("check-experiment-tracking.py")
                    ),
                    "--work-dir",
                    str(where / "experiment tracking"),
                ],
                cwd=where,
                env=env,
            )
        )
        assert experiment_tracking["status"] == "passed"
    project_management = None
    if args.require_project:
        project_management = json.loads(
            run(
                [
                    str(python),
                    str(
                        Path(__file__)
                        .resolve()
                        .with_name("check-project-management.py")
                    ),
                    "--work-dir",
                    str(where / "project management"),
                ],
                cwd=where,
                env=env,
            )
        )
        assert project_management["status"] == "passed"
    print(
        json.dumps(
            {
                "status": "passed",
                "wheel": wheel.name,
                "python": sys.version.split()[0],
                "translator": doctor["translator"],
                "network": "external connections blocked after install",
                "agent": args.agent,
                "pdf": args.pdf,
                "registry_version": args.registry_version,
                "getting_started": getting_started,
                "visual_comparison": visual_comparison,
                "research_workflow": research_workflow,
                "experiment_tracking": experiment_tracking,
                "project_management": project_management,
                "work_dir": str(where),
            }
        )
    )


if __name__ == "__main__":
    main()
