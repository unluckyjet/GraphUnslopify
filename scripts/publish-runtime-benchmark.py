"""Publish exact runtime-v1 measurements, including slower cases and raw evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import statistics
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def check(run, rules, mode):
    result = json.loads((run / "results.json").read_text())
    assert result["passed"] and result["complete"] and result["mode"] == mode
    assert result["protocol_sha256"] == sha(
        (ROOT / "benchmarks/runtime/protocol.json").read_bytes()
    )
    cases = {c["id"]: c for c in rules["cases"]}
    counts = {
        "attempted": 0,
        "strict0": 0,
        "original_strict2": 0,
        "instrumented_untimed": 0,
    }
    for section, arms in (
        ("native", rules["native"]["arms"]),
        ("direct", rules["direct"]["arms"]),
    ):
        assert len(result[section]) == len(cases) * len(arms)
        assert {(c, a) for c in cases for a in arms} == {
            (r["case"], r["arm"]) for r in result[section]
        }
        warm = (
            (
                rules["smoke"]["warm_native_repetitions"]
                if section == "native"
                else rules["smoke"]["direct_repetitions"]
            )
            if mode == "smoke"
            else rules[section]["warm_repetitions"]
        )
        for group in result[section]:
            assert group["passed"] and group.get("matches_other_native_arm", True)
            assert len(group["records"]) == warm + (2 if section == "native" else 1)
            assert (
                group["summary"]["accepted_warm"]
                == group["summary"]["scheduled_warm"]
                == warm
            )
            if section == "native":
                assert group["workers_closed"]
                assert group["node_sha256"] == result["node"]["sha256"]
            for r in group["records"]:
                assert (
                    r["passed"]
                    and r["exit_code"] == cases[group["case"]]["expected_exit_code"]
                )
                assert r["status"] == cases[group["case"]]["expected_status"]
                assert "error" not in r
                counts["attempted"] += 1
                counts["strict0" if r["exit_code"] == 0 else "original_strict2"] += 1
                counts["instrumented_untimed"] += r["phase"] == "instrumented-warm-font"
    counts.update(
        unexpected_failures=0,
        unrun=0,
        ordinary_and_cold_timed=counts["attempted"] - counts["instrumented_untimed"],
    )
    assert counts["attempted"] == (360 if mode == "smoke" else 900)
    assert counts["original_strict2"] == (12 if mode == "smoke" else 30)
    return result, counts


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--formal", type=Path, required=True)
    p.add_argument("--smoke", type=Path, required=True)
    p.add_argument("--native-science", type=Path, required=True)
    p.add_argument("--direct-science", type=Path, required=True)
    p.add_argument("--diagnostic", type=Path, action="append", default=[])
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    rules = json.loads((ROOT / "benchmarks/runtime/protocol.json").read_text())
    formal, formal_counts = check(a.formal, rules, "formal")
    smoke, smoke_counts = check(a.smoke, rules, "smoke")
    native_science, direct_science = (
        json.loads(x.read_text()) for x in (a.native_science, a.direct_science)
    )
    assert (
        native_science["interpreter_binary_sha256"]
        == direct_science["interpreter_binary_sha256"]
    )
    assert native_science["distributions"] == direct_science["distributions"]
    assert formal["native_probe"]["science"] == formal["direct_probe"]["science"]
    assert (
        formal["direct_probe"]["graphunslopify_version"] is None
        and not formal["direct_probe"]["graphunslopify_importable"]
    )
    for name, key in (
        ("runtime-benchmark.py", "driver_sha256"),
        ("profile-runtime-phases.py", "profile_sha256"),
    ):
        assert sha((ROOT / "scripts" / name).read_bytes()) == formal[key]
    a.out.mkdir(parents=True, exist_ok=False)
    write(a.out / "formal-results.json", formal)
    write(a.out / "smoke-results.json", smoke)
    rows = []
    for section in ("native", "direct"):
        for group in formal[section]:
            summary = group["summary"]
            first = group["records"][0]
            rows.append(
                {
                    "case": group["case"],
                    "executor": section,
                    "arm": group["arm"],
                    "strict_exit": first["exit_code"],
                    "warm_repetitions": summary["scheduled_warm"],
                    "median_seconds": summary["median_all_recorded_seconds"],
                    "p90_seconds_linear": summary["p90_all_recorded_seconds_linear"],
                    "cold_seconds": first[
                        "engine_seconds" if section == "native" else "wall_seconds"
                    ],
                }
            )
    with (a.out / "case-summary.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lookup = {(r["case"], r["executor"], r["arm"]): r for r in rows}
    ratios = []
    for case in rules["cases"]:
        identity = case["id"]
        native_base = lookup[identity, "native", "accepted-inline"]["median_seconds"]
        direct_base = lookup[identity, "direct", "accepted-inline"]["median_seconds"]
        ratios.append(
            {
                "case": identity,
                "kind": case["kind"],
                "expected_exit_code": case["expected_exit_code"],
                "native_shared_over_inline": lookup[
                    identity, "native", "default-shared"
                ]["median_seconds"]
                / native_base,
                "direct_shared_over_inline": lookup[
                    identity, "direct", "default-shared"
                ]["median_seconds"]
                / direct_base,
                "direct_bundle_over_inline": lookup[
                    identity, "direct", "standalone-bundle"
                ]["median_seconds"]
                / direct_base,
            }
        )
    write(a.out / "case-ratios.json", ratios)
    with tempfile.TemporaryDirectory(prefix="gu-runtime-publication-fonts-") as cache:
        os.environ["MPLCONFIGDIR"] = cache
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(12, 12), sharey=True)
        y = list(range(len(ratios)))
        axes[0].scatter(
            [r["native_shared_over_inline"] for r in ratios],
            y,
            color="#32609b",
            label="Shared / inline",
        )
        axes[1].scatter(
            [r["direct_shared_over_inline"] for r in ratios],
            [v - 0.13 for v in y],
            color="#32609b",
            label="Shared / inline",
        )
        axes[1].scatter(
            [r["direct_bundle_over_inline"] for r in ratios],
            [v + 0.13 for v in y],
            color="#a25427",
            marker="s",
            label="Bundle / inline",
        )
        labels = [
            r["case"][: r["case"].rfind("-") + 7]
            + (" [strict2]" if r["expected_exit_code"] == 2 else "")
            for r in ratios
        ]
        axes[0].set_yticks(y, labels, fontsize=9)
        axes[0].invert_yaxis()
        for axis, title in zip(
            axes,
            (
                "Owned native workers · 7 warm repetitions",
                "Fresh direct processes · 3 warm repetitions",
            ),
        ):
            axis.axvline(1, color="#777777", linestyle="--", linewidth=1)
            axis.set_title(title, fontsize=11)
            axis.set_xlabel(
                "Per-case median latency / accepted inline median\nBelow 1: faster in this run; above 1: slower"
            )
            axis.grid(axis="x", alpha=0.2)
            axis.legend(loc="lower right", fontsize=9)
        fig.suptitle("Compact runtime: mixed measured latency outcomes", fontsize=14)
        fig.tight_layout(rect=(0, 0, 1, 0.97))
        fig.savefig(a.out / "warm-latency-ratios.png", dpi=160)
        fig.savefig(a.out / "warm-latency-ratios.svg")
        plt.close(fig)
    raw = []
    for label, root in (("formal", a.formal), ("smoke", a.smoke)):
        for section in ("native", "direct"):
            for arm in rules[section]["arms"]:
                target = a.out / f"{label}-{section}-{arm}-raw.zip"
                with zipfile.ZipFile(
                    target, "w", zipfile.ZIP_DEFLATED, compresslevel=6
                ) as z:
                    for path in sorted(root.rglob("*")):
                        if (
                            not path.is_file()
                            or "__pycache__" in path.parts
                            or path.suffix == ".pyc"
                        ):
                            continue
                        relative = path.relative_to(root)
                        parts = relative.parts
                        include = len(parts) == 1 or parts[0] in {
                            "accepted-source",
                            "current-source",
                        }
                        include |= (
                            len(parts) >= 3 and parts[1] == section and parts[2] == arm
                        )
                        include |= (
                            section == "direct"
                            and arm == "standalone-bundle"
                            and parts[-1] == "complete-source.zip"
                        )
                        if include:
                            z.write(path, str(relative))
                    if label == "formal":
                        for name in (
                            "runtime-benchmark.py",
                            "profile-runtime-phases.py",
                        ):
                            if name not in z.namelist():
                                z.write(ROOT / "scripts" / name, name)
                    z.write(
                        ROOT / "benchmarks/runtime/protocol.json",
                        "frozen-protocol.json",
                    )
                assert target.stat().st_size < 99 * 1024 * 1024, (
                    "Split a raw archive before publishing; never discard evidence."
                )
                raw.append(
                    {
                        "path": target.name,
                        "bytes": target.stat().st_size,
                        "sha256": sha(target.read_bytes()),
                    }
                )
    diagnostic = a.out / "diagnostic-and-environment-raw.zip"
    with zipfile.ZipFile(diagnostic, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for folder in a.diagnostic:
            for file in folder.rglob("*"):
                if (
                    file.is_file()
                    and "__pycache__" not in file.parts
                    and file.suffix != ".pyc"
                ):
                    z.write(file, str(Path(folder.name) / file.relative_to(folder)))
        for file in (a.native_science, a.direct_science):
            z.write(file, file.name)
        z.write(__file__, "publish-runtime-benchmark.py")
        for label, folder in (("formal", a.formal), ("smoke", a.smoke)):
            log = folder.with_suffix(".log")
            if log.exists():
                z.write(log, label + ".log")
    raw.append(
        {
            "path": diagnostic.name,
            "bytes": diagnostic.stat().st_size,
            "sha256": sha(diagnostic.read_bytes()),
        }
    )
    source = formal["footprint"]
    entry_before = statistics.median(r["entry_inline"]["bytes"] for r in source)
    entry_after = statistics.median(r["entry_shared"]["bytes"] for r in source)
    lines_before = statistics.median(r["entry_inline"]["utf8_lines"] for r in source)
    lines_after = statistics.median(r["entry_shared"]["utf8_lines"] for r in source)
    wins = {
        k: {
            "faster": sum(r[k] < 1 for r in ratios),
            "slower_or_equal": sum(r[k] >= 1 for r in ratios),
        }
        for k in (
            "native_shared_over_inline",
            "direct_shared_over_inline",
            "direct_bundle_over_inline",
        )
    }
    verification = {
        "scope": "Developer-controlled source379 runtime-v1 measurement on one Mac; no human, independent-executor or universal speed claim.",
        "source_revision": formal["source_revision"],
        "protocol_sha256": formal["protocol_sha256"],
        "formal_counts": formal_counts,
        "smoke_counts": smoke_counts,
        "actual_scientific_distributions_matched": len(native_science["distributions"]),
        "actual_scientific_files_matched": sum(
            len(d["files"]) for d in native_science["distributions"].values()
        ),
        "actual_interpreter_binary_matched": True,
        "entry_median_bytes": {"inline": entry_before, "shared": entry_after},
        "entry_median_utf8_lines": {"inline": lines_before, "shared": lines_after},
        "case_median_directions": wins,
        "archives": raw,
        "local_seven_checks": "Separate gate receipts; benchmark success alone does not complete release/CI acceptance.",
    }
    write(a.out / "verification.json", verification)
    text = f"""# Compact runtime measurement v1

