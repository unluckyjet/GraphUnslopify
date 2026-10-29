"""Transport and scientific-header integrity, using explicitly synthetic parser fixtures."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CORPUS = runpy.run_path(str(ROOT / "benchmarks/certified/corpus.py"))


def fixture():
    lines = [""] * 60
    lines[0] = "File Name: Fixture.dat"
    lines[7] = "Dataset Name: Fixture"
    lines[40] = "Sample Mean ybar: 2 (exact)"
    lines[41] = "Sample Standard Deviation (denom. = n-1) s: 1 (exact)"
    lines[42] = "Sample Autocorrelation Coefficient (lag 1) r(1): -0.5 (exact)"
    lines[44] = "Number of Observations: 3"
    lines[58:60] = ["Data: Y", "----------"]
    data = ("\r\n".join([*lines, "1.0000", "3", "2.000"]) + "\r\n").encode("ascii")
    row = {
        "id": "Fixture",
        "file": "Fixture.dat",
        "url": "https://example.invalid/Fixture.dat",
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "observations": 3,
        "difficulty": "lower",
        "nist_source_class": "generated",
        "certified": {
            key: {"value": value, "exact": True}
            for key, value in [("mean", "2"), ("sample_sd", "1"), ("lag1_autocorrelation", "-0.5")]
        },
    }
    manifest = {
        "schema_version": 1,
        "collection": "Synthetic parser fixture, not external benchmark evidence",
        "dataset_order": ["Fixture"],
        "transport_user_agent": "Synthetic test",
        "sources": [row],
    }
    return data, row, manifest


def manifest_file(tmp_path):
    data, row, manifest = fixture()
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    source = tmp_path / "sources"
    source.mkdir()
    (source / row["file"]).write_bytes(data)
    return path, source, data


def test_real_manifest_freezes_all_nine_published_strata_without_product_results():
    d = CORPUS["read_manifest"](ROOT / "benchmarks/certified/sources.json")
    assert len(d["sources"]) == 9 and sum(r["observations"] for r in d["sources"]) == 8574
    assert {r["difficulty"] for r in d["sources"]} == {"lower", "average", "higher"}
    assert sum(r["nist_source_class"] == "observed" for r in d["sources"]) == 5
    assert d["data_redistributed"] is False


def test_offline_preparation_preserves_decimal_tokens_order_and_is_repeatable(
    tmp_path, monkeypatch
):
    path, source, data = manifest_file(tmp_path)
    monkeypatch.setattr(
        CORPUS["urllib"].request,
        "urlopen",
        lambda *a, **k: pytest.fail("offline preparation attempted network"),
    )
    first = CORPUS["prepare"](manifest_path=path, source_dir=source, output=tmp_path / "first")
    second = CORPUS["prepare"](manifest_path=path, source_dir=source, output=tmp_path / "second")
    assert first == second and first["status"] == "prepared"
    assert (
        tmp_path / "first/Fixture.csv"
    ).read_bytes() == b"observation,dataset,value\n1,Fixture,1.0000\n2,Fixture,3\n3,Fixture,2.000\n"
    assert (source / "Fixture.dat").read_bytes() == data
    assert "no GraphUnslopify/Matplotlib accuracy" in first["scope"]
    with pytest.raises(ValueError, match="empty output"):
        CORPUS["prepare"](manifest_path=path, source_dir=source, output=tmp_path / "first")


@pytest.mark.parametrize(
    ("before", "after", "reason"),
    [
        ("Dataset Name: Fixture", "Dataset Name: Other", "identity"),
        ("Number of Observations: 3", "Number of Observations: 4", "count"),
        ("s: 1 (exact)", "s: 2 (exact)", "certified"),
        ("denom. = n-1", "denom. = n", "sample_sd"),
        ("\r\n3\r\n", "\r\nNaN\r\n", "finite"),
        ("\r\n3\r\n", "\r\n", "actual observation"),
    ],
)
def test_semantic_corruption_rejects_even_when_transport_hash_is_rebound(before, after, reason):
    data, row, _ = fixture()
    changed = data.replace(before.encode(), after.encode())
    assert changed != data
    expected = {**row, "bytes": len(changed), "sha256": hashlib.sha256(changed).hexdigest()}
    with pytest.raises(ValueError, match=reason):
        CORPUS["parse_source"](changed, expected)


def test_changed_cached_source_is_never_overwritten_or_redownloaded(tmp_path, monkeypatch):
    path, source, data = manifest_file(tmp_path)
    changed = data + b"0\n"
    (source / "Fixture.dat").write_bytes(changed)
    monkeypatch.setattr(
        CORPUS["urllib"].request,
        "urlopen",
        lambda *a, **k: pytest.fail("must not redownload changed cache"),
    )
    with pytest.raises(ValueError, match="bytes/hash"):
        CORPUS["prepare"](
            manifest_path=path, source_dir=source, output=tmp_path / "absent", download=True
        )
    assert (source / "Fixture.dat").read_bytes() == changed and not (tmp_path / "absent").exists()


def test_download_requires_opt_in_and_validates_before_caching(tmp_path, monkeypatch):
    data, row, manifest = fixture()
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    source = tmp_path / "cache"
    calls = []

    def fetch(request, timeout):
        calls.append((request.get_header("User-agent"), timeout))
        return io.BytesIO(data)

    monkeypatch.setattr(CORPUS["urllib"].request, "urlopen", fetch)
    with pytest.raises(ValueError, match="--download"):
        CORPUS["prepare"](manifest_path=path, source_dir=source, output=tmp_path / "absent")
    assert not calls
    result = CORPUS["prepare"](
        manifest_path=path, source_dir=source, output=tmp_path / "prepared", download=True
    )
    assert calls == [("Synthetic test", 30)] and result["datasets"] == 1
    assert (source / row["file"]).read_bytes() == data


def test_corpus_membership_cannot_silently_drop_or_reorder_cases(tmp_path):
    _, _, manifest = fixture()
    changed = copy.deepcopy(manifest)
    changed["dataset_order"] = []
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="membership/order"):
        CORPUS["read_manifest"](path)
