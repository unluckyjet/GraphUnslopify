"""Progress images cannot become scientific acceptance or a different attempt."""

from __future__ import annotations

import hashlib
import io
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin

from graphunslopify.preview import PreviewServer
from graphunslopify.preview_staging import PreviewStages, publish_png, stage_paths
from graphunslopify.preview_worker import RenderWorker

ROOT = Path(__file__).resolve().parents[2]


def bound_image(tmp_path, *, manager=None, client="one", generation=1):
    """Metadata-only registry fixture; real canonical execution is tested below."""
    manager = manager or PreviewStages(tmp_path)
    record = manager.begin(client, generation, uuid.uuid4().hex)
    folder = tmp_path / "runs" / uuid.uuid4().hex
    folder.mkdir(parents=True)
    script = folder / "figure.py"
    script.write_text("# registry fixture, not scientific renderer evidence\n")
    data = folder / "data.csv"
    data.write_text("x,y\n1,2\n")
    manager.bind(record, folder, "figure", "data-id", data)
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text(
        "GraphUnslopify",
        json.dumps(
            {
                "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
                "data_sha256_prefix": hashlib.sha256(data.read_bytes()).hexdigest()[:16],
                "spec_hash": "0" * 16,
            }
        ),
    )
    png = folder / "figure.png"
    Image.new("RGB", (24, 18), "navy").save(png, pnginfo=metadata)
    publish_png(png, script)
    return manager, record, png


def test_stage_is_an_isolated_image_without_acceptance_or_final_files(tmp_path):
    manager, record, png = bound_image(tmp_path)
    stage = manager.poll(record.ticket, record.client, record.generation, wait=False)
    assert stage["phase"] == "unverified" and stage["verified"] is False
    assert not {"report", "files", "edit_map", "diagnostic_map", "run_id"}.intersection(stage)
    raw = manager.image(record.ticket, record.client, record.generation, record.identity)
    assert raw == png.read_bytes()
    png.write_bytes(b"producer subsequently changed its own file")
    assert manager.image(record.ticket, record.client, record.generation, record.identity) == raw
    manager.finish(record)
    assert manager.poll(record.ticket, record.client, record.generation)["verified"] is False


def test_same_generation_attempt_supersedes_earlier_image_without_cross_client_leak(tmp_path):
    manager, old, _ = bound_image(tmp_path)
    _, other, _ = bound_image(tmp_path, manager=manager, client="other")
    manager.begin("one", 1, uuid.uuid4().hex)
    assert manager.poll(old.ticket, "one", 1)["phase"] == "stale"
    with pytest.raises(ValueError, match="stale"):
        manager.image(old.ticket, "one", 1, old.identity)
    assert manager.poll(other.ticket, "other", 1)["phase"] == "unverified"
    with pytest.raises(ValueError, match="unavailable"):
        manager.poll(other.ticket, "one", 1)


def test_older_generation_and_invalid_tickets_cannot_replace_current_attempt(tmp_path):
    manager, record, _ = bound_image(tmp_path, generation=4)
    manager.begin("one", 3, uuid.uuid4().hex)
    assert manager.is_current(record)
    with pytest.raises(ValueError, match="already used"):
        manager.begin("one", 5, record.ticket)
    with pytest.raises(ValueError, match="Invalid"):
        manager.begin("one", 5, "../escape")
    assert manager.is_current(record)


def test_pending_completed_and_closed_runs_do_not_invent_images(tmp_path):
    manager = PreviewStages(tmp_path)
    record = manager.begin("one", 1, uuid.uuid4().hex)
    assert manager.poll(record.ticket, "one", 1, wait=False)["phase"] == "pending"
    manager.finish(record)
    assert manager.poll(record.ticket, "one", 1)["phase"] == "unavailable"
    manager.close()
    assert manager.poll(record.ticket, "one", 1)["phase"] == "stale"
    with pytest.raises(ValueError, match="closed"):
        manager.begin("one", 2, uuid.uuid4().hex)


def test_registry_is_bounded_without_evicting_active_current_work(tmp_path):
    manager = PreviewStages(tmp_path, max_records=1)
    first = manager.begin("one", 1, uuid.uuid4().hex)
    with pytest.raises(ValueError, match="Too many"):
        manager.begin("two", 1, uuid.uuid4().hex)
    manager.finish(first)
    manager.begin("two", 1, uuid.uuid4().hex)
    assert len(manager.records) == 1
    with pytest.raises(ValueError, match="unavailable"):
        manager.poll(first.ticket, "one", 1)


