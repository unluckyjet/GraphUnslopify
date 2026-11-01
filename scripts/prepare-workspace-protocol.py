"""Prepare the v1 workflow protocol once, before performance implementation/measurement."""

from __future__ import annotations

import copy
import json
import os
import runpy
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
C = runpy.run_path(str(ROOT / "benchmarks/workspace/corpus.py"))
HERE = C["HERE"]


def write(path, raw):
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError(f"Refusing to replace different prepared evidence: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def main():
    if (HERE / "protocol.json").exists():
        raise ValueError(
            "Protocol already exists. Validate it; do not regenerate a frozen protocol."
        )
    for name, raw in C["views"]().items():
        write(HERE / "inputs" / name, raw)
    specs = {}
    for name in C["FIGURES"]:
        source = ROOT / "examples/published-papers" / (name + ".json")
        spec = json.loads(source.read_text())
        data = source.parent / spec["data"]["path"]
        if name == "penguins-mass":
            data = HERE / "inputs/penguins-sex-complete.csv"
        spec["data"]["path"] = os.path.relpath(data.resolve(), HERE / "figures")
        spec["output"].update(
            dpi=600, stem="figure", formats=C["FORMATS"][:], size="double_column"
        )
        specs[name] = spec
        write(HERE / "figures" / (name + ".json"), C["encoded"](spec))
    target = copy.deepcopy(specs["iris-scatter"])
    target["data"]["path"] = "../inputs/iris-mm.csv"
    for axis in ("x", "y"):
        target[axis]["field"] += "_mm"
        target[axis]["unit"] = "mm"
    write(HERE / "figures/iris-scatter-mm.json", C["encoded"](target))
    science_faults = []
    for name, subject, reference in [
        ("penguins-mass", "female", "male"),
        ("iris-measurements", "Iris-virginica", "Iris-setosa"),
    ]:
        spec = copy.deepcopy(specs[name])
        spec["claims"] = [
            {"kind": "beats_everywhere", "subject": subject, "reference": reference}
        ]
        science_faults.append((name + "-false-claim", spec))
    absent = copy.deepcopy(specs["penguins-mass"])
    absent["claims"][0]["reference"] = "unobserved-reference"
    science_faults.append(("penguins-absent-reference", absent))
    singleton = copy.deepcopy(specs["penguins-mass"])
    singleton["data"]["path"] = "../inputs/penguins-singleton-sd.csv"
    singleton.pop("claims", None)
    science_faults.append(("penguins-singleton-sd", singleton))
    truth = {}
    reference = runpy.run_path(str(ROOT / "benchmarks/papers/reference.py"))
    for name, spec in specs.items():
        for step, candidate in C["requests"](spec, HERE / "figures"):
            expected = C["oracle"](candidate, HERE / "figures")
            C["independent_check"](candidate, HERE / "figures", expected, reference)
            assert expected["status"] == "passed"
            truth[name + "/" + step] = expected
    truth["iris-scatter-mm"] = C["oracle"](target, HERE / "figures")
    for name, spec in science_faults:
        write(HERE / "figures" / (name + ".json"), C["encoded"](spec))
        expected = C["oracle"](spec, HERE / "figures")
        C["independent_check"](spec, HERE / "figures", expected, reference)
        assert expected["status"] == (
            "failed" if "false-claim" in name else "incomplete"
        )
        truth[name] = expected
    write(HERE / "ground-truth.json", C["encoded"](truth))
    inputs = [
        "benchmarks/papers/sources.json",
        "benchmarks/papers/NOTICE.md",
        "benchmarks/papers/sources/penguins.csv",
        "benchmarks/papers/sources/bezdekIris.data",
        "benchmarks/papers/sources/iris.data",
        "examples/published-papers/data/iris.csv",
        "examples/published-papers/data/iris-long.csv",
        "benchmarks/papers/reference.py",
        "benchmarks/certified/protocol.json",
        "benchmarks/certified/protocol-v1.json",
        "benchmarks/certified/corpus.py",
        "benchmarks/certified/measurement.py",
        "benchmarks/authoring/protocol.json",
        "benchmarks/authoring/session.py",
        "benchmarks/certified/development-sessions.jsonl",
        "benchmarks/certified/results/report.json",
        "scripts/prepare-workspace-protocol.py",
        "scripts/check-workspace-protocol.py",
        "benchmarks/workspace/corpus.py",
        "benchmarks/workspace/README.md",
    ]
    inputs += [
        str(p.relative_to(ROOT)) for p in sorted((HERE / "inputs").glob("*.csv"))
    ]
    inputs += [
        str(p.relative_to(ROOT)) for p in sorted((HERE / "figures").glob("*.json"))
    ]
    inputs += ["benchmarks/workspace/ground-truth.json"]
    inputs += [
        str(p.relative_to(ROOT))
        for p in sorted((ROOT / "benchmarks/authoring/producers").glob("*.py"))
    ]
    protocol = {
        "schema_version": 1,
        "id": "public-workspace-comparison-v1",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "previous_accepted_source": "f15f1578ec5d330fdc611f19bb4050e8bbd8571b",
        "scope": "Prospective developer-controlled operational comparison and real scripted GUI conformance on two previously used public datasets. Not held-out, human authoring productivity, independent researcher judgment, blinded visual ratings, or a claim that either arm must win.",
        "prerequisite": "This protocol must be publicly committed/CI accepted. Both producers, controllers and the evaluator must then be implemented, untimed parity-checked and separately Git/CI sealed before formal timing. No formal timing is permitted by protocol preparation alone. Finish candidate UI fixes before the implementation seal. Record all exact code/resource/env hashes.",
        "datasets": [
            {
                "id": "penguins",
                "notice": "benchmarks/papers/NOTICE.md",
                "source_manifest": "benchmarks/papers/sources.json",
                "source_rows": 344,
                "descriptive_mass_rows": 333,
                "finite_scatter_pairs": 342,
            },
            {
                "id": "iris",
                "notice": "benchmarks/papers/NOTICE.md",
                "source_manifest": "benchmarks/papers/sources.json",
                "source_rows": 150,
                "long_rows": 600,
                "plants_per_species_measurement": 50,
            },
        ],
        "views": "Sex-complete penguins is an explicit333-row subset; singleton control takes one real row per species/sex. Iris mm explicitly multiplies each four cm measurements by10 with Decimal; no new observations. Original UCI files, including their documented differences, remain unchanged. SD describes observed spread, not population confidence or causal inference.",
        "arms": ["matplotlib-plus-validation", "graphunslopify"],
        "baseline_contract": {
            "numerics": "Separately authored csv/statistics or equivalent direct numerical calculations; no GraphUnslopify-generated drawing/statistics/claims code. Match frozen independent Decimal ground truth and actual artists, counts, group/order/units/SD ddof1. The earlier papers reference is a starting reference, not the complete benchmark baseline.",
            "strength": "Use normal Matplotlib artist/layout APIs, typed reusable functions, warmed processes, safe content-keyed calculation caches and safe incremental paper updates. Never handicap the baseline by requiring unnecessary rerender/recomputation. Shared inspect_figure is allowed as the same legibility gate, explicitly disclosed; scientific calculations/claims remain independently implemented.",
            "artifacts": "Match requested PNG/SVG/PDF or declared PNG-only outputs, physical width/DPI, required literal labels/units/legend, usable readable layout, numerical/claim report and data/program/environment manifests. Keep immutable source-bound history, failed evidence, current-output integrity and honest reuse ancestry in both arms.",
            "paper_reuse": "Both may reuse intact accepted unchanged figures with complete data/intent/policy/producer/environment keys. Never reuse acceptance after a failed latest whole-paper run or membership change. Inspect current evidence; retain original sources for reused reports. Recheck claims/geometry/exports for every executed figure; never cache acceptance as a calculation.",
        },
        "gates": {
            "strict": True,
            "fail_on_warning": False,
            "numeric_rel_tolerance": 1e-10,
            "numeric_abs_tolerance": 1e-10,
            "sd_ddof": 1,
            "width_in": {"single_column": 3.4, "double_column": 7.0},
            "width_tolerance_in": 0.02,
            "minimum_effective_font_pt": 6,
            "data_and_code_hashes": "Actual bytes, not normalized expected strings.",
            "quality": "Same scientific, physical/export, required-text and legibility checks. Warnings remain reported. Review PNG144 is not called a publication600 output. Do not infer task correctness from the product's status alone; independent task/artist/unit/label gates also apply.",
        },
        "actor_setup": "One familiarized scripted operational actor; same frozen requests/artifacts. All producer/operator code prepared before formal clocks; its authoring cost is unmeasured and excluded for both arms. No human productivity claim. Record dependency/install and fixture preparation separately; no hidden arm-specific setup. No model/provider is configured for quality evaluation; no mock output counts as a real model result.",
        "clocks": {
            "clock": "Same-host perf_counter_ns wall intervals plus UTC/source/env binding.",
            "startup": "Each fresh arm process from launch through imports/readiness; report separately and include in cold end-to-end. Include owned child startup, handshake and cleanup separately; do not pool with warm requests.",
            "first_image": "Only an actual owned current-request PNG availability event; mark unverified until all task/scientific/export gates finish. Never infer from a timer, earlier image or final report. Record unavailable with reason if genuinely unexposed.",
            "terminal": "Outer request dispatch through final outputs/report and independent task gates. Record first tool acceptance separately from first task-correct strict acceptance; failed/incomplete requests have terminal times and no verified time.",
            "warm": "Same live process/session; all seven ordinary changes retained. Do not exclude a slow first operation as a warmup.",
            "isolation": "No other benchmarks, test suites, artifact downloads, CI/vault work or producer edits during formal timing. Every interruption is retained and invalidates a clean timing interpretation rather than being silently replaced.",
        },
        "single_pipeline": {
            "figures": list(C["FIGURES"]),
            "sessions_per_arm_figure": 3,
            "steps": [
                name
                for name, _ in C["requests"](specs["penguins-mass"], HERE / "figures")
            ],
            "requests": 192,
            "order": "In each figure/session run the complete8-request sequence for one arm then the other. Arm order alternates by (figure_index+session_index) parity, fixed figure order as listed. No concurrent arms. Retain24 cold first requests and168 warm operations separately.",
        },
        "paper": {
            "figures": list(C["FIGURES"]),
            "binding_overrides": {
                "penguins-mass": {"data": "shared-inputs/penguins.csv"},
                "penguins-scatter": {"data": "shared-inputs/penguins.csv"},
            },
            "shared_data_scope": "Both Penguin figures bind the same owned clone of the original344-row CSV. Mass keeps its female/male filter, retaining333 observations. Do not bind its separate GUI sex-complete view for this paper track; CRLF reencoding must affect both Penguin figures.",
            "sessions_per_arm": 3,
            "requests": 54,
            "steps": [
                {
                    "id": "first",
                    "operation": "Full four-figure audit",
                    "expected_executed": 4,
                    "expected_reused": 0,
                    "exit_code": 0,
                },
                {
                    "id": "unchanged",
                    "operation": "Regenerate unchanged paper",
                    "expected_executed": 0,
                    "expected_reused": 4,
                    "exit_code": 0,
                },
                {
                    "id": "title",
                    "operation": "Change penguins-mass title only",
                    "expected_executed": 1,
                    "expected_reused": 3,
                    "exit_code": 0,
                },
                {
                    "id": "selected-output",
                    "operation": "Select first two figures; review/apply300 DPI, retaining formats and science",
                    "expected_executed": 2,
                    "expected_reused": 2,
                    "exit_code": 0,
                },
                {
                    "id": "reencoded-data",
                    "operation": "Rewrite owned penguin CSV with CRLF, same parsed observations; changed input bytes affect both penguin figures",
                    "expected_executed": 2,
                    "expected_reused": 2,
                    "exit_code": 0,
                },
                {
                    "id": "false-claim",
                    "operation": "Change penguin-mass comparison to female above male",
                    "expected_executed": 1,
                    "expected_reused": 3,
                    "exit_code": 2,
                },
                {
                    "id": "recover",
                    "operation": "Restore supported claim; latest failed run prevents old acceptance reuse",
                    "expected_executed": 4,
                    "expected_reused": 0,
                    "exit_code": 0,
                },
                {
                    "id": "add-alias",
                    "operation": "Add fifth figure alias of penguins-mass; membership requires full audit",
                    "expected_executed": 5,
                    "expected_reused": 0,
                    "exit_code": 0,
                },
                {
                    "id": "remove-alias",
                    "operation": "Remove alias; full four-figure membership audit",
                    "expected_executed": 4,
                    "expected_reused": 0,
                    "exit_code": 0,
                },
            ],
            "order": "Alternate arm order by session parity. Review/proposal/save/validation/history costs belong to each arm; do not compare a raw savefig call with a whole-paper audit.",
        },
        "reliability": {
            "repeats_per_arm_case": 2,
            "controls": 48,
            "clean": list(C["FIGURES"]),
            "science_faults": [
                {"id": name, "expected_status": truth[name]["status"], "exit_code": 2}
                for name, _ in science_faults
            ],
            "integrity_faults": [
                "change-saved-png-bytes",
                "change-saved-report-bytes",
                "reencode-data-after-acceptance",
                "append-comment-to-owned-recorded-producer-after-acceptance",
            ],
            "fault_scope": "Eight deliberate faults and four clean controls, all source-preserving clones. Not errors alleged in the papers. Integrity faults test borrowing old acceptance; distinguish unavailable/current-audit-needed from scientific failure. Match the relevant signal, not just any warning. Count all12 cases/two repeats in denominators; missed detections and false alarms remain results.",
        },
        "reproduction": {
            "figures": list(C["FIGURES"]),
            "arms": 2,
            "repeats": 2,
            "local_profiles": [
                "checkout-current3.12",
                "checkout-minimum3.10",
                "fresh-wheel3.12",
                "standalone-bundle-no-installed-graphunslopify3.12",
            ],
            "local_replays": 64,
            "native_ci_profiles": [
                "ubuntu3.10",
                "ubuntu3.12",
                "windows3.12",
                "macos3.12",
            ],
            "native_ci_replays": 64,
            "checks": "Actual scientific/artist/unit/physical/export/source binding in every relevant environment. Compare decoded PNGs only within the same arm/pinned environment; no cross-renderer or cross-version pixel equality claim. Cross-machine denominator is these four observed CI configurations, not general installations.",
        },
        "gui": {
            "tasks": [
                "penguins-mass-first",
                "iris-measurements-first",
                "penguins-scatter-first",
                "iris-scatter-first",
                "direct-owned-title-and-y-label",
                "review-three-export-presets",
                "save-template-retarget-iris-cm-to-mm-map-fields-review-and-correct-units",
            ],
            "profiles": ["source-current", "fresh-wheel"],
            "runs": 14,
            "actor": "Actual browser/manual controls and file drops only, no direct JSON/hidden state or success-response mocking. No first-time-human timing claim. Source/fresh desktop/mobile/keyboard, real strict failures and current exports must remain distinct. Prepared data/typed actions are disclosed. Preserve all failed attempts and report required JSON edits rather than hiding them.",
        },
        "analysis": "Retain every raw row. Report attempt/completion/accepted/failed counts, paired per-task medians and IQR, cold startup/first-image/final task-correct time, warm operation and whole-paper update time, actual executions/reuse, all reliability confusion-matrix cells and reproduction denominators. Show slower/failed/partial cases. Do not average incompatible phases or treat missing verified time as zero. No timing threshold, favorable-result stopping or post-outcome task/order/gate tuning.",
        "unavailable_judgments": [
            "independent researcher/first-use human authoring benefit",
            "blinded visual-quality/adoption scores",
            "general natural-language model quality/provider latency",
        ],
        "historical_evidence": "Original NIST e310 lineage/v1/v2 protocols, source data and four-episode familiarized-agent study are immutable. Their known earlier results informed this workload; do not replace them, relabel them independent, merge their clocks, or fabricate adoption.",
        "release": "No new release/tag authorized. Published0.8.0 remains distinct from the later tested source candidate.",
        "frozen_assets": {
            path: C["digest"]((ROOT / path).read_bytes()) for path in inputs
        },
    }
    raw = C["encoded"](protocol)
    write(HERE / "protocol.json", raw)
    write(HERE / "protocol.sha256", (C["digest"](raw) + "\n").encode())
    print(
        json.dumps(
            {
                "protocol_sha256": C["digest"](raw),
                "frozen_assets": len(inputs),
                "truth_cases": len(truth),
                "formal_timing_performed": False,
            }
        )
    )


if __name__ == "__main__":
    main()
