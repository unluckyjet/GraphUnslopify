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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path)
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
        api(
            "/api/shared",
            {
                "shared": {"output": {"size": "double_column", "dpi": 144}},
                "expected_revision": api("/api/state")["revision"],
            },
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
        result = {
            "status": "passed",
            "interface": "real loopback CLI/server",
            "figures": 2,
            "shared_settings": "applied to actual reports",
            "strict_run_exits": [0, 0, 2, 0, 0],
            "source_binding_history_and_stale_guard": "verified",
            "preview_export_and_comparison": "verified bytes",
            "data_unchanged": True,
            "grouped_scientific_review": "actual CLI/HTTP groups, source identity, failed claims and explicit historical selection",
            "work_dir": str(where),
        }
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