Smaller entries preserve the original results; measured latency is mixed.
The same30 frozen variants span all21 kinds and retain their original strict failures.
This is a developer-controlled comparison on one Mac, not human authoring time or independent execution.

| Actual measure | Accepted inline | Default shared |
| --- | ---: | ---: |
| Median entry bytes | {entry_before:,.1f} | {entry_after:,.1f} |
| Median entry UTF-8 lines | {lines_before:,.1f} | {lines_after:,.1f} |
| Complete package-source/resource bytes | {formal["accepted_package"]["bytes"]:,} | {formal["current_package"]["bytes"]:,} |
| Complete package-source/resource files | {formal["accepted_package"]["files"]} | {formal["current_package"]["files"]} |

Native shared case medians are faster in {wins["native_shared_over_inline"]["faster"]}/30 cases and slower in {wins["native_shared_over_inline"]["slower_or_equal"]}/30.
Direct shared case medians are faster in {wins["direct_shared_over_inline"]["faster"]}/30 and slower in {wins["direct_shared_over_inline"]["slower_or_equal"]}/30;
standalone bundles are faster in {wins["direct_bundle_over_inline"]["faster"]}/30 and slower in {wins["direct_bundle_over_inline"]["slower_or_equal"]}/30.
These counts do not establish a general speed advantage. All slower cases are retained.

