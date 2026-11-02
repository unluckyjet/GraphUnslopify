"""Explicit sealed study identity; this module never imports the plotting SDK.

Preparation is the default. A formal context is created prospectively from a
public exact-CI acceptance and an immutable implementation manifest, then passed
to the actual workers and observers. It cannot promote existing observations.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path, PurePosixPath

PROTOCOL_SHA256 = "32633e964a5274a848e2d207bc65c013e27586afde67bb5c09379d660ff6c636"
TRACKS = {"single", "paper", "reliability", "local", "native_ci", "gui"}
CHECKS = {
    "typescript",
    "python (3.10)",
    "python (3.12)",
    "render",
    "published-papers",
    "consumer",
    "distribution (ubuntu-latest, 3.10)",
    "distribution (ubuntu-latest, 3.12)",
    "distribution (windows-latest, 3.12)",
    "distribution (macos-latest, 3.12)",
    "native-reproduction (ubuntu3.10)",
    "native-reproduction (ubuntu3.12)",
    "native-reproduction (windows3.12)",
    "native-reproduction (macos3.12)",
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf8")


def relative(name):
    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in name
        or ":" in name
    ):
        raise ValueError("Execution manifest requires a safe repository-relative path")
    return path


def git(repo, *args):
    command = Path("/Library/Developer/CommandLineTools/usr/bin/git")
    executable = str(command) if command.is_file() else shutil.which("git")
    if not executable:
        raise RuntimeError("Sealed execution requires Git")
    return subprocess.check_output(
        [executable, "-c", "gc.auto=0", "-c", "maintenance.auto=false", *args],
        cwd=repo,
    )


def validate_acceptance(value, revision):
    if value.get("commit") != revision or not value.get(
        "all_nine_main_jobs_figure_and_four_native_passed"
    ):
        raise ValueError(
            "Formal execution requires exact14 CI acceptance for this source"
        )
    if not value.get("source_binding_matches") or not value.get(
        "expected_check_names_match"
    ):
        raise ValueError("CI acceptance has no exact source/check binding")
    checks = value.get("checks", [])
    if len(checks) != len(CHECKS) or {r.get("name") for r in checks} != CHECKS:
        raise ValueError("Formal seal must contain all14 distinct expected checks")
    if any(
        r.get("status") != "completed" or r.get("conclusion") != "success"
        for r in checks
    ):
        raise ValueError("Formal seal contains incomplete or failed checks")
    workflows = value.get("workflows", [])
    if len(workflows) != 3 or {r.get("name") for r in workflows} != {
        "checks",
        "Figure CI integration",
        "Workspace native reproduction",
    }:
        raise ValueError("Formal seal requires the three distinct original workflows")
    if any(
        r.get("head_sha") != revision
        or r.get("status") != "completed"
        or r.get("conclusion") != "success"
        for r in workflows
    ):
        raise ValueError("Formal seal workflow source/status differs")
    if any(value.get(key) for key in ("missing_checks", "unexpected_checks")):
        raise ValueError("Formal seal contains missing or unexpected checks")
    run_ids = {row.get("id") for row in workflows}
    if len(run_ids) != 3 or any(type(n) is not int or n <= 0 for n in run_ids):
        raise ValueError("Formal seal needs distinct actual workflow run identifiers")
    base = "https://github.com/unluckyjet/GraphUnslopify/actions/runs/"
    by_name = {row["name"]: row["id"] for row in workflows}
    for row in workflows:
        if row.get("html_url") != base + str(row["id"]):
            raise ValueError("Formal workflow identity is not the expected repository")
    jobs = set()
    for row in checks:
        workflow = (
            "Figure CI integration"
            if row["name"] == "consumer"
            else "Workspace native reproduction"
            if row["name"].startswith("native-reproduction (")
            else "checks"
        )
        prefix = base + str(by_name[workflow]) + "/job/"
        url = row.get("details_url", "")
        if (
            not url.startswith(prefix)
            or not url[len(prefix) :].isdigit()
            or int(url[len(prefix) :]) <= 0
            or url in jobs
        ):
            raise ValueError(
                "Formal check does not bind a distinct original job in its workflow"
            )
        jobs.add(url)


def validate_seal(seal, repo):
    """Verify public implementation bytes before any formal clock starts."""
    if not __debug__:
        raise RuntimeError("Do not optimize sealed execution guards")
    repo = Path(repo).resolve()
    revision = seal.get("revision", "")
    if seal.get("schema_version") != 1 or not re.fullmatch("[a-f0-9]{40}", revision):
        raise ValueError("Use a versioned seal with a full implementation revision")
    if seal.get("protocol_sha256") != PROTOCOL_SHA256:
        raise ValueError("Formal protocol identity changed")
    if (
        digest((repo / "benchmarks/workspace/protocol.json").read_bytes())
        != PROTOCOL_SHA256
    ):
        raise ValueError("Actual frozen protocol bytes changed")
    if git(repo, "rev-parse", "HEAD").decode().strip() != revision:
        raise ValueError("Formal implementation differs from the actual checkout")
    validate_acceptance(seal.get("exact_ci_acceptance", {}), revision)
    sources = seal.get("source_sha256", {})
    packages = seal.get("package_sha256", {})
    if not sources or not packages:
        raise ValueError("Formal seal must bind actual implementation and SDK files")
    import runpy

    runner = runpy.run_path(str(repo / "benchmarks/workspace/session_runner.py"))
    if (
        sources != runner["source_snapshot"]()
        or packages != runner["expected_package"]()
    ):
        raise ValueError(
            "Formal seal omits or changes the actual implementation closure"
        )
    combined = {
        **sources,
        **{"python/graphunslopify/" + n: h for n, h in packages.items()},
    }
    if len(combined) != len(sources) + len(packages):
        raise ValueError("Formal source and package scopes overlap")
    for name, expected in combined.items():
        relative(name)
        if not re.fullmatch("[a-f0-9]{64}", expected):
            raise ValueError("Invalid sealed file digest")
        if (
            digest((repo / name).read_bytes()) != expected
            or digest(git(repo, "show", revision + ":" + name)) != expected
        ):
            raise ValueError("Sealed implementation bytes differ: " + name)
    return digest(canonical(seal))


def validate_case(value, protocol):
    track, case, arm = value["track"], value["case"], value.get("arm")
    if arm not in {"matplotlib", "graphunslopify"}:
        raise ValueError("Unknown actual producer arm")
    if track == "single":
        valid = (
            set(case) == {"figure", "session"}
            and case["figure"] in protocol[track + "_pipeline"]["figures"]
            and type(case["session"]) is int
            and 0 <= case["session"] < 3
        )
    elif track == "paper":
        valid = (
            set(case) == {"session"}
            and type(case["session"]) is int
            and 0 <= case["session"] < 3
        )
    elif track in {"local", "native_ci"}:
        plan = protocol["reproduction"]
        valid = (
            set(case) == {"figure", "repeat", "profile"}
            and case["figure"] in plan["figures"]
            and type(case["repeat"]) is int
            and 0 <= case["repeat"] < plan["repeats"]
            and case["profile"]
            in plan["native_ci_profiles" if track == "native_ci" else "local_profiles"]
        )
    elif track == "gui":
        valid = (
            arm == "graphunslopify"
            and set(case) == {"profile"}
            and case["profile"] in protocol["gui"]["profiles"]
        )
    else:
        plan = protocol["reliability"]
        names = {
            "clean": plan["clean"],
            "science": [r["id"] for r in plan["science_faults"]],
            "integrity": plan["integrity_faults"],
        }
        valid = (
            set(case) == {"kind", "control", "repeat"}
            and case["kind"] in names
            and case["control"] in names[case["kind"]]
            and type(case["repeat"]) is int
            and 0 <= case["repeat"] < plan["repeats_per_arm_case"]
        )
    if not valid:
        raise ValueError("Execution context does not name a registered complete case")


def preparation():
    return {"mode": "preseal", "formal_comparison_performed": False}


def load(path, *, repo, track=None, arm=None):
    """Load only an explicitly supplied context; no ambient formal-mode switch."""
    if not __debug__:
        raise RuntimeError("Do not optimize execution context guards")
    if path is None:
        return preparation()
    path = Path(path).resolve()
    raw = path.read_bytes()
    value = json.loads(raw)
    if value.get("schema_version") != 1 or value.get("mode") not in {
        "formal",
        "preseal",
    }:
        raise ValueError("Explicit execution context must select a supported mode")
    tracks = {track} if isinstance(track, str) else set(track or TRACKS)
    if value.get("track") not in TRACKS or (
        track is not None and value["track"] not in tracks
    ):
        raise ValueError("Execution context track differs from the actual worker")
    if arm is not None and value.get("arm") != arm:
        raise ValueError("Execution context arm differs from the actual producer")
    if not value.get("case") or not isinstance(value["case"], dict):
        raise ValueError("Formal execution requires a registered case identity")
    validate_case(
        value,
        json.loads(
            (Path(repo) / "benchmarks/workspace/protocol.json").read_text(
                encoding="utf8"
            )
        ),
    )
    if value["mode"] == "formal":
        seal_digest = validate_seal(value.get("seal", {}), repo)
        if value.get("seal_sha256") != seal_digest:
            raise ValueError("Execution context seal digest differs")
    elif value.get("seal") is not None or value.get("seal_sha256") is not None:
        raise ValueError("Preparation cannot borrow a formal implementation seal")
    return {
        **value,
        "path": str(path),
        "context_sha256": digest(raw),
        "formal_comparison_performed": value["mode"] == "formal",
    }


def receipt(context):
    """Small actual-execution identity, retained alongside original observations."""
    if not context.get("context_sha256"):
        return preparation()
    return {
        key: context.get(key)
        for key in (
            "mode",
            "track",
            "arm",
            "case",
            "seal_sha256",
            "context_sha256",
            "formal_comparison_performed",
        )
    }


def arguments(context):
    if context.get("path"):
        return [
            "--execution-context",
            context["path"],
            "--execution-context-sha256",
            context["context_sha256"],
        ]
    return []


def observer(path, expected):
    """Bind copied observer to its validated parent's exact context document.

    The parent validates the full source/CI closure before dispatch. An observer
    verifies the document and its own original bytes without repeating hundreds
    of Git subprocesses inside a measured render. This is trusted local custody,
    not authentication against a malicious owner able to replace the harness.
    """
    if path is None:
        if expected is not None:
            raise ValueError("Observer context digest has no document")
        return preparation()
    if not __debug__:
        raise RuntimeError("Do not optimize observer execution guards")
    raw = Path(path).read_bytes()
    if not expected or digest(raw) != expected:
        raise ValueError("Observer execution document differs from its parent")
    value = json.loads(raw)
    if value.get("schema_version") != 1 or value.get("mode") not in {
        "preseal",
        "formal",
    }:
        raise ValueError("Observer execution mode is unavailable")
    if value["mode"] == "formal":
        seal = value["seal"]
        if digest(canonical(seal)) != value["seal_sha256"]:
            raise ValueError("Observer formal seal changed")
        own = seal["source_sha256"]["benchmarks/workspace/execution_context.py"]
        if digest(Path(__file__).read_bytes()) != own:
            raise ValueError("Copied execution guard differs from the sealed source")
    return {
        **value,
        "context_sha256": expected,
        "formal_comparison_performed": value["mode"] == "formal",
    }


def request(context, value, sequence, protocol):
    """Check actual worker RPC identity before the producer is invoked."""
    if not context.get("context_sha256"):
        return
    case, track = context["case"], context["track"]
    if track == "single":
        steps = protocol["single_pipeline"]["steps"]
        valid = (
            sequence < len(steps)
            and value.get("operation") == "render"
            and value.get("name") == steps[sequence]
            and value.get("case") == case["figure"] + "/" + steps[sequence]
        )
    elif track == "paper":
        steps = [r["id"] for r in protocol["paper"]["steps"]]
        valid = (
            sequence < len(steps)
            and value.get("operation") == "step"
            and value.get("step") == steps[sequence]
            and value.get("case") == "paper/" + steps[sequence]
        )
    elif track in {"local", "native_ci"}:
        valid = (
            sequence == 0
            and value.get("operation") == "render"
            and value.get("case") == case["figure"] + "/first"
        )
    elif track == "reliability":
        figure = "penguins-mass" if case["kind"] == "integrity" else case["control"]
        identity = figure if case["kind"] == "science" else figure + "/first"
        valid = value.get("case") == identity and (
            (sequence == 0 and value.get("operation") == "render")
            or (
                sequence == 1
                and case["kind"] == "integrity"
                and value.get("operation") == "validate"
            )
        )
    else:
        raise ValueError("GUI execution does not use the isolated RPC worker")
    if not valid:
        raise ValueError(
            "Actual worker request differs from its registered execution case"
        )
