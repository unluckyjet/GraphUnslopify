"""Real child processes must be reaped after callback/communication interruption."""

import subprocess
import sys

import pytest

from graphunslopify import audit


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
