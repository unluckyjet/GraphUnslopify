"""Actual question/data API/CLI,public-value artist references and strict-failure evidence."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from graphunslopify.autopilot import generate_drafts, propose_figures

ROOT = Path(__file__).resolve().parents[1]


def cli(*arguments):
    run = subprocess.run(
        [sys.executable, "-m", "graphunslopify.cli", *map(str, arguments)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert run.stdout, run.stderr[-2000:]
    return run.returncode, json.loads(run.stdout)


def check(out, expected_sha=None):
    out.mkdir(parents=True, exist_ok=False)
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    dirty = bool(
        subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        ).strip()
    )
    if expected_sha is not None:
        assert revision == expected_sha
        assert not dirty
    source = ROOT / "benchmarks/papers/sources/penguins.csv"
    original = source.read_bytes()
    source_sha = hashlib.sha256(original).hexdigest()
    (out / "public-source.csv").write_bytes(original)
    frame = pd.read_csv(source)
    valid = np.isfinite(frame["body_mass_g"]) & frame["species"].notna()
    plan = propose_figures(source, "Compare body mass between species")
    assert plan.report["choices"]["target"] == "body_mass_g"
    assert (
        plan.report["choices"]["group"] == "species"
        and not plan.report["choices"]["units"]
    )
    normalized = json.loads(plan.data_bytes)
    assert [r["source_record"] for r in normalized] == list(frame.index[valid])
    assert [r["measure"] for r in normalized] == frame.loc[
        valid, "body_mass_g"
    ].tolist()
    assert [r["group"] for r in normalized] == frame.loc[valid, "species"].tolist()
    assert plan.report["excluded_count"] == int((~valid).sum())
    with contextlib.redirect_stdout(io.StringIO()):
        result = generate_drafts(
            plan, out / "public", reviewed=True, accept_exclusions=True
        )
    assert result["status"] == "passed" and len(result["drafts"]) == 3
    artists = {}
    quantities = []
    for draft in result["drafts"]:
        native = draft["native_report"]
        assert native["status"] == "passed" and native["policy"]["strict"]
        assert native["data"]["counts"]["prepared"] == int(valid.sum())
        folder = out / "public" / draft["id"]
        script = folder / (native["spec"]["output"]["stem"] + ".py")
        assert (
            hashlib.sha256(script.read_bytes()).hexdigest()
            == native["script"]["sha256"]
        )
        for exported in native["outputs"]:
            raw = (folder / exported["path"]).read_bytes()
            assert (
                len(raw) == exported["bytes"]
                and hashlib.sha256(raw).hexdigest() == exported["sha256"]
            )
        loader = importlib.util.spec_from_file_location(
            "autopilot_reference_" + draft["id"], script
        )
        module = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(module)
        figure, axes = plt.subplots()
        try:
            table = pd.read_json(out / "public/autopilot-data.json")
            module.draw_panel(axes, module.prepare(table))
            if native["spec"]["kind"] == "bar":
                expected = (
                    frame.loc[valid]
                    .groupby("species", sort=False)["body_mass_g"]
                    .mean()
                    .tolist()
                )
                actual = [patch.get_height() for patch in axes.patches]
                np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=0)
                artists["descriptive_means"] = list(map(float, actual))
            elif native["spec"]["kind"] == "ecdf":
                for name, line in zip(plan.report["groups"], axes.lines, strict=True):
                    assert line.get_label() == name
                    values = np.sort(
                        frame.loc[
                            valid & frame["species"].eq(name), "body_mass_g"
                        ].to_numpy()
                    )
                    np.testing.assert_array_equal(
                        line.get_xdata(), np.r_[values[:1], values]
                    )
                    np.testing.assert_allclose(
                        line.get_ydata(),
                        np.r_[0, np.arange(1, len(values) + 1) / len(values)],
                        rtol=1e-14,
                        atol=0,
                    )
                artists["empirical_groups"] = len(axes.lines)
            else:
                for name, cloud in zip(
                    plan.report["groups"], axes.collections, strict=True
                ):
                    actual = np.sort(np.asarray(cloud.get_offsets())[:, 1])
                    expected = np.sort(
                        frame.loc[
                            valid & frame["species"].eq(name), "body_mass_g"
                        ].to_numpy()
                    )
                    np.testing.assert_array_equal(actual, expected)
                artists["raw_group_clouds"] = len(axes.collections)
            figure.savefig(out / (draft["id"] + "-reference.png"))
        finally:
            plt.close(figure)
        quantities.append(
            {
                "id": draft["id"],
                "kind": native["spec"]["kind"],
                "status": native["status"],
                "prepared_rows": int(valid.sum()),
            }
        )
    failed_source = out / "long-groups.csv"
    failed_source.write_text(
        "model,loss\n"
        + "\n".join(
            f"{label},{value}"
            for label, value in [
                ("A" * 250, 1),
                ("A" * 250, 2),
                ("B" * 250, 3),
                ("B" * 250, 4),
            ]
        )
        + "\n"
    )
    bad = propose_figures(failed_source, "Compare loss between models")
    with contextlib.redirect_stdout(io.StringIO()):
        failed = generate_drafts(bad, out / "strict-failure", reviewed=True)
    assert failed["exit_code"] == 2 and failed["status"] == "incomplete"
    assert len(failed["drafts"]) == 3 and any(
        d["status"] != "passed" for d in failed["drafts"]
    )
    review_path = out / "cli-review.json"
    code, document = cli(
        "autopilot-propose",
        source,
        "--question",
        plan.report["question"],
        "--out",
        review_path,
    )
    assert code == 0 and document["report"]["snapshot"] == plan.report["snapshot"]
    assert json.loads(review_path.read_text()) == document
    code, unreviewed = cli(
        "autopilot-generate", review_path, "--out-dir", out / "cli-unreviewed"
    )
    assert (
        code == unreviewed["exit_code"] == 2 and not (out / "cli-unreviewed").exists()
    )
    (out / "cli-unreviewed.json").write_text(json.dumps(unreviewed, indent=2) + "\n")
    code, cli_result = cli(
        "autopilot-generate",
        review_path,
        "--out-dir",
        out / "cli-drafts",
        "--reviewed",
        "--accept-exclusions",
    )
    assert code == cli_result["exit_code"] == 0 and cli_result["status"] == "passed"
    assert len(cli_result["drafts"]) == 3 and all(
        d["status"] == "passed" for d in cli_result["drafts"]
    )
    assert (out / "cli-drafts/autopilot-data.json").read_bytes() == plan.data_bytes
    assert cli_result["review"]["fingerprint"] == document["fingerprint"]
    assert json.loads((out / "cli-drafts/autopilot.json").read_text()) == cli_result
    assert (
        out / "cli-drafts/reviewed-proposal.json"
    ).read_bytes() == review_path.read_bytes()
    assert all(
        d["native_report"]["data"]["counts"]["prepared"] == int(valid.sum())
        for d in cli_result["drafts"]
    )
    assert source.read_bytes() == original
    proof = {
        "schema_version": 1,
        "revision": revision,
        "worktree_dirty": dirty,
        "expected_ci_sha": expected_sha,
        "python": sys.version.split()[0],
        "public_source_sha256": source_sha,
        "question": plan.report["question"],
        "snapshot": plan.report["snapshot"],
        "input_rows": len(frame),
        "selected_rows": int(valid.sum()),
        "excluded_rows": int((~valid).sum()),
        "drafts": quantities,
        "independent_artist_references": artists,
        "strict_failure_verdicts": [
            {"id": d["id"], "status": d["status"]} for d in failed["drafts"]
        ],
        "source_unchanged": True,
        "cli": {
            "review_fingerprint": document["fingerprint"],
            "snapshot": document["report"]["snapshot"],
            "unreviewed_exit_code": unreviewed["exit_code"],
            "status": cli_result["status"],
            "drafts": [
                {"id": d["id"], "status": d["status"]} for d in cli_result["drafts"]
            ],
        },
        "model_service_used": False,
        "scientific_appropriateness_certified": False,
        "scope": "Core Python API and saved-review CLI;editor workflow remains unfinished",
        "passed": True,
    }
    (out / "verification.json").write_text(json.dumps(proof, indent=2) + "\n")
    return proof


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--expected-sha")
    args = parser.parse_args()
    result = check(args.out_dir, args.expected_sha)
    print(
        json.dumps(
            {
                "out": str(args.out_dir),
                "passed": result["passed"],
                "drafts": len(result["drafts"]),
                "core_only": True,
            }
        )
    )