@pytest.mark.parametrize("damage", ["acceptance", "script", "data", "phase", "dimensions", "bytes"])
def test_damaged_stage_cannot_supply_current_image(tmp_path, damage):
    manager, record, png = bound_image(tmp_path)
    image, marker = stage_paths(png)
    value = json.loads(marker.read_text())
    if damage == "acceptance":
        value["verified"] = True
    elif damage == "script":
        value["script_sha256"] = "f" * 64
    elif damage == "data":
        value["data_sha256_prefix"] = "f" * 16
    elif damage == "phase":
        value["phase"] = "verified"
    elif damage == "dimensions":
        value["image"]["width"] += 1
    else:
        image.write_bytes(image.read_bytes() + b"changed")
    marker.write_text(json.dumps(value))
    result = manager.poll(record.ticket, "one", 1)
    assert result["phase"] == "unavailable" and result["verified"] is False
    with pytest.raises(ValueError):
        manager.image(record.ticket, "one", 1, record.identity)


def test_closed_registry_wakes_an_inflight_long_poll(tmp_path):
    manager = PreviewStages(tmp_path)
    record = manager.begin("one", 1, uuid.uuid4().hex)
    with ThreadPoolExecutor() as pool:
        pending = pool.submit(manager.poll, record.ticket, "one", 1)
        manager.close()
        assert pending.result(timeout=1)["phase"] == "stale"


def controlled_server(tmp_path):
    """Hold immediately before the genuine checker; never replace its result."""
    entered, release = tmp_path / "check-entered", tmp_path / "release-check"
    driver = tmp_path / "controlled-driver.py"
    driver.write_text(f"""import argparse,sys,time
from pathlib import Path
from graphunslopify import preview_render
p=argparse.ArgumentParser()
p.add_argument("--timings")
p.add_argument("--profile-script")
a,rest=p.parse_known_args()
def observe(phase,namespace):
    if phase!="ready":return
    if Path(namespace["__file__"]).resolve()!=Path(a.profile_script).resolve():
        raise ValueError("Controlled driver script ownership changed")
    original=namespace["check"]
    def check(*args,**kwargs):
        Path({str(entered)!r}).write_text("original checker is next")
        deadline=time.monotonic()+30
        while not Path({str(release)!r}).exists():
            if time.monotonic()>deadline:raise TimeoutError("controlled check was not released")
            time.sleep(.005)
        return original(*args,**kwargs)
    namespace["check"]=check
token=preview_render.NAMESPACE_OBSERVER.set(observe)
sys.argv=[sys.argv[0],*rest]
try:preview_render.main()
finally:preview_render.NAMESPACE_OBSERVER.reset(token)
""")
    server = PreviewServer(0)
    server.state.worker.close()
    server.state.worker = RenderWorker(
        server.state.root, profile_driver=driver, cache_statistics=True
    )
    original = server.state._run_generated

    def run(command, folder, timeout):
        script = next(x for x in command[3:] if x.endswith(".py"))
        return original(
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

    server.state._run_generated = run
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, entered, release


def request(server, path, payload=None, *, authorized=True):
    headers = {"X-Preview-Token": server.state.token} if authorized else {}
    body = json.dumps(payload).encode() if payload is not None else None
    if body is not None:
        headers["Content-Type"] = "application/json"
    with urllib.request.urlopen(
        urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}{path}", data=body, headers=headers
        ),
        timeout=40,
    ) as response:
        raw = response.read()
        return json.loads(raw) if response.headers.get_content_type() == "application/json" else raw


@pytest.mark.parametrize("case,expected", [("demo-bootstrap", 0), ("false-comparison", 2)])
def test_real_http_stage_precedes_genuine_strict_checks_and_cannot_export(tmp_path, case, expected):
    server, thread, entered, release = controlled_server(tmp_path)
    with ThreadPoolExecutor() as pool:
        try:
            spec = json.loads((ROOT / f"benchmarks/staged/cases/{case}/original.json").read_text())
            data = (ROOT / f"benchmarks/rendering/cases/{case}/data.csv").read_bytes()
            upload = server.state.upload("original.csv", data)
            ticket = uuid.uuid4().hex
            payload = {
                "client": "browser",
                "generation": 1,
                "stage_id": ticket,
                "spec": spec,
                "data_id": upload["id"],
            }
            final = pool.submit(request, server, "/api/render", payload)
            deadline = time.monotonic() + 25
            while not entered.exists():
                if final.done():
                    pytest.fail(f"Strict producer ended before controlled check: {final.result()}")
                assert time.monotonic() < deadline
                time.sleep(0.01)
            assert not final.done() and server.state.runs == {}
            query = urllib.parse.urlencode({"client": "browser", "generation": 1})
            stage = request(server, f"/stage/{ticket}?{query}")
            assert stage["phase"] == "unverified" and stage["verified"] is False
            image_url = f"/stage/{ticket}/png?{query}&attempt={stage['attempt']}"
            raw = request(server, image_url)
            assert hashlib.sha256(raw).hexdigest() == stage["image"]["sha256"]
            for path, authorized, status in [
                (image_url, False, 403),
                (f"/stage/{ticket}?client=other&generation=1", True, 404),
                (f"/bundle/{ticket}", True, 404),
                (f"/bundle/{server.state.stages.records[ticket].folder.name}", True, 404),
            ]:
                with pytest.raises(urllib.error.HTTPError) as error:
                    request(server, path, authorized=authorized)
                assert error.value.code == status
            release.touch()
            result = final.result(timeout=25)
            assert result["exit_code"] == expected
            assert result["report"]["status"] == ("passed" if expected == 0 else "failed")
            assert result["execution"]["pid"] == stage["producer_pid"]
            png = next(x for x in result["files"] if x["format"] == "png")
            assert request(server, f"/artifact/{result['run_id']}/{png['name']}") == raw
            with zipfile.ZipFile(
                io.BytesIO(request(server, f"/bundle/{result['run_id']}"))
            ) as bundle:
                assert not any("provisional" in n for n in bundle.namelist())
                assert "data.csv" not in bundle.namelist()
        finally:
            release.touch()
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
    assert server.state.stages.closed.is_set()


