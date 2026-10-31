"""Library reuse must preserve actual figures and fail closed on lifecycle errors."""

from __future__ import annotations

import gc
import hashlib
import json
import os
import subprocess
import sys
import uuid
import weakref
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from PIL import Image

from graphunslopify import preview_worker
from graphunslopify.demo import write_demo
from graphunslopify.preview import PreviewState
from graphunslopify.preview_worker import RenderWorker, arguments
from graphunslopify.worker_process import JsonWorker, WorkerError

ROOT = Path(__file__).resolve().parents[2]


def private_job(worker, code):
    folder = worker.runs / uuid.uuid4().hex
    folder.mkdir()
    program = folder / "figure.py"
    program.write_text(code)
    return [sys.executable, "-c", "pass", *arguments(program, "figure")], folder


def call(worker, code, timeout=30):
    command, folder = private_job(worker, code)
    return worker.run(command, folder, timeout)


@pytest.fixture
def worker(tmp_path):
    service = RenderWorker(tmp_path)
    try:
        yield service
    finally:
        service.close()


def image_signature(state, answer):
    record = state.runs[answer["run_id"]]
    image = next(path for path in record["files"].values() if path.suffix == ".png")
    with Image.open(image) as picture:
        rgba = picture.convert("RGBA")
        return rgba.size, hashlib.sha256(rgba.tobytes()).hexdigest()


def test_cross_case_native_semantics_pixels_and_strict_negatives(tmp_path):
    base = ROOT / "benchmarks/rendering"
    protocol = json.loads((base / "protocol.json").read_text())
    process = PreviewState(tmp_path / "process", 1000000)
    service = PreviewState(tmp_path / "worker", 1000000, reuse_renderer=True)
    expected = {}
    pids = []
    fields = [
        "spec_hash",
        "spec",
        "data",
        "script",
        "status",
        "ok",
        "findings",
        "inspection",
        "panels",
        "claims",
        "significance",
        "annotations",
        "untested",
        "alt_text",
        "policy",
        "exit_code",
    ]
    try:
        for number, case in enumerate(protocol["cases"]):
            spec = json.loads((base / case["spec"]).read_text())
            raw = (base / case["data"]).read_bytes()
            uploaded = process.upload("data.csv", raw)
            answer = process.render(
                {
                    "client": "reference",
                    "generation": number,
                    "data_id": uploaded["id"],
                    "spec": spec,
                }
            )
            assert answer["exit_code"] == case["expected_exit_code"]
            expected[case["id"]] = (
                {k: answer["report"][k] for k in fields},
                image_signature(process, answer),
            )
        for round_number in range(2):
            for number, case in enumerate(protocol["cases"]):
                uploaded = service.upload("data.csv", (base / case["data"]).read_bytes())
                answer = service.render(
                    {
                        "client": "worker",
                        "generation": round_number * 5 + number,
                        "data_id": uploaded["id"],
                        "spec": json.loads((base / case["spec"]).read_text()),
                    }
                )
                assert answer["exit_code"] == case["expected_exit_code"]
                assert (
                    {k: answer["report"][k] for k in fields},
                    image_signature(service, answer),
                ) == expected[case["id"]]
                assert not answer["export_errors"] and not answer["stale"]
                for key in ["edit_map", "diagnostic_map"]:
                    assert answer[key]["available"]
                    assert answer[key]["run_id"] == answer["run_id"]
                    assert answer[key]["spec_hash"] == answer["report"]["spec_hash"]
                execution = answer["execution"]
                assert execution["mode"] == "worker"
                assert execution["request_number"] == round_number * 5 + number + 1
                pids.append(execution["pid"])
        assert len(set(pids)) == 1
    finally:
        service.close()
        process.close()


def test_known_process_context_is_reset_between_jobs(worker):
    first = call(
        worker,
        """import os,sys,json,random,numpy as np,matplotlib.pyplot as plt
print(json.dumps({'random':random.random(),'numpy':float(np.random.random())}))
PRIVATE_LEAK='old-data'
os.environ['GU_PRIVATE_LEAK']='old-data'
sys.path.append('old-private-path')
plt.rcParams['font.size']=79
plt.figure()
random.seed(1)
np.random.seed(1)
""",
    )
    original = json.loads(first.stdout)
    second = call(
        worker,
        """import os,sys,json,random,numpy as np,matplotlib.pyplot as plt
print(json.dumps({'random':random.random(),'numpy':float(np.random.random()),'namespace':globals().get('PRIVATE_LEAK'),'environment':os.environ.get('GU_PRIVATE_LEAK'),'path':'old-private-path' in sys.path,'font':plt.rcParams['font.size'],'figures':plt.get_fignums()}))
""",
    )
    value = json.loads(second.stdout)
    assert value["environment"] is None and not value["path"]
    assert value["font"] != 79 and value["figures"] == []
    assert value["namespace"] is None
    assert {key: value[key] for key in original} == original
    assert first.execution["pid"] == second.execution["pid"]


