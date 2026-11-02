"""Observed interpreter/platform/CI identity, never a substitute for actual job artifacts."""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

NATIVE_PROFILES = {
    "ubuntu3.10": ("3.10.", "Linux", "Linux"),
    "ubuntu3.12": ("3.12.", "Linux", "Linux"),
    "windows3.12": ("3.12.", "Windows", "Windows"),
    "macos3.12": ("3.12.", "Darwin", "macOS"),
}


def observed():
    return {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "system": platform.system(),
        "machine": platform.machine(),
        "ci": {
            "github_actions": os.environ.get("GITHUB_ACTIONS") == "true",
            **{
                key: os.environ.get(variable)
                for key, variable in {
                    "commit": "GITHUB_SHA",
                    "repository": "GITHUB_REPOSITORY",
                    "run_id": "GITHUB_RUN_ID",
                    "run_attempt": "GITHUB_RUN_ATTEMPT",
                    "job": "GITHUB_JOB",
                    "runner_os": "RUNNER_OS",
                    "image_os": "ImageOS",
                    "image_version": "ImageVersion",
                }.items()
            },
        },
    }


def validate_worker(actual, profile, expected_ci):
    version, system, runner = NATIVE_PROFILES[profile]
    if not actual["python"].startswith(version) or actual["system"] != system:
        raise ValueError("Actual interpreter/platform differs from the native profile")
    ci = actual["ci"]
    if not ci["github_actions"]:
        raise ValueError("Native CI replay requires an actual GitHub Actions context")
    for key in ("commit", "repository", "run_id", "run_attempt", "job"):
        if not ci[key] or ci[key] != expected_ci.get(key):
            raise ValueError("Native worker CI identity differs: " + key)
    if ci["runner_os"] != runner or not re.fullmatch(r"[0-9a-f]{40}", ci["commit"]):
        raise ValueError("Actual runner or full source revision differs")
    if not str(ci["run_id"]).isdigit() or not str(ci["run_attempt"]).isdigit():
        raise ValueError("Actual CI run/attempt identifiers are unavailable")


def checkout_context(repo, profile, expected_revision):
    if not re.fullmatch(r"[0-9a-f]{40}", expected_revision):
        raise ValueError("Use a full expected Git revision")
    clt = Path("/Library/Developer/CommandLineTools/usr/bin/git")
    git = str(clt) if clt.is_file() else shutil.which("git")
    if not git:
        raise RuntimeError("Actual checkout binding requires Git")
    command = [git, "-c", "gc.auto=0", "-c", "maintenance.auto=false"]
    head = subprocess.check_output(
        [*command, "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    if head != expected_revision:
        raise ValueError("Actual checkout differs from requested native source")
    if subprocess.check_output(
        [*command, "status", "--porcelain", "--untracked-files=no"], cwd=repo, text=True
    ).strip():
        raise ValueError("Actual native checkout has tracked source changes")
    actual = observed()
    ci = actual["ci"]
    if ci["commit"] != head:
        raise ValueError("GitHub source context differs from actual checkout")
    validate_worker(actual, profile, ci)
    return {"checkout": head, "observed_parent": actual, "expected_worker_ci": ci}