![Each exact case's warm median latency ratio; original strict failure labelled](warm-latency-ratios.png)

The [150-row per-case CSV](case-summary.csv) gives every native/direct arm's warm median, linear-interpolated P90, repetition count and first-start time.
[Ratios](case-ratios.json) retain all30 exact comparisons. Never pool these as human time to a verified figure.

## Conditions and complete evidence

- Frozen [protocol](../../protocol.json): `{formal["protocol_sha256"]}`; accepted baseline1b.
- Formal900 actual executions:870 strict0 and30 original strict2, zero unexpected failures/unrun;840 ordinary/cold timed and60 separate instrumented samples.
- Smoke360:348 strict0/12 original strict2, zero unexpected failures/unrun;300 ordinary/cold timed and60 instrumented samples.
- Per case/native arm: fresh owned context/font directory,16 renderer/64 compiler budgets,64-entry/32MiB numerical cache, one cold-font/seven warm/one extra instrumented original; alternate arm order per case.
- Direct arms: fresh process for each run, one cold-font/three warm; rotate arm order. Original source/true main guards execute through the same disclosed bootstrap. Launch-to-child-entry, bootstrap setup, original execution and completion/teardown remain separate raw fields. Wall time includes this harness.
- Exact actual Node binary matches native arms. Python interpreter binary and6,980 installed library/resource files across11 declared scientific distributions match between native/direct environments; only installed GraphUnslopify metadata deliberately differs. Bundled runs have no installed/importable package before launch and an invalid Node override.
- Actual report mathematics, identifiers/units/seeded uncertainty, strict policy, PNG pixels, SVG/PDF drawing content and native maps match accepted originals. Log contents match; actual script/component/provenance hashes are checked before normalizing source identity.
- Complete runtime/package/bundle bytes, UTF-8 lines and per-file hashes are in [formal raw measurements](formal-results.json). Eleven pinned scientific components are distinct from the full64-file shipped runtime; they are not a minimal dependency closure. Bundles contain source/input/spec/runtime; third-party scientific packages and optional external tools remain external.
- Read/compile/real C-exec hooks run only in the extra untimed native sample, against original program bytes, and restore before rendering. Ordinary samples have no hooks. Source-read/compile/exec diagnostic timings include observer overhead.

Small samples, one host and non-randomized alternating/rotating order limit performance inference; OS background activity and CPU frequency are not controlled. Repeated identical figures exercise the already-enabled numerical cache. No blind layout scores, outside researchers, new release or general Matplotlib advantage is measured here. Original reference/NIST protocols remain unchanged.

## Reproduce the measurement

Use the actual matching scientific versions in formal-results.json and a second Python environment without GraphUnslopify. The executable must retain its venv path. From the source checkout:

```sh
python scripts/runtime-benchmark.py --smoke --python /path/to/no-package/bin/python --out-dir /outside/checkout/smoke
python scripts/runtime-benchmark.py --python /path/to/no-package/bin/python --out-dir /outside/checkout/formal
```

Run serially without other project checks. The native geometry guard retains the frozen baseline's actual drawing conditions; different platforms/library/font versions may correctly refuse comparison. Setup/probes/translation/archive creation/extraction are recorded separately. All raw outputs, original programs, inputs, reports/maps, archives, complete source and actual harness versions are retained in the ZIPs listed in [verification](verification.json). Initial six one-case diagnostic probes predate full harness snapshots and are excluded from formal/smoke denominators. The intentional wrong-reference diagnostic fails as expected while retaining its real successful process duration. Required local gates and exact-commit CI are separate delivery checks.
"""
    (a.out / "README.md").write_text(text)
    print(json.dumps(verification, indent=2))


if __name__ == "__main__":
    main()
