"""Create a prospective seal only from exact CI and all actual preparation plans."""

from __future__ import annotations

import argparse
import json
import runpy
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "benchmarks/workspace"


def create(output, acceptance, parity):
    if not __debug__:
        raise RuntimeError("Do not optimize implementation seal guards")
    output = Path(output)
    if output.exists():
        raise ValueError("Refuse to replace an existing implementation seal")
    execution = runpy.run_path(str(HERE / "execution_context.py"))
    runner = runpy.run_path(str(HERE / "session_runner.py"))
    qualifier = runpy.run_path(str(HERE / "qualification.py"))
    revision = execution["git"](ROOT, "rev-parse", "HEAD").decode().strip()
    execution["validate_acceptance"](acceptance, revision)
    source, package = runner["source_snapshot"](), runner["expected_package"]()
    native = next(
        r["id"]
        for r in acceptance["workflows"]
        if r["name"] == "Workspace native reproduction"
    )
    qualification = qualifier["qualify"](
        parity,
        source_sha256=source,
        package_sha256=package,
        revision=revision,
        native_run=native,
    )
    seal = {
        "schema_version": 1,
        "revision": revision,
        "protocol_sha256": execution["PROTOCOL_SHA256"],
        "source_sha256": source,
        "package_sha256": package,
        "exact_ci_acceptance": acceptance,
        "qualification": qualification,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Prospective project-run operational comparison; preparation does not become formal data. No human productivity,blind ratings,adoption or model-quality claim.",
    }
    execution["validate_seal"](seal, ROOT)
    if len(execution["canonical"](seal)) > 60000:
        raise ValueError("Compact seal exceeds native workflow dispatch capacity")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf8") as stream:
        json.dump(seal, stream, indent=2)
        stream.write("\n")
    return seal


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ci-acceptance", type=Path, required=True)
    parser.add_argument("--parity-manifest", type=Path, required=True)
    args = parser.parse_args()
    seal = create(
        args.out,
        json.loads(args.ci_acceptance.read_text(encoding="utf8")),
        json.loads(args.parity_manifest.read_text(encoding="utf8")),
    )
    print(
        json.dumps(
            {
                "revision": seal["revision"],
                "qualified_tracks": list(seal["qualification"]["tracks"]),
                "formal_measurements_performed": False,
            }
        )
    )
