"""Compare fresh processes with both owned workers for every kind and mixed input."""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = [
    "schema_version",
    "spec_hash",
    "spec",
    "status",
    "ok",
    "data",
    "findings",
    "inspection",
    "panels",
    "claims",
    "significance",
    "annotations",
    "untested",
    "alt_text",
    "policy",
    "exit_code",
    "script",
]


def fingerprint(state, answer):
    from PIL import Image

    files = state.runs[answer["run_id"]]["files"]
    png = next(p for p in files.values() if p.suffix == ".png")
    with Image.open(png) as image:
        rgba = image.convert("RGBA")
        pixels = [list(rgba.size), hashlib.sha256(rgba.tobytes()).hexdigest()]
    folder = state.runs[answer["run_id"]]["folder"]
    stem = answer["spec"]["output"]["stem"]
    text = {
        suffix: hashlib.sha256((folder / f"{stem}.{suffix}").read_bytes()).hexdigest()
        for suffix in ["md", "tex"]
        if (folder / f"{stem}.{suffix}").exists()
    }
    animated = {}
    for path in files.values():
        if path.suffix == ".gif":
            from PIL import ImageSequence

            with Image.open(path) as image:
                animated[path.name] = {
                    "loop": image.info.get("loop"),
                    "frames": [
                        {
                            "size": list(frame.size),
                            "duration": frame.info.get("duration"),
                            "rgba_sha256": hashlib.sha256(
                                frame.convert("RGBA").tobytes()
                            ).hexdigest(),
                        }
                        for frame in ImageSequence.Iterator(image)
                    ],
                }
    return {
        "script_sha256": hashlib.sha256(
            (folder / f"{stem}.py").read_bytes()
        ).hexdigest(),
        "animated_exports": animated,
        "report": {key: answer["report"].get(key) for key in FIELDS},
        "pixels": pixels,
        "table_text": text,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    recipe_input = parser.add_mutually_exclusive_group(required=True)
    recipe_input.add_argument("--recipes-dir", type=Path)
    recipe_input.add_argument("--recipe-log", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--installed", action="store_true")
    args = parser.parse_args()
    out = args.out_dir.resolve()
    if args.recipe_log:
        match = re.search(r"^workdir: (.+)$", args.recipe_log.read_text(), re.MULTILINE)
        if match is None:
            parser.error("Recipe log has no actual generated fixture directory")
        args.recipes_dir = Path(match.group(1))
    recipes_dir = args.recipes_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    if not args.installed:
        sys.path.insert(0, str(ROOT / "python"))
    import graphunslopify
    import pandas as pd
    from graphunslopify.preview import PreviewState
    from graphunslopify.transport import local_request

    package = Path(graphunslopify.__file__).resolve().parent
    if args.installed and package == (ROOT / "python/graphunslopify").resolve():
        raise ValueError("Installed conformance resolved to the source checkout")
    assets = [
        "preview.py",
        "preview_worker.py",
        "translator_worker.py",
        "transport.py",
        "drafts.py",
        "preview_drafts.py",
        "worker_process.py",
        "preview_render.py",
        "preview_geometry.py",
        "preview_diagnostics.py",
        "_translator.mjs",
    ]
    hashes = {
        name: hashlib.sha256((package / name).read_bytes()).hexdigest()
        for name in assets
    }
    if any(
        value
        != hashlib.sha256(
            (ROOT / "python/graphunslopify" / name).read_bytes()
        ).hexdigest()
        for name, value in hashes.items()
    ):
        raise ValueError("Invoked package assets differ from source")
    recipes = local_request("recipes", {})
    assert len(recipes) == 25
    cases = []
    for recipe in recipes:
        spec = copy.deepcopy(recipe["spec"])
        data = recipes_dir / spec["data"]["path"]
        receipt = json.loads(
            (recipes_dir / f"{recipe['name']}.report.json").read_text()
        )
        assert receipt["status"] == "passed" and receipt["spec"]["kind"] == spec["kind"]
        cases.append(
            {
                "id": recipe["name"],
                "spec": spec,
                "name": data.name,
                "raw": data.read_bytes(),
                "exit": 0,
            }
        )
    box = next(case for case in cases if case["spec"]["kind"] == "box")
    violin = {key: copy.deepcopy(box["spec"][key]) for key in ["x", "y", "data"]}
    violin["kind"] = "violin"
    cases.append({**box, "id": "native-violin", "spec": violin})
    bar = next(case for case in cases if case["id"] == "ablation_bar")
    table = {
        key: copy.deepcopy(bar["spec"][key])
        for key in ["x", "y", "data", "aggregation", "uncertainty"]
    }
    table["kind"] = "table"
    cases.append({**bar, "id": "native-table", "spec": table})
    corpus = ROOT / "benchmarks/rendering"
    rules = json.loads((corpus / "protocol.json").read_text())
    negative = next(case for case in rules["cases"] if case["id"] == "false-comparison")
    negative_raw = (corpus / negative["data"]).read_bytes()
    cases.append(
        {
            "id": "original-false-comparison",
            "spec": json.loads((corpus / negative["spec"]).read_text()),
            "name": "data.csv",
            "raw": negative_raw,
            "exit": 2,
        }
    )
    positive = copy.deepcopy(cases[-1]["spec"])
    positive.pop("claims")
    frame = pd.read_csv(io.BytesIO(negative_raw))
    cases.append(
        {
            "id": "json-after-csv",
            "spec": positive,
            "name": "data.json",
            "raw": frame.to_json(orient="records").encode(),
            "exit": 0,
        }
    )
    parquet = io.BytesIO()
    frame.to_parquet(parquet, index=False)
    cases.append(
        {
            "id": "parquet-after-json",
            "spec": positive,
            "name": "data.parquet",
            "raw": parquet.getvalue(),
            "exit": 0,
        }
    )
    process = PreviewState(out / "process", 100 * 1024 * 1024)
    worker = PreviewState(
        out / "worker", 100 * 1024 * 1024, reuse_renderer=True, reuse_translator=True
    )
    result = {
        "scope": __doc__,
        "package_mode": "installed" if args.installed else "source",
        "package_root": str(package),
        "package_assets": hashes,
        "complete": False,
        "passed": False,
        "records": [],
    }
    try:
        for number, case in enumerate(cases):
            record = {
                "id": case["id"],
                "kind": case["spec"]["kind"],
                "format": case["name"].split(".")[-1],
                "passed": False,
            }
            result["records"].append(record)
            try:
                spec = {
                    **case["spec"],
                    "output": {
                        **case["spec"].get("output", {}),
                        "stem": "figure",
                        "formats": ["png", "svg", "pdf"],
                        "size": "double_column",
                        "dpi": 150,
                    },
                }
                pair = []
                for state in [process, worker]:
                    upload = state.upload(case["name"], case["raw"])
                    answer = state.render(
                        {
                            "client": "all-kinds",
                            "generation": number,
                            "data_id": upload["id"],
                            "spec": spec,
                        }
                    )
                    if answer["report"] is None:
                        raise ValueError(json.dumps(answer["translation"]))
                    assert answer["exit_code"] == case["exit"], answer["report"]
                    assert (
                        not answer["export_errors"]
                        and not answer["stale"]
                        and answer["report"]["policy"]["strict"]
                    )
                    for key in ["edit_map", "diagnostic_map"]:
                        location = answer[key]
                        if location["available"]:
                            assert (
                                location["run_id"] == answer["run_id"]
                                and location["spec_hash"]
                                == answer["report"]["spec_hash"]
                            )
                    pair.append((fingerprint(state, answer), answer))
                assert pair[0][0] == pair[1][0], (
                    "Actual scientific report, PNG or table text differs"
                )
                assert (
                    pair[0][1]["execution"]["mode"] == "process"
                    and pair[1][1]["execution"]["mode"] == "worker"
                )
                compiler = pair[1][1]["translation_execution"]
                assert compiler["mode"] == "worker" and compiler["kind"] == "translator"
                assert compiler["request_number"] == number + 1
                assert (
                    compiler["pid"] == worker.translator.process.connection.process.pid
                )
                assert compiler["runtime_source_sha256"] == hashes["_translator.mjs"]
                assert pair[0][1]["translation_execution"]["mode"] == "process"
                record.update(
                    passed=True,
                    exit_code=case["exit"],
                    worker=pair[1][1]["execution"],
                    translator=compiler,
                    matching_original_semantic_report_png_and_table_text=True,
                )
            except Exception as problem:  # noqa: BLE001 -- preserve every failed native case
                record["error"] = f"{type(problem).__name__}: {problem}"
            (out / "checks.json").write_text(json.dumps(result, indent=2) + "\n")
            print(case["id"], record["passed"], record.get("error", ""), flush=True)
    finally:
        worker.close()
        process.close()
    result.update(
        complete=True,
        passed=all(r["passed"] for r in result["records"]),
        kinds=sorted({r["kind"] for r in result["records"]}),
    )
    assert len(result["kinds"]) == 21
    (out / "checks.json").write_text(json.dumps(result, indent=2) + "\n")
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
