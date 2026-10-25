"""Install a built wheel in a fresh venv and exercise it outside the checkout."""

from __future__ import annotations

import argparse
import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path
from zipfile import ZipFile


def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf8",
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"{command}:\n{completed.stdout}\n{completed.stderr}")
    return completed.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path, nargs="?")
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument(
        "--keep-environment",
        action="store_true",
        help="retain the temporary venv for debugging",
    )
    parser.add_argument(
        "--agent",
        action="store_true",
        help="also install/test the optional stdio agent bridge",
    )
    args = parser.parse_args()
    if args.wheel is None:
        candidates = list(Path("dist").glob("graphunslopify-*-py3-none-any.whl"))
        if len(candidates) != 1:
            parser.error("pass one wheel path, or build exactly one wheel in dist/")
        args.wheel = candidates[0]
    wheel = args.wheel.resolve()
    with ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "graphunslopify/_translator.mjs" in names
        assert "graphunslopify/ZOD-LICENSE.txt" in names
        assert any(name.endswith("/licenses/LICENSE") for name in names)
    where = (args.work_dir or Path(tempfile.mkdtemp(prefix="gu-install-"))).resolve()
    where.mkdir(parents=True, exist_ok=True)
    virtual = where / "fresh environment"
    if virtual.exists():
        parser.error(
            "the test environment already exists; choose a fresh work directory"
        )
    if not args.keep_environment:
        atexit.register(shutil.rmtree, virtual, ignore_errors=True)
    venv.EnvBuilder(with_pip=True).create(virtual)
    python = virtual / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("GRAPHUNSLOPIFY_NODE", None)
    env["GRAPHUNSLOPIFY_API"] = "local"
    env["PYTHONIOENCODING"] = "utf-8"
    run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            str(wheel) + ("[agent]" if args.agent else ""),
        ],
        cwd=where,
        env=env,
    )

    # Block external calls after installation; asyncio may use local socket pairs.
    hooks = where / "offline hooks"
    hooks.mkdir()
    (hooks / "sitecustomize.py").write_text(
        "import socket, ipaddress\n"
        "def denied(*a, **k): raise RuntimeError('network disabled for installation smoke test')\n"
        "def local(host):\n"
        "    if host == 'localhost': return True\n"
        "    try: return ipaddress.ip_address(host).is_loopback\n"
        "    except ValueError: return False\n"
        "original_connect, original_ex = socket.socket.connect, socket.socket.connect_ex\n"
        "original_create = socket.create_connection\n"
        "def allowed(sock, address):\n"
        "    return local(address[0]) if isinstance(address, tuple) else sock.family == getattr(socket, 'AF_UNIX', None)\n"
        "def connect(sock, address):\n"
        "    return original_connect(sock, address) if allowed(sock, address) else denied()\n"
        "def connect_ex(sock, address):\n"
        "    return original_ex(sock, address) if allowed(sock, address) else denied()\n"
        "def create(address, *a, **k):\n"
        "    return original_create(address, *a, **k) if local(address[0]) else denied()\n"
        "socket.socket.connect, socket.socket.connect_ex = connect, connect_ex\n"
        "socket.create_connection = create\n",
        encoding="utf8",
    )
    node_hook = hooks / "offline.cjs"
    node_hook.write_text(
        "const denied = () => { throw new Error('network disabled for installation smoke test'); };\n"
        "require('node:net').Socket.prototype.connect = denied;\n"
        "require('node:http').request = denied; require('node:https').request = denied;\n"
        "require('node:dns').lookup = denied; globalThis.fetch = denied;\n",
        encoding="utf8",
    )
    env["PYTHONPATH"] = str(hooks)
    env["NODE_OPTIONS"] = "--require=" + json.dumps(node_hook.as_posix())
    env["MPLBACKEND"] = "Agg"
    env["MPLCONFIGDIR"] = str(where / "matplotlib")
    cli = [str(python), "-m", "graphunslopify.cli"]
    doctor = json.loads(run([*cli, "doctor"], cwd=where, env=env))
    assert doctor["ok"] and len(doctor["translator"]["kinds"]) == 21
    assert doctor["translator"]["node"].startswith(("v22.", "v24."))
    demo = where / "paper with spaces" / "data"
    report = json.loads(run([*cli, "demo", str(demo), "--json"], cwd=where, env=env))
    assert report["status"] == "passed" and report["policy"]["strict"]
    assert report["data"]["counts"]["read"] == 24
    assert report["data"]["counts"]["sample_sizes"] == [4] * 6
    assert report["claims"][0]["verdict"] == "holds"
    assert "ours is highest at 56.5" in report["alt_text"]
    for suffix in ("png", "svg", "pdf"):
        provenance = json.loads(
            run(
                [*cli, "provenance", str(demo / f"figure.{suffix}")], cwd=where, env=env
            )
        )
        assert provenance["ok"]
        assert (
            provenance["provenance"]["data_sha256_prefix"]
            == report["data"]["sha256_prefix"]
        )
    run([*cli, "audit-init", str(demo)], cwd=where, env=env)
    audited = json.loads(
        run(
            [*cli, "audit", str(demo), "--out-dir", str(where / "audit")],
            cwd=where,
            env=env,
        )
    )
    assert audited["status"] == "passed"
    assert audited["figures"][0]["report"]["claims"][0]["verdict"] == "holds"
    generated_script = (
        where / "audit" / audited["figures"][0]["outputs"][0]["path"]
    ).parent / "figure.py"
    script_manifest = where / "script-manifest.json"
    script_manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "figures": [{"id": "script", "script": str(generated_script)}],
            }
        ),
        encoding="utf8",
    )
    script_audit = json.loads(
        run(
            [
                *cli,
                "audit",
                str(script_manifest),
                "--out-dir",
                str(where / "script audit"),
            ],
            cwd=where,
            env=env,
        )
    )
    assert script_audit["status"] == "passed"
    copied = json.loads(
        run(
            [*cli, "notebook", "--output", str(where / "quickstart.ipynb")],
            cwd=where,
            env=env,
        )
    )
    assert copied["ok"] and not copied["executed"]
    assert len(json.loads((where / "quickstart.ipynb").read_text())["cells"]) == 10
    config = json.loads(run([*cli, "mcp-config"], cwd=where, env=env))
    assert config["mcpServers"]["graphunslopify"]["command"] == str(python)
    if args.agent:
        agent_script = where / "agent-check.py"
        agent_script.write_text(
            "import asyncio, os, sys\nfrom mcp import Client, StdioServerParameters\n"
            "async def main():\n"
            "    params = StdioServerParameters(command=sys.executable, args=['-m','graphunslopify.cli','mcp'], env=dict(os.environ))\n"
            "    async with Client(params) as client:\n"
            "        tools = await client.list_tools()\n"
            "        assert len(tools.tools) == 7\n"
            "        schema = await client.call_tool('get_figure_schema', {})\n"
            "        assert len(schema.structured_content['oneOf']) == 21\n"
            "        bad = await client.call_tool('figure_to_matplotlib', {'spec':{'kind':'unknown'}})\n"
            "        assert bad.is_error and bad.structured_content['status'] == 'invalid_spec'\n"
            "asyncio.run(main())\n",
            encoding="utf8",
        )
        run([str(python), str(agent_script)], cwd=where, env=env)
    # The SDK resolves nested relative input paths and separate output directories.
    sdk = where / "sdk.py"
    sdk.write_text(
        "import json\nfrom pathlib import Path\nimport graphunslopify\n"
        "from graphunslopify import Figure\n"
        "from graphunslopify.transport import local_request\n"
        "assert 'site-packages' in str(Path(graphunslopify.__file__))\n"
        "assert local_request('info')['version'] == graphunslopify.__version__\n"
        "f = Figure.line('paper with spaces/data/results.csv').x('epoch', 'Epoch').y('score', 'Score')\n"
        "f.by('model').average_over('seed').set(legend={'position':'outside_bottom'})\n"
        "before = f.to_dict()\nr = f.render(cwd='separate output', strict=True)\n"
        "assert r['report']['status'] == 'passed'\nassert f.to_dict() == before\n"
        "candidate = Figure.from_profile('paper with spaces/data/results.csv')\n"
        "assert candidate.spec['data']['path'] == 'paper with spaces/data/results.csv'\n"
        "assert candidate.translate()['status'] == 'translated'\n"
        "print(json.dumps({'package':graphunslopify.__file__, 'sdk':'passed'}))\n",
        encoding="utf8",
    )
    run([str(python), str(sdk)], cwd=where, env=env)
    # Ensure the network hooks themselves work, rather than merely claiming offline mode.
    blocked = subprocess.run(
        [
            str(python),
            "-c",
            "import socket; socket.create_connection(('example.com', 443))",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert blocked.returncode and "network disabled" in blocked.stderr
    blocked_node = subprocess.run(
        [
            str(python),
            "-m",
            "nodejs_wheel",
            "-e",
            "require('node:https').get('https://example.com')",
        ],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf8",
        check=False,
    )
    assert blocked_node.returncode and "network disabled" in blocked_node.stderr
    print(
        json.dumps(
            {
                "status": "passed",
                "wheel": wheel.name,
                "python": sys.version.split()[0],
                "translator": doctor["translator"],
                "network": "external connections blocked after install",
                "agent": args.agent,
                "work_dir": str(where),
            }
        )
    )


if __name__ == "__main__":
    main()
