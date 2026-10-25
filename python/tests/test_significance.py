"""Known-answer checks against the actual emitted adjustment functions."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def emitted(tmp_path_factory):
    root = Path(__file__).resolve().parents[2]
    script = """
import { translate } from './src/translate.ts';
const result = translate({
  kind: 'bar', x: {field: 'method', label: 'Method'},
  y: {field: 'score', label: 'Score'}, aggregation: 'mean',
  significance: {method: 'bootstrap', pairs: [['base', 'ours']]}
});
if (result.status !== 'translated') throw Error('invalid fixture');
process.stdout.write(result.code);
"""
    completed = subprocess.run(
        ["node", "--experimental-strip-types", "--input-type=module", "-e", script],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    path = tmp_path_factory.mktemp("significance") / "figure.py"
    path.write_text(completed.stdout, encoding="utf8")
    spec = importlib.util.spec_from_file_location("significance_reference", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("values", "holm", "bh"),
    [
        ([0.01, 0.04, 0.03, 0.002], [0.03, 0.06, 0.06, 0.008], [0.02, 0.04, 0.04, 0.008]),
        ([0.01, 0.01, 0.04, 0.2], [0.04, 0.04, 0.08, 0.2], [0.02, 0.02, 0.16 / 3, 0.2]),
        ([0.8, 0.9], [1.0, 1.0], [0.9, 0.9]),
        ([0.02], [0.02], [0.02]),
        ([], [], []),
    ],
)
def test_hand_calculated_adjustments_preserve_input_order(emitted, values, holm, bh):
    assert emitted.adjust_pvalues(values, "holm").tolist() == pytest.approx(holm)
    assert emitted.adjust_pvalues(values, "benjamini_hochberg").tolist() == pytest.approx(bh)
    assert emitted.adjust_pvalues(values, "none").tolist() == values


def test_holm_and_bh_make_different_decisions_on_reference_family(emitted):
    values = [0.01, 0.04, 0.03, 0.002]
    assert emitted.adjust_pvalues(values, "holm")[1] > 0.05
    assert emitted.adjust_pvalues(values, "benjamini_hochberg")[1] <= 0.05


@pytest.mark.parametrize("values", [[float("nan")], [float("inf")], [-0.1], [1.1]])
def test_invalid_probabilities_are_never_presented_as_corrected_results(emitted, values):
    with pytest.raises(ValueError, match="p-values"):
        emitted.adjust_pvalues(values, "holm")
