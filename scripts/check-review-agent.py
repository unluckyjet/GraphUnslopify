"""Real public-paper reviewer evidence; HTTP contracts or explicit actual inference.

Default CI uses a controlled loopback provider, never downloads/calls a model.
Supply --endpoint/--model to make one consented actual inference request. Only
public source/check evidence is used; the model reply is not certified science.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import platform
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import graphunslopify
from graphunslopify import project
from graphunslopify.drafts import DraftProvider, _encoded
from graphunslopify.project_review import project_review
from graphunslopify.review_agent import (
    FigureReviewPlan,
    InvalidReview,
    review_document,
    write_document,
)

ROOT = Path(__file__).resolve().parents[1]


def save(path, value):
    path.write_text(
        json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf8"
    )


def inventory(root):
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }


@contextlib.contextmanager
def controlled_provider():
    reply = {
        "summary": "The recorded failed comparison needs author attention.",
        "suggestions": [
            {
                "figure_key": "mass",
                "topic": "claims",
                "suggestion": "Review the declared direction of the sex comparison.",
                "why": "The supplied saved claim has verdict fails.",
                "evidence_ids": ["F1.claims.1"],
            }
        ],
        "author_questions": [
            "What sampling design supports the intended interpretation?"
        ],
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            self.server.calls.append(raw)
            body = {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps(reply)}],
                    }
                ],
            }
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        server.calls = []
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            yield (
                DraftProvider(
                    f"http://127.0.0.1:{server.server_port}/model",
                    "controlled-contract-provider",
                ),
                server.calls,
            )
        finally:
            server.shutdown()
            thread.join(5)


def cli(*arguments):
    completed = subprocess.run(
        [sys.executable, "-m", "graphunslopify.cli", *map(str, arguments)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.stdout, completed.stderr[-2000:]
    return completed.returncode, json.loads(completed.stdout)


def check(out, provider, calls, expected_sha=None, *, structured_output=True):
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    dirty = bool(
        subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip()
    )
    if expected_sha:
        assert revision == expected_sha and not dirty
    package = inventory(Path(graphunslopify.__file__).parent)
    assert package == inventory(ROOT / "python/graphunslopify")
    save(
        out / "package-binding.json", {"files": package, "matched_files": len(package)}
    )
    paper = out / "public-paper"
    paper.mkdir()
    original = (ROOT / "benchmarks/papers/sources/penguins.csv").read_bytes()
    source = paper / "public-data.csv"
    source.write_bytes(original)
    for name, example in [("mass", "penguins-mass"), ("scatter", "penguins-scatter")]:
        spec = json.loads(
            (ROOT / f"examples/published-papers/{example}.json").read_text()
        )
        spec["data"]["path"] = source.name
        save(paper / f"{name}.json", spec)
    save(
        paper / "graphunslopify.json",
        {
            "schema_version": 1,
            "figures": [
                {"id": key, "spec": key + ".json"} for key in ("mass", "scatter")
            ],
        },
    )
    project.initialize_project(paper)
    with contextlib.redirect_stdout(io.StringIO()):
        passed = project.run_project(paper)
    assert passed["exit_code"] == 0, passed
    positive = project_review(paper)
    assert positive["figures"][0]["groups"]["claims"]["items"][0]["verdict"] == "holds"
    save(out / "positive-evidence.json", positive)
    path = paper / "mass.json"
    spec = json.loads(path.read_text())
    spec["claims"][0].update(subject="female", reference="male")
    save(path, spec)
    with contextlib.redirect_stdout(io.StringIO()):
        failed = project.run_project(paper)
    assert failed["exit_code"] == 2
    evidence = project_review(paper)
    assert evidence["figures"][0]["groups"]["claims"]["items"][0]["verdict"] == "fails"
    save(out / "failed-evidence.json", evidence)
    before = inventory(paper)
    plan = FigureReviewPlan(
        provider,
        paper,
        question="What would a skeptical reviewer criticize about these figures?",
        author_context="Public observational Palmer penguins data; no experimental independence claim.",
        structured_output=structured_output,
    )
    document = review_document(plan)
    write_document(document, out / "reviewed-request.json")
    disclosure = plan.disclosure()
    for marker in (
        str(paper),
        "public-data.csv",
        "bill_length_mm,bill_depth_mm",
        provider.api_key,
    ):
        if marker:
            assert marker not in json.dumps(disclosure)
    try:
        plan.request()
        raise AssertionError("Unconsented request succeeded")
    except ValueError as problem:
        assert "consent" in str(problem)
    assert calls is None or not calls
    try:
        result = plan.request(consent=True, consent_sha256=disclosure["consent_sha256"])
    except InvalidReview as problem:
        save(
            out / "invalid-model-reply.json",
            {"error": str(problem), "reply": problem.reply},
        )
        raise
    save(out / "review-result.json", result)
    assert (
        result["deterministic_evidence"]["figures"][0]["groups"]["claims"]
        == evidence["figures"][0]["groups"]["claims"]
    )
    assert (
        result["status"] == "completed"
        and result["scientific_acceptance"] == "not_established"
    )
    assert (
        not result["applied"]
        and not result["deterministic_evidence"]["images_supplied"]
    )
    assert before == inventory(paper)
    if calls is not None:
        assert calls == [_encoded(disclosure["request"])]
        code, refused = cli(
            "review-agent-run",
            out / "reviewed-request.json",
            "--path",
            paper,
            "--out",
            out / "refused.json",
        )
        assert code == 2 and "consent" in refused["error"] and len(calls) == 1
        code, cli_result = cli(
            "review-agent-run",
            out / "reviewed-request.json",
            "--path",
            paper,
            "--consent",
            "--consent-sha256",
            disclosure["consent_sha256"],
            "--out",
            out / "cli-result.json",
        )
        assert (
            code == 0
            and cli_result["deterministic_evidence"] == result["deterministic_evidence"]
        )
        assert len(calls) == 2 and calls[1] == calls[0]
    stale = FigureReviewPlan(provider, paper)
    source.write_bytes(original + b"\n")
    try:
        stale.request(consent=True, consent_sha256=stale.disclosure()["consent_sha256"])
        raise AssertionError("Stale evidence reached the provider")
    except ValueError as problem:
        assert "evidence changed" in str(problem)
    finally:
        source.write_bytes(original)
    assert calls is None or len(calls) == 2
    assert source.read_bytes() == original
    assert (ROOT / "benchmarks/papers/sources/penguins.csv").read_bytes() == original
    assert before == inventory(paper)
    return {
        "status": "passed",
        "source_revision": revision,
        "worktree_dirty": dirty,
        "python": platform.python_version(),
        "provider_kind": "actual_inference"
        if calls is None
        else "controlled_HTTP_contract",
        "provider": provider.public(),
        "structured_output": structured_output,
        "public_source_sha256": hashlib.sha256(original).hexdigest(),
        "positive_claim": "holds",
        "failed_claim": "fails",
        "selected_figures": 2,
        "unconsented_refused": True,
        "source_change_refused": True,
        "project_bytes_unchanged": True,
        "request_sha256": disclosure["request_sha256"],
        "consent_sha256": disclosure["consent_sha256"],
        "request_bytes": disclosure["request_bytes"],
        "calls": 1 if calls is None else len(calls),
        "package_files": len(package),
        "scope": "Actual saved public native results and reviewer integration; model prose is unverified. No independent judgment, quality, productivity or adoption claim.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--expected-sha")
    parser.add_argument("--endpoint")
    parser.add_argument("--model")
    parser.add_argument("--json-mode", action="store_true")
    parser.add_argument(
        "--protocol", choices=["responses", "chat"], default="responses"
    )
    args = parser.parse_args()
    if bool(args.endpoint) != bool(args.model):
        parser.error(
            "--endpoint and --model are required together for actual inference"
        )
    args.out_dir.mkdir(parents=True, exist_ok=False)
    try:
        if args.endpoint:
            provider = DraftProvider(
                args.endpoint,
                args.model,
                args.protocol,
                os.environ.get("GRAPHUNSLOPIFY_DRAFT_API_KEY", ""),
            )
            result = check(
                args.out_dir,
                provider,
                None,
                args.expected_sha,
                structured_output=not args.json_mode,
            )
        else:
            with controlled_provider() as (provider, calls):
                result = check(
                    args.out_dir,
                    provider,
                    calls,
                    args.expected_sha,
                    structured_output=not args.json_mode,
                )
        save(args.out_dir / "verification.json", result)
        print(json.dumps(result, indent=2))
    except Exception as problem:
        save(
            args.out_dir / "verification.json",
            {"status": "failed", "error": str(problem)},
        )
        raise


if __name__ == "__main__":
    main()
