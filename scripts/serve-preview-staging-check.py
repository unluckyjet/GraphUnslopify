"""Actual editor with a controlled pre-check hold; never a performance server."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path


def profile():
    from graphunslopify import preview_render

    parser = argparse.ArgumentParser()
    parser.add_argument("--timings", type=Path)
    parser.add_argument("--profile-script", type=Path)
    args, rest = parser.parse_known_args()
    root = Path(os.environ["GRAPHUNSLOPIFY_STAGE_CHECK_DIR"]).resolve()

    def observe(phase, namespace):
        if phase != "ready":
            return
        if Path(namespace["__file__"]).resolve() != args.profile_script.resolve():
            raise ValueError("Controlled checker script ownership changed")
        original = namespace["check"]

        def check(*positional, **keywords):
            config = root / "control.json"
            value = json.loads(config.read_text()) if config.exists() else {}
            if value.get("title") is not None and value["title"] == namespace.get(
                "FIGURE_TITLE"
            ):
                nonce = value.get("nonce", "")
                if not re.fullmatch("[0-9a-f]{32}", nonce):
                    raise ValueError("Invalid controlled-check identity")
                (root / f"{nonce}.entered").write_text(
                    json.dumps({"phase": "before_original_check", "pid": os.getpid()})
                )
                deadline = time.monotonic() + 45
                while not (root / f"{nonce}.release").exists():
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            "Controlled original checker was not released"
                        )
                    time.sleep(0.005)
            return original(*positional, **keywords)

        namespace["check"] = check

    token = preview_render.NAMESPACE_OBSERVER.set(observe)
    sys.argv = [sys.argv[0], *rest]
    try:
        preview_render.main()
    finally:
        preview_render.NAMESPACE_OBSERVER.reset(token)


def serve():
    from graphunslopify.preview import PreviewServer
    from graphunslopify.preview_worker import RenderWorker

    parser = argparse.ArgumentParser()
    parser.add_argument("--control-dir", required=True, type=Path)
    args = parser.parse_args()
    root = args.control_dir.resolve()
    root.mkdir(parents=True, exist_ok=False)
    os.environ["GRAPHUNSLOPIFY_STAGE_CHECK_DIR"] = str(root)
    server = PreviewServer(0)
    server.state.worker.close()
    server.state.worker = RenderWorker(
        server.state.root, profile_driver=Path(__file__), cache_statistics=True
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
    print(json.dumps({"url": f"http://127.0.0.1:{server.server_port}/"}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        native = server.state.worker.process.connection
        compiler = server.state.translator.process.connection
        folder = server.state.root
        server.server_close()
        (root / "closed.json").write_text(
            json.dumps(
                {
                    "native_closed": native is None
                    or native.process.poll() is not None,
                    "compiler_closed": compiler is None
                    or compiler.process.poll() is not None,
                    "temporary_root_removed": not folder.exists(),
                }
            )
        )


if __name__ == "__main__":
    if "--profile-script" in sys.argv:
        profile()
    else:
        serve()
