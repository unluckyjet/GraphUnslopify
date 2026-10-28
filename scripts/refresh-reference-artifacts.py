"""Refresh owned reference PNG provenance from committed LF inputs and current emitter."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from graphunslopify.transport import local_request

ROOT = Path(__file__).resolve().parents[1]
IMAGES = {
    "density": "density-evidence.png",
    "table": "fifth-pass-table.png",
    "confusion": "seventh-pass-confusion.png",
    "heatmap": "third-pass-heatmap.png",
    "qq": "seventh-pass-qq.png",
    "scaling": "seventh-pass-scaling-fit.png",
    "sparklines": "sparkline-shared-scales.png",
}


def main() -> None:
    folder = ROOT / "examples/references"
    for name, destination in IMAGES.items():
        spec = json.loads((folder / f"{name}.figure.json").read_text())
        result = local_request("convert", spec)
        if not result.get("ok"):
            raise ValueError(f"reference translation failed: {name}")
        program = folder / f"{name}.py"
        program.write_text(result["code"], encoding="utf8", newline="\n")
        process = subprocess.run(
            [sys.executable, str(program), "--strict", "--json"],
            cwd=folder,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
        report = json.loads(process.stdout)
        expected = "incomplete" if name == "density" else "passed"
        if (
            process.returncode != (2 if name == "density" else 0)
            or report["status"] != expected
        ):
            raise ValueError(
                f"reference {name} unexpectedly returned {process.returncode}/{report['status']}"
            )
        shutil.copyfile(folder / f"{name}.png", ROOT / "docs" / destination)
        print(name, report["status"], destination)


if __name__ == "__main__":
    main()
