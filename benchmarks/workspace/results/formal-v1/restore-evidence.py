"""Restore the published original study bytes without executing archived code."""

import argparse
import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath


def relative(value):
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value:
        raise ValueError("Archive members must be safe relative file paths")
    return path


def main():
    if not __debug__:
        raise RuntimeError("Do not optimize evidence guards")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parts", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    parts = json.loads(args.parts.read_text())
    assert parts["schema_version"] == 1
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    archive = output / "_originals.cas.zip"
    combined = hashlib.sha256()
    total = 0
    with archive.open("xb") as dest:
        for item in parts["parts"]:
            name = relative(item["name"])
            assert len(name.parts) == 1
            raw = (args.parts.parent / str(name)).read_bytes()
            assert len(raw) == item["bytes"]
            assert hashlib.sha256(raw).hexdigest() == item["sha256"]
            dest.write(raw)
            combined.update(raw)
            total += len(raw)
    assert total == parts["archive_bytes"]
    assert combined.hexdigest() == parts["archive_sha256"]
    with zipfile.ZipFile(archive) as z:
        manifest_raw = z.read("original-members.json")
        assert (
            hashlib.sha256(manifest_raw).hexdigest()
            == parts["original_manifest_sha256"]
        )
        manifest = json.loads(manifest_raw)
        assert manifest["schema_version"] == 1
        assert manifest["revision"] == parts["revision"]
        members = manifest["members"]
        assert len(members) == parts["original_members"]
        objects = {"objects/" + item["sha256"] for item in members.values()}
        assert len(z.namelist()) == len(set(z.namelist()))
        assert set(z.namelist()) == objects | {"original-members.json"}
        for name, item in members.items():
            target = output.joinpath(*relative(name).parts)
            raw = z.read("objects/" + item["sha256"])
            assert len(raw) == item["bytes"]
            assert hashlib.sha256(raw).hexdigest() == item["sha256"]
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as f:
                f.write(raw)
            assert hashlib.sha256(target.read_bytes()).hexdigest() == item["sha256"]
    (output / "portable-inputs.json").write_text(
        json.dumps(manifest["portable_analysis_inputs"], indent=2) + "\n"
    )
    proof = {
        "archive_sha256": combined.hexdigest(),
        "restored_original_members": len(members),
        "all_original_bytes_verified": True,
        "archived_code_executed": False,
    }
    (output / "restore-verification.json").write_text(
        json.dumps(proof, indent=2) + "\n"
    )
    archive.unlink()
    print(json.dumps(proof))


if __name__ == "__main__":
    main()
