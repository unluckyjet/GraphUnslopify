"""Check the frozen public-workspace protocol and independent numerical ground truth.

This is untimed conformance only. It does not implement or run the comparison.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
from pathlib import Path


def check(root):
    root = root.resolve()
    here = root / "benchmarks/workspace"
    raw = (here / "protocol.json").read_bytes()
    if (
        hashlib.sha256(raw).hexdigest()
        != (here / "protocol.sha256").read_text().strip()
    ):
        raise ValueError(
            "Frozen protocol bytes changed; preserve this version and preregister an amendment."
        )
    protocol = json.loads(raw)
    assert (
        protocol["id"] == "public-workspace-comparison-v1"
        and protocol["schema_version"] == 1
    )
    for name, expected in protocol["frozen_assets"].items():
        path = (root / name).resolve()
        if (
            not path.is_relative_to(root)
            or not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected
        ):
            raise ValueError("Frozen asset bytes changed: " + name)
    c = runpy.run_path(str(here / "corpus.py"))
    for name, expected in c["views"]().items():
        assert (here / "inputs" / name).read_bytes() == expected, (
            "Prepared view changed: " + name
        )
    truth = json.loads((here / "ground-truth.json").read_text())
    reference = runpy.run_path(str(root / "benchmarks/papers/reference.py"))
    checked = 0
    for name in c["FIGURES"]:
        spec = json.loads((here / "figures" / (name + ".json")).read_text())
        assert (here / "figures" / spec["data"]["path"]).resolve().is_relative_to(root)
        for step, candidate in c["requests"](spec, here / "figures"):
            actual = c["oracle"](candidate, here / "figures")
            assert actual == truth[name + "/" + step], (
                "Numerical ground truth changed: " + name + "/" + step
            )
            c["independent_check"](candidate, here / "figures", actual, reference)
            checked += 1
    for name in [
        "iris-scatter-mm",
        *(r["id"] for r in protocol["reliability"]["science_faults"]),
    ]:
        spec = json.loads((here / "figures" / (name + ".json")).read_text())
        actual = c["oracle"](spec, here / "figures")
        assert actual == truth[name], "Numerical ground truth changed: " + name
        c["independent_check"](spec, here / "figures", actual, reference)
        checked += 1
    assert set(truth) == {
        name + "/" + step
        for name in c["FIGURES"]
        for step in protocol["single_pipeline"]["steps"]
    } | {"iris-scatter-mm"} | {
        r["id"] for r in protocol["reliability"]["science_faults"]
    }
    assert checked == 37
    assert protocol["single_pipeline"]["requests"] == 4 * 2 * 3 * 8 == 192
    assert protocol["paper"]["requests"] == 2 * 3 * 9 == 54
    assert protocol["reliability"]["controls"] == (4 + 4 + 4) * 2 * 2 == 48
    assert (
        protocol["reproduction"]["local_replays"]
        == protocol["reproduction"]["native_ci_replays"]
        == 4 * 2 * 4 * 2
        == 64
    )
    assert protocol["gui"]["runs"] == 7 * 2 == 14
    assert (
        protocol["gates"]["strict"] is True
        and protocol["gates"]["fail_on_warning"] is False
    )
    return {
        "passed": True,
        "protocol_sha256": c["digest"](raw),
        "frozen_assets": len(protocol["frozen_assets"]),
        "independently_checked_numerical_cases": checked,
        "formal_timing_performed": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    a = p.parse_args()
    print(json.dumps(check(a.root)))


if __name__ == "__main__":
    main()
