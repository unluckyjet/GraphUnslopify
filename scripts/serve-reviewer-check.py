"""Owned browser-test workspaces and a controlled loopback reviewer, not inference.

Commands arrive on the parent's stdin. No control endpoint is exposed to a
browser. Public source bytes and scientific failures remain independently visible.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import platform
import shutil
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import graphunslopify
from graphunslopify import preview_reviews, project, review_agent
from graphunslopify.preview import PreviewServer
from graphunslopify.preview_worker import RenderWorker
from graphunslopify.project_preview import ProjectServer
from graphunslopify.review_agent import read_document, restore_plan

ROOT = Path(__file__).resolve().parents[1]


def runtime():
    folder = Path(graphunslopify.__file__).parent
    files = {
        p.relative_to(folder).as_posix(): digest(p.read_bytes())
        for p in folder.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }
    return {
        "python": platform.python_version(),
        "package_root": str(folder),
        "files": files,
    }


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--observe-actual-provider", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(exist_ok=False)
    initial_runtime = runtime()
    # Record both actual platform APIs, including Windows creation/change ctime.
    # This private probe is separate from scientific observations/provider data.
    probe = args.out / "file-stamp-probe.bin"
    probe_bytes = b"native reviewer file metadata probe\r\n"
    probe.write_bytes(probe_bytes)
    os.utime(probe, ns=(978307200000000000, 978307200000000000))
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    path_stat = probe.lstat()
    with probe.open("rb") as stream:
        handle_stat = os.fstat(stream.fileno())
    observed = preview_reviews._file(args.out, probe.name)
    assert observed == {"bytes": len(probe_bytes), "sha256": digest(probe_bytes)}
    file_stamp_probe = {
        "path": {key: str(getattr(path_stat, key)) for key in fields},
        "handle": {key: str(getattr(handle_stat, key)) for key in fields},
        "encoding": "Exact decimal integers;preserved through browser JSON",
        "reader": observed,
        "scope": "Actual private file APIs;no scientific data or inference",
    }
    save(args.out / "file-stamp-probe.json", file_stamp_probe)
    probe.unlink()
    original = (ROOT / "benchmarks/papers/sources/penguins.csv").read_bytes()
    paper = args.out / "paper"
    paper.mkdir()
    (paper / "public-data.csv").write_bytes(original)
    for name, example in [("mass", "penguins-mass"), ("scatter", "penguins-scatter")]:
        spec = json.loads(
            (ROOT / f"examples/published-papers/{example}.json").read_text()
        )
        spec["data"]["path"] = "public-data.csv"
        spec.pop("palette_lock", None)
        spec["output"]["formats"] = ["png"]
        save(paper / (name + ".json"), spec)
    save(
        paper / "graphunslopify.json",
        {
            "schema_version": 1,
            "figures": [{"id": k, "spec": k + ".json"} for k in ["mass", "scatter"]],
        },
    )
    project.initialize_project(paper)
    with contextlib.redirect_stdout(io.StringIO()):
        positive = project.run_project(paper)
    assert positive["exit_code"] == 0, positive
    spec = json.loads((paper / "mass.json").read_text())
    spec["claims"][0].update(subject="female", reference="male")
    save(paper / "mass.json", spec)
    with contextlib.redirect_stdout(io.StringIO()):
        negative = project.run_project(paper)
    assert negative["exit_code"] == 2, negative
    # A separate source-free visual fixture does not borrow numerical checks.
    from matplotlib.figure import Figure

    visual = Figure(figsize=(4, 3))
    visual.text(0.1, 0.5, "PDF visual-only fixture", fontsize=10)
    from matplotlib.backends.backend_pdf import PdfPages

    with PdfPages(args.out / "visual-only.pdf") as pages:
        pages.savefig(visual)
        visual.text(0.1, 0.3, "Second visual-only page", fontsize=10)
        pages.savefig(visual)

    fresh = args.out / "fresh-paper"
    fresh.mkdir()
    (fresh / "public-data.csv").write_bytes(original)
    fresh_figures = []
    for index in range(22):
        name = f"unrun-{index + 1:02d}"
        shutil.copyfile(paper / "mass.json", fresh / (name + ".json"))
        fresh_figures.append({"id": name, "spec": name + ".json"})
    save(fresh / "graphunslopify.json", {"schema_version": 1, "figures": fresh_figures})
    project.initialize_project(fresh)

    lock = threading.Lock()
    gate = threading.Event()
    gate.set()
    state = {"mode": "valid", "calls": []}
    actual_calls = []
    transport_original = review_agent.reviewer_model_text

    def observe_provider(config, body, **kwargs):
        with lock:
            index = len(actual_calls) + 1
            actual_calls.append(
                {
                    "bytes": len(body),
                    "sha256": digest(body),
                    "provider": config.public(),
                }
            )
        text = transport_original(config, body, **kwargs)
        save(
            args.out / f"actual-provider-{index}-unverified-text.json",
            {
                "label": "Unverified provider diagnostic,not accepted science",
                "text": text,
            },
        )
        return text

    if args.observe_actual_provider:
        review_agent.reviewer_model_text = observe_provider

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            body = json.loads(raw)
            content = (
                body["messages"][1]["content"]
                if "messages" in body
                else body["input"][0]["content"]
            )
            packet = json.loads(content)["deterministic_evidence"]
            with lock:
                mode = state["mode"]
                state["calls"].append(
                    {
                        "sha256": digest(raw),
                        "bytes": len(raw),
                        "figures": [f["key"] for f in packet["figures"]],
                        "execution_statuses": [
                            f["execution_status"] for f in packet["figures"]
                        ],
                        "key_in_body": b"REVIEWER_TEST_KEY" in raw,
                        "authorization_present": "Authorization" in self.headers,
                        "mode": mode,
                    }
                )
            if mode == "held":
                gate.wait(30)
            figure = packet["figures"][0]["key"]
            reference = next(
                r["id"] for r in packet["evidence_ids"] if r["figure_key"] == figure
            )
            reply = {
                "summary": 'Unverified literal text: <img src="https://invalid.example/x" onerror="window.REVIEW_HTML_EXECUTED=true">',
                "suggestions": [
                    {
                        "figure_key": figure,
                        "topic": "comparison",
                        "suggestion": "Review the supplied evidence with the author.",
                        "why": "Recorded checks do not establish experimental design.",
                        "evidence_ids": [reference],
                    }
                ],
                "author_questions": [
                    "What study design supports the intended interpretation?"
                ],
            }
            text = (
                "INVALID_PRIVATE_PROVIDER_REPLY"
                if mode == "invalid"
                else json.dumps(reply)
            )
            response = (
                {"choices": [{"finish_reason": "stop", "message": {"content": text}}]}
                if "messages" in body
                else {
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": text}],
                        }
                    ],
                }
            )
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                self.send_response(503 if mode == "error" else 200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())

    provider = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    stage_root = args.out / "stage-control"
    stage_root.mkdir()
    os.environ["GRAPHUNSLOPIFY_STAGE_CHECK_DIR"] = str(stage_root)
    native, saved, fresh_server = (
        PreviewServer(),
        ProjectServer(paper),
        ProjectServer(fresh),
    )
    # Reuse the existing real-render pre-check hold. It changes timing only;
    # original native checks and exports still execute after release.
    native.state.worker.close()
    native.state.worker = RenderWorker(
        native.state.root,
        profile_driver=ROOT / "scripts/serve-preview-staging-check.py",
        cache_statistics=True,
    )
    run_original = native.state._run_generated

    def profiled_run(command, folder, timeout):
        script = next(x for x in command[3:] if x.endswith(".py"))
        return run_original(
            [
                *command[:3],
                "--timings",
                str(folder / "phase-timings.json"),
                "--profile-script",
                script,
                *command[3:],
            ],
            folder,
            timeout,
        )

    native.state._run_generated = profiled_run
    active_hold = None
    servers = {
        "native": native,
        "paper": saved,
        "fresh": fresh_server,
        "provider": provider,
    }
    threads = {}
    for name, server in servers.items():
        thread = threading.Thread(
            target=server.serve_forever, name="reviewer-check-" + name
        )
        thread.start()
        threads[name] = thread

    def snapshot():
        with lock:
            calls = list(state["calls"])
        assert runtime() == initial_runtime

        def session_state(server):
            manager = server.state.reviewer
            with manager.lock:
                return [
                    {
                        "id": row["id"],
                        "phase": row["phase"],
                        "cancelled": row["cancelled"].is_set(),
                        "result_present": row["result"] is not None,
                        "worker_alive": bool(
                            row["worker"] and row["worker"].is_alive()
                        ),
                    }
                    for row in manager.records.values()
                ]

        return {
            "calls": calls,
            "actual_provider_calls": list(actual_calls),
            "public_source_unchanged": (
                ROOT / "benchmarks/papers/sources/penguins.csv"
            ).read_bytes()
            == original,
            "paper_source_sha256": digest((paper / "public-data.csv").read_bytes()),
            "paper_definitions": {
                name: digest((paper / (name + ".json")).read_bytes())
                for name in ["mass", "scatter"]
            },
            "runtime_unchanged": True,
            "native_active_review": native.state.reviewer.active is not None,
            "paper_active_review": saved.state.reviewer.active is not None,
            "native_sessions": session_state(native),
            "paper_sessions": session_state(saved),
            "stage_entered": bool(
                active_hold and (stage_root / (active_hold + ".entered")).is_file()
            ),
        }

    def emit(value):
        print(json.dumps(value), flush=True)

    emit(
        {
            "runtime": {**initial_runtime, "file_stamp_probe": file_stamp_probe},
            "native": f"http://127.0.0.1:{native.server_port}/",
            "paper": f"http://127.0.0.1:{saved.server_port}/",
            "fresh": f"http://127.0.0.1:{fresh_server.server_port}/",
            "provider": f"http://127.0.0.1:{provider.server_port}/model",
            "paper_path": str(paper),
            "public_source": str(ROOT / "benchmarks/papers/sources/penguins.csv"),
            "public_source_sha256": digest(original),
            "native_spec": spec,
            "pdf": str(args.out / "visual-only.pdf"),
        }
    )
    try:
        import sys

        for line in sys.stdin:
            command = json.loads(line)
            operation = command.get("operation")
            if operation == "mode":
                with lock:
                    state["mode"] = command["mode"]
                gate.clear() if command["mode"] == "held" else gate.set()
                emit({"ok": True})
            elif operation == "release":
                gate.set()
                emit({"ok": True})
            elif operation == "snapshot":
                emit(snapshot())
            elif operation == "hold-native-check":
                active_hold = uuid.uuid4().hex
                save(
                    stage_root / "control.json",
                    {"title": command["title"], "nonce": active_hold},
                )
                emit({"held": True})
            elif operation == "release-native-check":
                assert active_hold
                (stage_root / (active_hold + ".release")).touch()
                emit({"released": True})
            elif operation == "damage-paper-source":
                (paper / "public-data.csv").write_bytes(original + b"\n")
                emit({"changed": True})
            elif operation == "restore-paper-source":
                (paper / "public-data.csv").write_bytes(original)
                emit({"restored": True})
            elif operation == "restore-paper-request":
                path = Path(command["path"]).resolve(strict=True)
                assert path.is_relative_to(args.out.parent.resolve())
                plan = restore_plan(
                    read_document(path), paper, api_key="REVIEWER_TEST_KEY"
                )
                emit(
                    {
                        "restored": True,
                        "request_sha256": plan.disclosure()["request_sha256"],
                    }
                )
            elif operation == "damage-native-export":
                record = native.state.runs[command["run_id"]]
                exports = [p for n, p in record["files"].items() if n.endswith(".png")]
                assert len(exports) == 1
                exports[0].write_bytes(b"changed actual native export")
                emit({"damaged": True})
            elif operation == "stop":
                emit(snapshot())
                break
            else:
                raise ValueError("Unknown owned reviewer fixture operation")
    finally:
        review_agent.reviewer_model_text = transport_original
        gate.set()
        if active_hold:
            (stage_root / (active_hold + ".release")).touch()
        for name in ["native", "paper", "fresh", "provider"]:
            servers[name].shutdown()
            threads[name].join(15)
            assert not threads[name].is_alive()
            servers[name].server_close()
        assert (
            ROOT / "benchmarks/papers/sources/penguins.csv"
        ).read_bytes() == original


if __name__ == "__main__":
    main()
