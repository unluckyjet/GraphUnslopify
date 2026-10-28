"""Verify an existing public GitHub release before an optional PyPI upload."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tarfile
from email.parser import BytesParser
from pathlib import Path
from zipfile import ZipFile

REPO = "unluckyjet/GraphUnslopify"


def gh(*args: str) -> dict:
    return json.loads(subprocess.check_output(["gh", *args], text=True))


def verify_downloads(folder: Path, release: dict, version: str) -> dict[str, str]:
    names = {
        f"graphunslopify-{version}-py3-none-any.whl",
        f"graphunslopify-{version}.tar.gz",
    }
    assets = {item["name"]: item for item in release["assets"]}
    if not (names | {"SHA256SUMS"}) <= assets.keys():
        raise ValueError("release must include the wheel, sdist and SHA256SUMS")
    hashes = {}
    for name in names | {"SHA256SUMS"}:
        content = (folder / name).read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if assets[name].get("digest") != "sha256:" + digest or assets[name][
            "size"
        ] != len(content):
            raise ValueError(f"GitHub asset digest/size mismatch: {name}")
        hashes[name] = digest
    checksums = {}
    for line in (folder / "SHA256SUMS").read_text().splitlines():
        match = re.fullmatch(r"([0-9a-f]{64}) [ *]([^\s/\\]+)", line)
        if not match or match[2] in checksums:
            raise ValueError("invalid or duplicate SHA256SUMS entry")
        checksums[match[2]] = match[1]
    if checksums.keys() != names or any(
        hashes[name] != checksums[name] for name in names
    ):
        raise ValueError("release distributions do not match SHA256SUMS")
    wheel = folder / f"graphunslopify-{version}-py3-none-any.whl"
    with ZipFile(wheel) as archive:
        metadata = archive.read(f"graphunslopify-{version}.dist-info/METADATA")
    with tarfile.open(folder / f"graphunslopify-{version}.tar.gz") as archive:
        member = archive.extractfile(f"graphunslopify-{version}/PKG-INFO")
        if member is None:
            raise ValueError("sdist package metadata missing")
        source_metadata = member.read()
    for payload in (metadata, source_metadata):
        headers = BytesParser().parsebytes(payload)
        if headers["Name"] != "graphunslopify" or headers["Version"] != version:
            raise ValueError(
                "distribution name/version differs from the selected release"
            )
    return hashes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", args.tag):
        parser.error("select an existing stable vMAJOR.MINOR.PATCH release")
    output = args.out_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        parser.error(
            "choose an empty output directory; previous artifacts are preserved"
        )
    release = gh("api", f"repos/{REPO}/releases/tags/{args.tag}")
    if release["draft"] or release["prerelease"] or release["tag_name"] != args.tag:
        raise ValueError("select a published, non-prerelease GitHub release")
    revision = gh("api", f"repos/{REPO}/commits/{args.tag}")["sha"]
    checks = []
    for workflow in ("checks.yml", "figure-ci-example.yml"):
        runs = gh(
            "api",
            "-X",
            "GET",
            f"repos/{REPO}/actions/workflows/{workflow}/runs",
            "-f",
            f"head_sha={revision}",
            "-f",
            "per_page=100",
        )["workflow_runs"]
        exact = sorted(
            (run for run in runs if run["head_sha"] == revision),
            key=lambda run: run["id"],
            reverse=True,
        )
        if (
            not exact
            or exact[0]["status"] != "completed"
            or exact[0]["conclusion"] != "success"
        ):
            raise ValueError(
                f"latest {workflow} run for exact release revision is not successful"
            )
        checks.append(
            {
                "workflow": workflow,
                "run_id": exact[0]["id"],
                "sha": revision,
                "conclusion": "success",
            }
        )
    version = args.tag[1:]
    assets = output / "release-assets"
    assets.mkdir()
    subprocess.run(
        [
            "gh",
            "release",
            "download",
            args.tag,
            "--repo",
            REPO,
            "--dir",
            str(assets),
            "--pattern",
            f"graphunslopify-{version}-py3-none-any.whl",
            "--pattern",
            f"graphunslopify-{version}.tar.gz",
            "--pattern",
            "SHA256SUMS",
        ],
        check=True,
    )
    hashes = verify_downloads(assets, release, version)
    destination = output / "dist"
    destination.mkdir()
    for name in hashes:
        if name != "SHA256SUMS":
            shutil.copyfile(assets / name, destination / name)
    result = {
        "schema_version": 1,
        "repository": REPO,
        "tag": args.tag,
        "revision": revision,
        "release_id": release["id"],
        "checks": checks,
        "sha256": hashes,
        "published_to_pypi": False,
        "scope": "existing release identity, exact-revision CI, distribution digests and metadata; install smoke and upload are separate steps",
    }
    (output / "readiness.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