@pytest.mark.parametrize("second_client", ["browser", "another-browser"])
def test_real_overlapping_attempts_keep_their_own_current_images(tmp_path, second_client):
    server, thread, entered, release = controlled_server(tmp_path)
    with ThreadPoolExecutor() as pool:
        try:
            spec = json.loads(
                (ROOT / "benchmarks/staged/cases/demo-bootstrap/original.json").read_text()
            )
            upload = server.state.upload(
                "data.csv",
                (ROOT / "benchmarks/rendering/cases/demo-bootstrap/data.csv").read_bytes(),
            )
            first_ticket, second_ticket = uuid.uuid4().hex, uuid.uuid4().hex
            payload = {
                "client": "browser",
                "generation": 1,
                "stage_id": first_ticket,
                "spec": spec,
                "data_id": upload["id"],
            }
            first = pool.submit(request, server, "/api/render", payload)
            deadline = time.monotonic() + 25
            while not entered.exists():
                assert time.monotonic() < deadline
                time.sleep(0.01)
            old = server.state.stages.poll(first_ticket, "browser", 1)
            changed = json.loads(json.dumps(spec))
            changed["title"] = spec.get("title", "") + " current second attempt"
            second = pool.submit(
                request,
                server,
                "/api/render",
                {
                    **payload,
                    "stage_id": second_ticket,
                    "client": second_client,
                    "spec": changed,
                },
            )
            while second_ticket not in server.state.stages.records:
                assert time.monotonic() < deadline
                time.sleep(0.005)
            before = server.state.stages.poll(first_ticket, "browser", 1)
            assert before["phase"] == ("stale" if second_client == "browser" else "unverified")
            release.touch()
            a, b = first.result(timeout=25), second.result(timeout=25)
            assert a["exit_code"] == b["exit_code"] == 0
            assert a["stale"] is (second_client == "browser") and b["stale"] is False
            current = server.state.stages.poll(second_ticket, second_client, 1)
            assert (
                current["phase"] == "unverified"
                and current["image"]["sha256"] != old["image"]["sha256"]
            )
            assert current["script_sha256"] == b["report"]["script"]["sha256"]
            assert current["producer_pid"] == b["execution"]["pid"]
            assert b["execution"]["request_id"] != a["execution"]["request_id"]
        finally:
            release.touch()
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


def test_server_close_joins_a_producer_with_an_available_unverified_image(tmp_path):
    server, thread, entered, release = controlled_server(tmp_path)
    with ThreadPoolExecutor() as pool:
        try:
            spec = json.loads(
                (ROOT / "benchmarks/staged/cases/demo-bootstrap/original.json").read_text()
            )
            upload = server.state.upload(
                "data.csv",
                (ROOT / "benchmarks/rendering/cases/demo-bootstrap/data.csv").read_bytes(),
            )
            ticket = uuid.uuid4().hex
            final = pool.submit(
                request,
                server,
                "/api/render",
                {
                    "client": "closing",
                    "generation": 1,
                    "stage_id": ticket,
                    "spec": spec,
                    "data_id": upload["id"],
                },
            )
            deadline = time.monotonic() + 25
            while not entered.exists():
                assert time.monotonic() < deadline
                time.sleep(0.01)
            assert server.state.stages.poll(ticket, "closing", 1)["phase"] == "unverified"
            native = server.state.worker.process.connection.process
            compiler = server.state.translator.process.connection.process
            folder = server.state.root
            server.shutdown()
            closing = pool.submit(server.server_close)
            time.sleep(0.03)
            assert not closing.done() and native.poll() is None
            release.touch()
            assert final.result(timeout=25)["exit_code"] == 0
            closing.result(timeout=5)
            assert native.poll() is not None and compiler.poll() is not None
            assert not folder.exists() and server.state.stages.closed.is_set()
        finally:
            release.touch()
            server.server_close()
            thread.join(timeout=3)