def test_timeout_kills_owned_worker_and_next_request_recovers(worker):
    call(worker, "print('ready')")
    old = worker.process.connection.process
    with pytest.raises(subprocess.TimeoutExpired):
        call(worker, "import time; time.sleep(60)", timeout=0.2)
    assert old.poll() is not None
    recovered = call(worker, "print('recovered')")
    assert recovered.stdout.strip() == "recovered"
    assert recovered.execution["pid"] != old.pid


def test_startup_is_included_in_the_request_deadline(tmp_path):
    service = JsonWorker(
        [sys.executable, "-c", "import time; time.sleep(60)"], tmp_path, kind="renderer"
    )
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            service.request({}, timeout=0.1)
        assert service.connection is None
    finally:
        service.close()


def test_measurement_driver_cannot_be_requested_without_private_authorization(worker):
    command, folder = private_job(worker, "raise AssertionError('must not execute')")
    command[3:3] = ["--timings", str(folder / "phase-timings.json"), "--profile-script", command[9]]
    with pytest.raises(WorkerError, match="authorized measurement"):
        worker.run(command, folder, 30)
    assert worker.process.connection is None


def test_crash_eof_never_returns_a_scientific_success(worker):
    with pytest.raises(WorkerError, match="closed"):
        call(worker, "import os; os._exit(7)")
    assert worker.process.connection is None
    assert call(worker, "print('after-crash')").stdout.strip() == "after-crash"


def test_request_bound_recycles_and_close_is_terminal(tmp_path):
    service = RenderWorker(tmp_path, max_jobs=2)
    try:
        pids = [call(service, "print('ok')").execution["pid"] for _ in range(3)]
        assert pids[0] == pids[1] and pids[2] != pids[1]
        process = service.process.connection.process
    finally:
        service.close()
    assert process.poll() is not None
    with pytest.raises(WorkerError, match="closed"):
        call(service, "print('cannot-run')")


def test_owner_collection_stops_process_without_reader_reference_cycle(tmp_path):
    service = RenderWorker(tmp_path)
    call(service, "print('ok')")
    process = service.process.connection.process
    owner = weakref.ref(service.process)
    del service
    gc.collect()
    assert owner() is None
    assert process.wait(timeout=5) is not None


def test_concurrent_requests_keep_their_own_response_and_identity(worker):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda value: call(worker, f"print({value!r})"), ["first", "second"])
        )
    assert [r.stdout.strip() for r in results] == ["first", "second"]
    assert len({r.execution["request_id"] for r in results}) == 2
    assert len({r.execution["pid"] for r in results}) == 1


def test_changed_parent_environment_recycles_the_actual_process(worker, monkeypatch):
    first = call(worker, "import os;print(os.environ.get('GU_ENV_REVISION','initial'))")
    monkeypatch.setenv("GU_ENV_REVISION", "changed")
    second = call(worker, "import os;print(os.environ['GU_ENV_REVISION'])")
    assert first.stdout.strip() == "initial" and second.stdout.strip() == "changed"
    assert first.execution["pid"] != second.execution["pid"]


def test_source_change_refuses_cached_runtime(worker, monkeypatch):
    first = call(worker, "print('initial')")
    process = worker.process.connection.process
    monkeypatch.setattr(preview_worker, "_package_signature", lambda: "changed-source")
    with pytest.raises(WorkerError, match="source changed"):
        call(worker, "print('must-not-run')")
    assert (
        process.poll() is not None and first.execution["runtime_source_sha256"] != "changed-source"
    )


def test_script_tamper_between_parent_and_service_is_refused(worker, monkeypatch):
    command, folder = private_job(worker, "print('original')")
    original = worker.process.request

    def tamper(payload, timeout):
        (folder / "figure.py").write_text("print('changed')")
        return original(payload, timeout)

    monkeypatch.setattr(worker.process, "request", tamper)
    with pytest.raises(WorkerError, match="does not match"):
        worker.run(command, folder, 30)


def test_foreign_path_and_redirected_native_arguments_are_refused(worker, tmp_path):
    foreign = tmp_path / "foreign.py"
    foreign.write_text("raise AssertionError('foreign code executed')")
    command, folder = private_job(worker, "print('owned')")
    command[9] = str(foreign)
    with pytest.raises(WorkerError):
        worker.run(command, folder, 30)
    command, folder = private_job(worker, "print('owned')")
    command[-1] = "../foreign.report.json"
    with pytest.raises(WorkerError, match="arguments"):
        worker.run(command, folder, 30)
    assert not (worker.root.parent / "foreign.report.json").exists()


def test_nonpositive_lifecycle_and_timeout_bounds_refuse():
    for bound in [0, -1, True, 129]:
        with pytest.raises(ValueError):
            JsonWorker([sys.executable], Path.cwd(), kind="test", max_requests=bound)


