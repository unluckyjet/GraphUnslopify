"""A frozen performance plan must not pass on hashes alone or changed source rows."""

from __future__ import annotations

import hashlib
import json
import runpy
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECK = runpy.run_path(str(ROOT / "scripts/check-workspace-protocol.py"))["check"]


@pytest.fixture
def frozen(tmp_path):
    plan = json.loads((ROOT / "benchmarks/workspace/protocol.json").read_text())
    names = [
        *plan["frozen_assets"],
        "benchmarks/workspace/protocol.json",
        "benchmarks/workspace/protocol.sha256",
    ]
    for name in names:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return tmp_path


def reseal_changed_asset(root, name):
    """Even a self-consistent replacement hash must face independent numerical checks."""
    path = root / "benchmarks/workspace/protocol.json"
    plan = json.loads(path.read_text())
    plan["frozen_assets"][name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    raw = (json.dumps(plan, ensure_ascii=False, indent=2) + "\n").encode()
    path.write_bytes(raw)
    path.with_suffix(".sha256").write_text(hashlib.sha256(raw).hexdigest() + "\n")


def test_original_protocol_checks_real_data_and_independent_numerical_truth():
    proof = CHECK(ROOT)
    assert proof["passed"] and proof["independently_checked_numerical_cases"] == 37
    assert not proof["formal_timing_performed"]


def test_same_observations_with_changed_source_bytes_are_not_silently_reaccepted(frozen):
    source = frozen / "benchmarks/papers/sources/penguins.csv"
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="Frozen asset bytes changed"):
        CHECK(frozen)


def test_hash_consistent_but_wrong_numeric_oracle_is_rejected(frozen):
    name = "benchmarks/workspace/ground-truth.json"
    path = frozen / name
    truth = json.loads(path.read_text())
    truth["penguins-mass/first"]["artists"][0]["mean"] += 1
    path.write_text(json.dumps(truth) + "\n")
    reseal_changed_asset(frozen, name)
    with pytest.raises(AssertionError, match="Numerical ground truth changed"):
        CHECK(frozen)


def test_prepared_views_cannot_invent_values_even_with_replaced_hashes(frozen):
    name = "benchmarks/workspace/inputs/penguins-sex-complete.csv"
    path = frozen / name
    raw = path.read_bytes()
    assert b",3750," in raw
    path.write_bytes(raw.replace(b",3750,", b",9999,", 1))
    reseal_changed_asset(frozen, name)
    with pytest.raises(AssertionError, match="Prepared view changed"):
        CHECK(frozen)


def test_modified_fixture_code_is_rejected_before_it_can_execute(frozen):
    source = frozen / "benchmarks/workspace/corpus.py"
    marker = frozen / "unexpected-code-execution"
    source.write_text(
        source.read_text()
        + "\nPath(__file__).resolve().parents[2].joinpath('unexpected-code-execution').write_text('bad')\n"
    )
    with pytest.raises(ValueError, match="Frozen asset bytes changed"):
        CHECK(frozen)
    assert not marker.exists()
