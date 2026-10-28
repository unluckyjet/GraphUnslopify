"""Reject altered or misidentified release files before the upload job."""

from __future__ import annotations

import hashlib
import io
import runpy
import tarfile
from pathlib import Path
from zipfile import ZipFile

import pytest

VERIFY = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / "scripts/prepare-pypi-release.py")
)["verify_downloads"]


def release_files(folder, *, metadata_version="0.7.0", duplicate=False):
    metadata = f"Name: graphunslopify\nVersion: {metadata_version}\n".encode()
    wheel = folder / "graphunslopify-0.7.0-py3-none-any.whl"
    source = folder / "graphunslopify-0.7.0.tar.gz"
    with ZipFile(wheel, "w") as archive:
        archive.writestr("graphunslopify-0.7.0.dist-info/METADATA", metadata)
    with tarfile.open(source, "w:gz") as archive:
        member = tarfile.TarInfo("graphunslopify-0.7.0/PKG-INFO")
        member.size = len(metadata)
        archive.addfile(member, io.BytesIO(metadata))
    entries = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}" for p in (wheel, source)]
    if duplicate:
        entries.append(entries[0])
    (folder / "SHA256SUMS").write_text("\n".join(entries) + "\n")
    return {
        "assets": [
            {
                "name": p.name,
                "size": p.stat().st_size,
                "digest": "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest(),
            }
            for p in folder.iterdir()
        ]
    }


def test_release_rejects_one_byte_change_after_checksums(tmp_path):
    release = release_files(tmp_path)
    assert len(VERIFY(tmp_path, release, "0.7.0")) == 3
    wheel = tmp_path / "graphunslopify-0.7.0-py3-none-any.whl"
    wheel.write_bytes(wheel.read_bytes() + b"x")
    with pytest.raises(ValueError, match="digest/size mismatch"):
        VERIFY(tmp_path, release, "0.7.0")


def test_release_rejects_version_mismatch_even_when_all_hashes_match(tmp_path):
    release = release_files(tmp_path, metadata_version="0.8.0")
    with pytest.raises(ValueError, match="name/version"):
        VERIFY(tmp_path, release, "0.7.0")


def test_release_rejects_duplicate_manifest_entries_with_matching_asset_digest(tmp_path):
    release = release_files(tmp_path, duplicate=True)
    with pytest.raises(ValueError, match="duplicate"):
        VERIFY(tmp_path, release, "0.7.0")