def test_rpc_wrong_request_identity_cannot_be_accepted(tmp_path):
    code = """import os,json,sys
print(json.dumps({'protocol':1,'ready':True,'kind':'test','pid':os.getpid()}),flush=True)
request=json.loads(sys.stdin.buffer.readline())
print(json.dumps({'protocol':1,'id':'wrong','ok':True,'result':'stale'}),flush=True)
"""
    service = JsonWorker([sys.executable, "-u", "-c", code], tmp_path, kind="test")
    try:
        with pytest.raises(WorkerError, match="another request"):
            service.request({}, 10)
        assert service.connection is None
    finally:
        service.close()


def test_request_backpressure_is_inside_deadline_and_closes_writer(tmp_path):
    code = """import os,json,time
print(json.dumps({'protocol':1,'ready':True,'kind':'test','pid':os.getpid()}),flush=True)
time.sleep(60)
"""
    service = JsonWorker([sys.executable, "-u", "-c", code], tmp_path, kind="test")
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            service.request({"large": "x" * (3 * 1024 * 1024)}, 0.3)
        assert service.connection is None
    finally:
        service.close()


def test_rpc_response_frame_limit_fails_closed(tmp_path, monkeypatch):
    from graphunslopify import worker_process

    monkeypatch.setattr(worker_process, "MAX_FRAME", 1024)
    code = """import os,json,sys
print(json.dumps({'protocol':1,'ready':True,'kind':'test','pid':os.getpid()}),flush=True)
sys.stdin.buffer.readline()
print('x'*4096,flush=True)
"""
    service = JsonWorker([sys.executable, "-u", "-c", code], tmp_path, kind="test")
    try:
        with pytest.raises(WorkerError, match="frame limit"):
            service.request({}, 10)
    finally:
        service.close()


def test_server_shutdown_closes_worker_before_removing_owned_files():
    from graphunslopify.preview import PreviewServer

    with PreviewServer(0) as server:
        spec_path = write_demo(server.state.root / "demo")
        data = server.state.upload("data.csv", (spec_path.parent / "results.csv").read_bytes())
        answer = server.state.render(
            {
                "client": "shutdown",
                "generation": 0,
                "data_id": data["id"],
                "spec": json.loads(spec_path.read_text()),
            }
        )
        assert answer["report"]["status"] == "passed"
        process = server.state.worker.process.connection.process
        directory = server.state.root
    assert process.poll() is not None and not directory.exists()


def test_stale_generation_cannot_republish_worker_output(tmp_path, monkeypatch):
    import threading

    state = PreviewState(tmp_path, 1000000, reuse_renderer=True)
    spec_path = write_demo(tmp_path / "demo")
    data = state.upload("data.csv", (spec_path.parent / "results.csv").read_bytes())
    payload = {
        "client": "generation",
        "generation": 1,
        "data_id": data["id"],
        "spec": json.loads(spec_path.read_text()),
    }
    started, release = threading.Event(), threading.Event()
    original = state._run_generated

    def held(command, folder, timeout):
        started.set()
        assert release.wait(10)
        return original(command, folder, timeout)

    monkeypatch.setattr(state, "_run_generated", held)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(state.render, payload)
            assert started.wait(5)
            with state.lock:
                state.generations["generation"] = 2
            release.set()
            older = pending.result(timeout=30)
        assert older["stale"] and older["report"]["status"] == "passed"
        newer = state.render({**payload, "generation": 2})
        assert not newer["stale"] and newer["run_id"] != older["run_id"]
        assert newer["execution"]["pid"] == older["execution"]["pid"]
    finally:
        release.set()
        state.close()


def test_log_budget_failure_discards_success_and_recovers(worker):
    with pytest.raises(WorkerError, match="log exceeds"):
        call(worker, 'print("x"*(9*1024*1024))')
    assert worker.process.connection is None
    assert call(worker, "print('after-budget')").stdout.strip() == "after-budget"


@pytest.mark.skipif(os.name == "nt", reason="POSIX descendant process-group check")
def test_timeout_kills_descendant_that_inherits_worker_pipes(worker):
    import time

    call(worker, "print('ready')")
    command, folder = private_job(
        worker,
        """import subprocess,sys,time
from pathlib import Path
child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
Path('child.pid').write_text(str(child.pid))
time.sleep(60)
""",
    )
    with pytest.raises(subprocess.TimeoutExpired):
        worker.run(command, folder, 0.5)
    child = int((folder / "child.pid").read_text())
    for _ in range(60):
        observation = subprocess.run(
            ["ps", "-p", str(child), "-o", "stat="], capture_output=True, text=True, check=False
        )
        status = observation.stdout.strip()
        if not status or status.startswith("Z"):
            break
        time.sleep(0.05)
    else:
        pytest.fail("Timed-out descendant remains running")
    assert call(worker, "print('after-tree-timeout')").stdout.strip() == "after-tree-timeout"
