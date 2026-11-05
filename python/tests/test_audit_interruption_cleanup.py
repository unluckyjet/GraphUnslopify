"""Real child processes must be reaped after callback/communication interruption."""

import json
import subprocess
import sys
import time

import pytest

from graphunslopify import audit


def test_audit_worker_cannot_read_the_owners_control_pipe(tmp_path):
    """Keep the real owner's stdin open while its background audit completes."""
    receipt = tmp_path / "child-input.json"
    harness = tmp_path / "owner.py"
    harness.write_text(
        "import json, sys, threading\n"
        "from pathlib import Path\n"
        "from graphunslopify.audit import _run\n"
        "def work():\n"
        "    try:\n"
        "        child = _run([sys.executable, '-c', "
        '"import sys; print(repr(sys.stdin.buffer.read(1)))"], '
        "Path.cwd(), 3)\n"
        "        result = {'status': 'complete', 'exit': child.returncode, "
        "'stdout': child.stdout}\n"
        "    except Exception as problem:\n"
        "        result = {'status': 'failed', 'error': str(problem)}\n"
        "    Path('child-input.tmp').write_text(json.dumps(result))\n"
        "    Path('child-input.tmp').replace('child-input.json')\n"
        "worker = threading.Thread(target=work)\n"
        "worker.start()\n"
        "control = sys.stdin.readline()\n"
        "worker.join(8)\n"
        "assert not worker.is_alive()\n"
        "print(json.dumps({'control': control}))\n",
        encoding="utf8",
    )
    owner = subprocess.Popen(
        [sys.executable, str(harness)],
        cwd=tmp_path,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        end = time.monotonic() + 10
        while not receipt.exists() and owner.poll() is None and time.monotonic() < end:
            time.sleep(0.02)
        assert receipt.exists(), "Audit did not finish while the owner's control pipe stayed open"
        outcome = json.loads(receipt.read_text())
    finally:
        try:
            stdout, stderr = owner.communicate("controller-only\n", timeout=12)
        finally:
            if owner.poll() is None:
                owner.kill()
                owner.communicate(timeout=5)
    assert owner.returncode == 0, stderr
    assert json.loads(stdout) == {"control": "controller-only\n"}
    assert outcome == {"status": "complete", "exit": 0, "stdout": "b''\n"}


@pytest.mark.parametrize("phase", ["callback", "communicate"])
def test_actual_audit_interruption_reaps_child(tmp_path, monkeypatch, phase):
    original = subprocess.Popen
    created = []

    class ActualChild(original):
        def __init__(self, *args, **kwargs):
            self.inject = phase == "communicate" and not created
            super().__init__(*args, **kwargs)
            created.append(self)

        def communicate(self, *args, **kwargs):
            if self.inject:
                self.inject = False
                raise KeyboardInterrupt("Actual child communication interrupted")
            return super().communicate(*args, **kwargs)

    def on_start():
        if phase == "callback":
            raise KeyboardInterrupt("Actual child start callback interrupted")

    monkeypatch.setattr(subprocess, "Popen", ActualChild)
    try:
        with pytest.raises(KeyboardInterrupt):
            audit._run(
                [sys.executable, "-c", "import time;time.sleep(30)"],
                tmp_path,
                60,
                on_start=on_start,
            )
        assert created and created[0].poll() is not None
    finally:
        for child in created:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=5)
