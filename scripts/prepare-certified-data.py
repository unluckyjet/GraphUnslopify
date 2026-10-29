"""Fetch explicitly requested NIST StRD inputs, verify pins and prepare offline CSV views."""

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        required=True,
        help="local publisher-file cache (not committed)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="empty directory for deterministic CSV views and metadata",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="explicitly fetch missing pinned files; default is offline",
    )
    args = parser.parse_args()
    prepare = runpy.run_path(str(ROOT / "benchmarks/certified/corpus.py"))["prepare"]
    try:
        result = prepare(
            manifest_path=ROOT / "benchmarks/certified/sources.json",
            source_dir=args.source_dir,
            output=args.out_dir,
            download=args.download,
        )
    except (OSError, ValueError, URLError) as problem:
        print(json.dumps({"status": "failed", "error": str(problem)}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
