"""Exercise a packaged paper workspace over its real loopback HTTP API."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlencode


def check_pdf_review(where, env, cli, pdf):
    paper = where / "PDF-only paper ü"
    paper.mkdir()
    cli("project-init", paper, "--review-only")
    log = (where / "pdf-server.stderr.log").open("w", encoding="utf8")
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "graphunslopify.cli",
            "project-preview",
            str(paper),
            "--port",
            "0",
        ],
        env=env,
        cwd=where,
        stdout=subprocess.PIPE,
        stderr=log,
        text=True,
        encoding="utf8",
    )
    try:
        root = json.loads(server.stdout.readline())["url"]

        def request(path, body=None, *, headers=None, expected=200):
            call = urllib.request.Request(root + path, data=body, headers=headers or {})
            try:
                response = urllib.request.urlopen(call, timeout=90)
            except urllib.error.HTTPError as problem:
                response = problem
            with response:
                data = response.read()
                assert response.code == expected, data
                return data, dict(response.headers)

        token = re.search(
            r'name="preview-token" content="([^"]+)"', request("/")[0].decode()
        )[1]
        headers = {"X-Preview-Token": token}

        def api(path, payload=None, expected=200):
            return json.loads(
                request(
                    path,
                    None if payload is None else json.dumps(payload).encode(),
                    headers=headers,
                    expected=expected,
                )[0]
            )

        state = api("/api/state")
        assert state["status"] == "review_only" and not state["figures"]
        api("/api/run", {"expected_revision": state["revision"]}, expected=400)
        query = urlencode(
            {
                "id": "external",
                "expected_revision": state["inspection_revision"],
                "pages": "1",
                "dpi": 72,
            }
        )
        request(
            "/api/pdf-upload?" + query,
            pdf,
            headers={
                **headers,
                "Content-Type": "application/pdf",
                "X-File-Name": "Synthetic-native-export.pdf",
            },
            expected=202,
        )
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            job = api("/api/job")
            if job["phase"] != "running":
                break
            time.sleep(0.05)
        assert (
            job["phase"] == "complete"
            and job["result"]["status"] == "incomplete"
            and job["result"]["exit_code"] == 2
        ), job
        review = api("/api/review")
        assert review["schema_version"] == 2 and len(review["figures"]) == 1
        row = review["figures"][0]
        assert row["source_type"] == "pdf" and not row["matches_latest_accepted_inputs"]
        assert row["groups"]["claims"]["state"] == "untested"
        assert row["groups"]["uncertainty"]["state"] == "untested"
        assert (paper / row["inspection"]["path"]).read_bytes() == pdf
        event = job["result"]["id"]
        assert not list(
            (paper / "graphunslopify-project/history" / event).rglob("*.pdf")
        )
        index, asset = next(
            (i, item)
            for i, item in enumerate(row["inspection"]["assets"])
            if item["path"].endswith(".png")
        )
        path = "/api/pdf-asset?" + urlencode(
            {"event": event, "index": index, "view": 1}
        )
        data, response = request(path, headers=headers)
        assert (
            response["Content-Type"] == "image/png"
            and hashlib.sha256(data).hexdigest() == asset["sha256"]
        )
        request(path, expected=403)
        request("/sources/source.pdf", headers=headers, expected=404)
        request(
            "/api/pdf-asset?event=../../outside&index=0", headers=headers, expected=400
        )
        assert api("/api/state")["status"] == "review_only"
        return {
            "status": "passed",
            "science_status": "untested",
            "strict_exit": 2,
            "actual_uploaded_source_and_page_hash_verified": True,
            "no_fake_native_manifest_or_audit": True,
        }
    finally:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
        log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--require-pdf-review", action="store_true")
    args = parser.parse_args()
    where = (
        args.work_dir or Path(tempfile.mkdtemp(prefix="gu-project-interface-"))
    ).resolve()
    if where.exists() and any(where.iterdir()):
        parser.error("choose a new/empty directory; existing evidence is preserved")
    where.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "GRAPHUNSLOPIFY_API": "local",
        "PYTHONIOENCODING": "utf-8",
        "MPLBACKEND": "Agg",
    }

    def cli(*args):
        done = subprocess.run(
            [sys.executable, "-m", "graphunslopify.cli", *map(str, args)],
            env=env,
            cwd=where,
            capture_output=True,
            text=True,
            encoding="utf8",
            timeout=120,
            check=False,
        )
        if done.returncode:
            raise RuntimeError(done.stdout + "\n" + done.stderr)
        return json.loads(done.stdout)

    paper = where / "paper ü with spaces"
    cli("demo", paper, "--json")
    original = (paper / "figure.json").read_bytes()
    value = json.loads(original)
    value["output"]["stem"] = "second"
    (paper / "second.json").write_text(json.dumps(value), encoding="utf8")
    cli("audit-init", paper)
    cli("project-init", paper)
    data = (paper / "results.csv").read_bytes()
    error_log = (where / "server.stderr.log").open("w", encoding="utf8")
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "graphunslopify.cli",
            "project-preview",
            str(paper),
            "--port",
            "0",
        ],
        env=env,
        cwd=where,
        stdout=subprocess.PIPE,
        stderr=error_log,
        text=True,
        encoding="utf8",
    )
    try:
        url = json.loads(server.stdout.readline())["url"]

        def request(path, payload=None, *, token=None, expected=200):
            call = urllib.request.Request(
                url + path,
                data=json.dumps(payload).encode() if payload is not None else None,
                headers={"X-Preview-Token": token} if token else {},
            )
            try:
                response = urllib.request.urlopen(call, timeout=40)
            except urllib.error.HTTPError as problem:
                response = problem
            with response:
                raw = response.read()
                assert response.code == expected, raw
                return raw, dict(response.headers)

        html = request("/")[0].decode()
        token = re.search(r'name="preview-token" content="([^"]+)"', html)[1]

        def api(path, body=None, *, expected=200):
            return json.loads(request(path, body, token=token, expected=expected)[0])

        def audit(expected="passed"):
            api(
                "/api/run",
                {"expected_revision": api("/api/state")["revision"]},
                expected=202,
            )
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                job = api("/api/job")
                if job["phase"] != "running":
                    assert (
                        job["phase"] == "complete"
                        and job["result"]["status"] == expected
                    ), job
                    return api("/api/event?id=" + job["result"]["id"])
                time.sleep(0.05)
            raise AssertionError("actual paper audit did not complete")

        request("/api/state", expected=403)
        request("/api/review", expected=403)
        for asset in (
            "project.js",
            "project-review.js",
            "project-shared.js",
            "project.css",
            "controls.js",
            "app.css",
        ):
            assert request("/" + asset)[0]
        assert len(api("/api/info")["schema"]["oneOf"]) == 21
        first = audit()
        review = api("/api/review")
        assert review == cli("project-review", paper)
        assert (
            review["query_status"] == "ok"
            and review["selection"]["event"] == first["id"]
        )
        assert all(
            row["matches_latest_accepted_inputs"] and not row["rerun_recommended"]
            for row in review["figures"]
        )
        assert all(
            row["groups"]["reproduction"]["audit_compiler_source"]["state"] == "matches"
            for row in review["figures"]
        )
        saved = api("/api/saved-source?event=" + first["id"] + "&figure=figure")
        assert json.loads(saved["text"]) == json.loads(original)
        source = api("/api/figure?id=figure")
        definition = json.loads(source["text"])
        definition["title"] = "Changed in the packaged paper workspace"
        api(
            "/api/definition",
            {
                "id": "figure",
                "spec": definition,
                "expected_revision": source["revision"],
            },
        )
        api(
            "/api/shared",
            {"shared": {}, "expected_revision": source["revision"]},
            expected=400,
        )
        config = paper / "graphunslopify-project/project.json"
        shared_original = config.read_bytes()
        shared_body = {
            "shared": {"output": {"size": "double_column", "dpi": 144}},
            "expected_revision": api("/api/state")["revision"],
        }
        history_before_review = api("/api/state")["history"]
        shared_plan = api("/api/shared-review", shared_body)
        assert shared_plan["can_apply"] and len(shared_plan["affected_ids"]) == 2
        assert shared_plan["execution"] == "not_run"
        assert api("/api/state")["history"] == history_before_review
        assert config.read_bytes() == shared_original
        shared_event = api(
            "/api/shared-apply",
            {**shared_body, "proposal_token": shared_plan["proposal_token"]},
        )
        second = audit()
        for figure in second["result"]["audit"]["figures"]:
            assert figure["report"]["spec"]["output"]["size"] == "double_column"
        raw, headers = request(
            f"/api/preview?event={second['id']}&figure=figure", token=token
        )
        assert raw.startswith(b"\x89PNG") and headers["Content-Type"] == "image/png"
        figure = second["result"]["audit"]["figures"][0]
        index, output = next(
            (i, item)
            for i, item in enumerate(figure["outputs"])
            if item["format"] == "png"
        )
        raw, headers = request(
            f"/api/artifact?event={second['id']}&figure={figure['id']}&index={index}",
            token=token,
        )
        assert (
            hashlib.sha256(raw).hexdigest() == output["sha256"]
            and "attachment" in headers["Content-Disposition"]
        )
        comparison = api(f"/api/comparison?event={second['id']}&figure=figure")
        assert (
            comparison["before"]["status"]
            == comparison["after"]["status"]
            == "available"
        )
        source = api("/api/figure?id=figure")
        wrong = json.loads(source["text"])
        wrong["claims"][0].update(subject="base", reference="ours")
        api(
            "/api/definition",
            {"id": "figure", "spec": wrong, "expected_revision": source["revision"]},
        )
        failed = audit("failed")
        assert failed["result"]["exit_code"] == 2
        review = api("/api/review")
        assert not any(
            row["matches_latest_accepted_inputs"] for row in review["figures"]
        )
        assert any(
            claim["verdict"] == "fails"
            for row in review["figures"]
            for claim in row["groups"]["claims"]["items"]
        )
        historical = api("/api/review?event=" + first["id"])
        assert historical["selection"]["explicit_history_selection"]
        assert not any(
            row["matches_latest_accepted_inputs"] for row in historical["figures"]
        )
        api(
            "/api/definition",
            {
                "id": "figure",
                "spec": definition,
                "expected_revision": api("/api/state")["revision"],
            },
        )
        audit()
        source = api("/api/figure?id=figure")
        clone = {**source["clone"], "id": "duplicate"}
        api(
            "/api/entry",
            {
                "id": "duplicate",
                "entry": clone,
                "mode": "add",
                "expected_revision": source["revision"],
            },
        )
        assert len(api("/api/state")["figures"]) == 3
        audit()
        api(
            "/api/entry",
            {
                "id": "duplicate",
                "mode": "remove",
                "expected_revision": api("/api/state")["revision"],
            },
        )
        assert len(api("/api/state")["figures"]) == 2
        assert api("/api/state")["status"] == "needs_audit"
        assert (paper / "results.csv").read_bytes() == data
        assert (
            api("/api/saved-source?event=" + first["id"] + "&figure=figure")["text"]
            == saved["text"]
        )
        assert cli("project-history", paper)["integrity"] == "verified"
        before_undo = {p.name: p.read_bytes() for p in paper.iterdir() if p.is_file()}
        undo_body = {
            "undo_event": shared_event["id"],
            "expected_revision": api("/api/state")["revision"],
        }
        undo_plan = api("/api/shared-review", undo_body)
        assert undo_plan["can_apply"] and undo_plan["operation"] == "undo"
        undone = api(
            "/api/shared-apply",
            {**undo_body, "proposal_token": undo_plan["proposal_token"]},
        )
        assert (
            undone["status"] == "settings_saved"
            and config.read_bytes() == shared_original
        )
        assert before_undo == {
            p.name: p.read_bytes() for p in paper.iterdir() if p.is_file()
        }
        assert api("/api/state")["history"][0]["undo_of"] == shared_event["id"]
        result = {
            "status": "passed",
            "interface": "real loopback CLI/server",
            "figures": 2,
            "shared_settings": "applied to actual reports",
            "shared_review": {
                "status": "passed",
                "affected_native": 2,
                "review_writes_no_settings_or_history": True,
                "actual_strict_reports_use_reviewed_settings": True,
                "undo_restored_original_config_preserving_later_definitions": True,
            },
            "strict_run_exits": [0, 0, 2, 0, 0],
            "source_binding_history_and_stale_guard": "verified",
            "preview_export_and_comparison": "verified bytes",
            "data_unchanged": True,
            "grouped_scientific_review": "actual CLI/HTTP groups, source identity, failed claims and explicit historical selection",
            "work_dir": str(where),
        }
        if args.require_pdf_review:
            output = next(
                item
                for item in first["result"]["audit"]["figures"][0]["outputs"]
                if item["format"] == "pdf"
            )
            pdf = (
                paper
                / "graphunslopify-project/history"
                / first["id"]
                / "audit"
                / output["path"]
            ).read_bytes()
            assert hashlib.sha256(pdf).hexdigest() == output["sha256"]
            result["pdf_review"] = check_pdf_review(where, env, cli, pdf)
        (where / "checks.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf8"
        )
        print(json.dumps(result))
    finally:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
        error_log.close()


if __name__ == "__main__":
    main()
