"""Actual source membership, dependency roles, stale owners and untrusted graphs."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import statistics

import pytest

from graphunslopify.observation_provenance import ObservationLedger

CONTEXT = {"run_id": "measured-run", "spec_sha256": "a" * 64, "program_sha256": "b" * 64}
CSV = b'x,series,value,note\n1,base,2,"two\nphysical lines"\n1,base,6,same\n1,alt,12,same\n1,alt,12,same\n'


def ledger(**kwargs):
    options = {"reader": {"format": "csv"}, "record_count": 4, "context": CONTEXT}
    return ObservationLedger.from_snapshot(CSV, **{**options, **kwargs})


def test_logical_records_and_identical_values_remain_distinct_without_copying_rows():
    records = list(csv.DictReader(io.StringIO(CSV.decode())))
    assert len(records) == 4 and len(CSV.splitlines()) == 6
    assert records[2] == records[3]
    trace = ledger()
    refs = [trace.observation(i) for i in range(len(records))]
    assert len(set(refs)) == 4 and trace.observation(2) == refs[2]
    packet = trace.as_dict()
    assert packet["source"]["snapshot_sha256"] == hashlib.sha256(CSV).hexdigest()
    assert [n["record_ordinal"] for n in packet["nodes"]] == [0, 1, 2, 3]
    assert all(set(n) == {"id", "kind", "record_ordinal"} for n in packet["nodes"])
    assert b"physical lines" not in trace.to_json()


def test_baseline_removed_from_display_still_contributes_to_calculation():
    rows = list(csv.DictReader(io.StringIO(CSV.decode())))
    trace = ledger()
    refs = [trace.observation(i) for i in range(4)]
    center = statistics.mean(float(rows[i]["value"]) for i in [0, 1])
    baseline = trace.calculate("mean", refs[:2], value=center, metadata={"field": "value"})
    hidden = trace.exclude("baseline_series_not_displayed", refs[:2], stage="display_selection")
    delta = trace.calculate(
        "subtract_baseline",
        [refs[2], baseline],
        value=float(rows[2]["value"]) - center,
        excluded=[hidden],
    )
    explanation = trace.explain(delta)
    assert explanation["complete"]
    assert explanation["contributing_records"] == [0, 1, 2]
    assert explanation["excluded_records"] == [0, 1]
    nodes = {n["id"]: n for n in explanation["nodes"]}
    assert nodes[delta]["value"] == 8
    assert nodes[hidden]["stage"] == "display_selection"
    assert refs[3] not in nodes


def test_technical_repeats_and_finite_exclusions_retain_the_actual_analysis_units():
    trace = ledger()
    refs = [trace.observation(i) for i in range(4)]
    a = trace.calculate("technical_repeat_mean", refs[:2], value=4, metadata={"unit": "A"})
    b = trace.calculate("technical_repeat_mean", [refs[2]], value=12, metadata={"unit": "B"})
    absent = trace.exclude("nonfinite_measurement", [refs[3]], stage="summary_input")
    mean = trace.calculate(
        "mean",
        [a, b],
        value=8,
        metadata={"declared_unit_count": 2, "independence": "not_established"},
        excluded=[absent],
    )
    spread = trace.calculate("sample_sd", [a, b], value=statistics.stdev([4, 12]))
    interval = trace.calculate(
        "descriptive_sd_bounds", [mean, spread], value=[8 - 32**0.5, 8 + 32**0.5]
    )
    answer = trace.explain(interval)
    assert answer["contributing_records"] == [0, 1, 2] and answer["excluded_records"] == [3]
    nodes = {n["id"]: n for n in answer["nodes"]}
    assert nodes[mean]["inputs"] == [a, b]
    assert nodes[mean]["metadata"]["declared_unit_count"] == 2
    assert nodes[spread]["value"] == pytest.approx(32**0.5)


def test_cumulative_dependency_order_and_multiplicity_are_preserved():
    trace = ledger()
    a, b, c = [trace.observation(i) for i in range(3)]
    prefix = trace.calculate("cumulative_sum", [b, a, c], value=20)
    repeated = trace.calculate("weighted_sum", [a, a, b], value=10)
    assert trace.explain(prefix)["nodes"][-1]["inputs"] == [b, a, c]
    assert trace.explain(repeated)["nodes"][-1]["inputs"] == [a, a, b]
    assert trace.explain(repeated)["contributing_records"] == [0, 1]
    assert prefix != trace.calculate("cumulative_sum", [a, b, c], value=20)


def test_same_snapshot_reader_and_ordinal_have_stable_identity_across_runs():
    left, right = ledger(), ledger(context={**CONTEXT, "run_id": "another-run"})
    a, b = left.observation(0), right.observation(0)
    assert a == b
    assert left.calculate("identity", [a], value=2) != right.calculate("identity", [b], value=2)
    excel_a = ledger(reader={"format": "excel", "sheet": "Results"})
    excel_b = ledger(reader={"format": "excel", "sheet": "Controls"})
    assert excel_a.observation(0) != excel_b.observation(0)
    changed = ObservationLedger.from_snapshot(
        CSV + b"\n", reader={"format": "csv"}, record_count=4, context=CONTEXT
    )
    assert changed.observation(0) != a


def test_metadata_snapshots_and_returned_values_do_not_mutate_stored_evidence():
    reader = {"format": "excel", "sheet": "Results", "options": {"header": 0}}
    trace = ledger(reader=reader)
    ref = trace.observation(0)
    options = {"unit": {"names": ["01", "1"]}}
    value = [1, 2]
    node = trace.calculate("interval", [ref], value=value, metadata=options)
    before = trace.to_json()
    reader["options"]["header"] = 2
    options["unit"]["names"].clear()
    value.append(3)
    trace.as_dict()["nodes"].clear()
    trace.explain(node)["nodes"].clear()
    assert trace.to_json() == before


def test_roundtrip_checks_actual_owner_and_reader_without_reexecuting_programs():
    trace = ledger()
    ref = trace.observation(1)
    trace.calculate("identity", [ref], value=6)
    packet = trace.as_dict()
    restored = ObservationLedger.from_json(
        trace.to_json(), expected_context=CONTEXT, expected_source=packet["source"]
    )
    assert restored.to_json() == trace.to_json()
    with pytest.raises(ValueError, match="different run"):
        ObservationLedger.from_json(trace.to_json(), expected_context={**CONTEXT, "run_id": "old"})
    with pytest.raises(ValueError, match="different reader"):
        ObservationLedger.from_json(
            trace.to_json(), expected_source={**packet["source"], "reader": {"format": "json"}}
        )


@pytest.mark.parametrize(
    "mutation", ["value", "id", "unknown", "cycle", "duplicate", "extra", "nan", "kind"]
)
def test_tampered_or_cyclic_local_evidence_is_rejected(mutation):
    trace = ledger()
    ref = trace.observation(0)
    node = trace.calculate("mean", [ref], value=2)
    packet = trace.as_dict()
    target = packet["nodes"][-1]
    if mutation == "value":
        target["value"] = 900
    elif mutation == "id":
        target["id"] = "calculation:" + "0" * 64
    elif mutation == "unknown":
        target["inputs"] = ["observation:" + "0" * 64]
    elif mutation == "cycle":
        target["inputs"] = [node]
    elif mutation == "duplicate":
        packet["nodes"].append(packet["nodes"][0])
    elif mutation == "extra":
        target["credential"] = "must-not-be-accepted"
    elif mutation == "nan":
        target["value"] = float("nan")
    elif mutation == "kind":
        target["kind"] = "execute_script"
    with pytest.raises(ValueError):
        ObservationLedger.from_json(json.dumps(packet).encode())


@pytest.mark.parametrize("budget", [{"max_nodes": 1}, {"max_edges": 1}, {"max_bytes": 700}])
def test_capacity_refusal_is_atomic_and_never_silently_truncates_ancestry(budget):
    trace = ledger(**budget)
    ref = trace.observation(0)
    before = trace.to_json()
    with pytest.raises(ValueError, match="budget"):
        trace.calculate("duplicate_weight", [ref, ref], value=4, metadata={"padding": "x" * 800})
    assert trace.to_json() == before
    assert trace.explain(ref)["complete"]


@pytest.mark.parametrize("ordinal", [-1, 4, True, 1.0, "1"])
def test_unparsed_ordinals_cannot_be_used_as_original_observations(ordinal):
    with pytest.raises(ValueError, match="ordinal"):
        ledger().observation(ordinal)


@pytest.mark.parametrize("value", [float("inf"), float("nan"), {1: "coerced-key"}, object()])
def test_values_cannot_hide_nonfinite_numbers_or_coerced_identity_keys(value):
    trace = ledger()
    ref = trace.observation(0)
    with pytest.raises(ValueError):
        trace.calculate("identity", [ref], value=value)


def test_exclusion_nodes_never_become_calculation_inputs_and_stay_locally_scoped():
    trace = ledger()
    ref = trace.observation(0)
    excluded = trace.exclude("filter", [ref], stage="prepare")
    with pytest.raises(ValueError, match="separate"):
        trace.calculate("mean", [excluded], value=2)
    with pytest.raises(ValueError, match="separate"):
        trace.calculate("mean", [ref], value=2, excluded=[ref])
    node = trace.calculate("mean", [ref], value=2)
    assert trace.explain(node)["excluded_records"] == []
    assert trace.explain(excluded)["contributing_records"] == []


def test_empty_source_and_constant_quantities_have_no_invented_observations():
    trace = ledger(record_count=0)
    node = trace.calculate("empty_category_count", [], value=0)
    assert trace.explain(node)["contributing_records"] == []
    assert ObservationLedger.from_json(trace.to_json()).to_json() == trace.to_json()
    with pytest.raises(ValueError):
        trace.observation(0)


def test_duplicate_json_keys_unknown_context_and_invalid_budgets_are_refused():
    with pytest.raises(ValueError, match="Duplicate"):
        ObservationLedger.from_json(b'{"schema_version":1,"schema_version":1}')
    with pytest.raises(ValueError, match="context"):
        ledger(context={**CONTEXT, "api_key": "not-an-allowed-context-field"})
    with pytest.raises(ValueError, match="positive"):
        ObservationLedger.from_json(b"{}", max_bytes=True)


def _nested_metadata(depth):
    value = "leaf"
    for _ in range(depth):
        value = {"nested": value}
    return value


@pytest.mark.parametrize("field", ["value", "metadata"])
@pytest.mark.parametrize("depth", [18, 20])
def test_accepted_nested_payloads_export_explain_and_roundtrip_without_aliases(field, depth):
    trace = ledger()
    ref = trace.observation(0)
    options = {"value": 1, "metadata": {}}
    tree = _nested_metadata(depth)
    options[field] = tree
    node = trace.calculate("nested_payload", [ref], **options)
    payload = trace.to_json()
    assert trace.explain(node)["nodes"][-1][field] == tree
    restored = ObservationLedger.from_json(payload, expected_context=CONTEXT)
    assert restored.to_json() == payload
    assert restored.explain(node) == trace.explain(node)
    copied = restored.as_dict()
    copied["nodes"][-1][field]["nested"].clear()
    assert restored.to_json() == payload


@pytest.mark.parametrize("field", ["value", "metadata"])
def test_overdeep_payload_refusal_leaves_ledger_exportable_and_unchanged(field):
    trace = ledger()
    ref = trace.observation(0)
    before = trace.to_json()
    options = {"value": 1, "metadata": {}}
    options[field] = _nested_metadata(21)
    with pytest.raises(ValueError, match="deeply nested"):
        trace.calculate("nested_payload", [ref], **options)
    assert trace.to_json() == before
    assert trace.explain(ref)["complete"]


@pytest.mark.parametrize("options_depth", [19, 20])
def test_reader_depth_limit_applies_to_configuration_before_envelope_wrapping(options_depth):
    reader = {"format": "csv", "options": _nested_metadata(options_depth)}
    if options_depth == 20:
        with pytest.raises(ValueError, match="deeply nested"):
            ledger(reader=reader)
    else:
        trace = ledger(reader=reader)
        payload = trace.to_json()
        restored = ObservationLedger.from_json(payload, expected_source=trace.as_dict()["source"])
        assert restored.to_json() == payload
