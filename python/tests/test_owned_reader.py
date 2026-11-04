"""Actual worker processes prove bounded readers retire on timeout/RSS and reject bad output."""

import json
import sys

import psutil
import pytest

from graphunslopify.owned_reader import ReaderError, run_reader
from graphunslopify.worker_process import PROTOCOL, JsonWorker


@pytest.mark.parametrize("mode", ["deadline", "memory", "descriptor"])
def test_real_reader_resource_and_output_fences(tmp_path, mode):
    program = f"""import json,os,sys,time
from pathlib import Path
Path('owned.pid').write_text(str(os.getpid()))
print(json.dumps({{'protocol':{PROTOCOL!r},'kind':'test-reader','pid':os.getpid(),'ready':True,'adapter_version':1}}),flush=True)
request=json.loads(sys.stdin.readline())
if {mode!r} == 'descriptor':
 print(json.dumps({{'protocol':{PROTOCOL!r},'id':request['id'],'ok':True,'result':{{'file':'../outside','bytes':0,'sha256':'bad'}}}}),flush=True)
else:
 time.sleep(30)
"""

    def factory(_args, root, **kwargs):
        return JsonWorker([sys.executable, "-c", program], root, **kwargs)

    with pytest.raises(
        ReaderError,
        match={"deadline": "deadline", "memory": "memory", "descriptor": "descriptor"}[mode],
    ):
        run_reader(
            tmp_path,
            module="unused.trusted.module",
            kind="test-reader",
            payload={},
            filename="result.json",
            max_output=1024,
            max_rss=1 if mode == "memory" else 512 * 1024 * 1024,
            timeout=0.5 if mode == "deadline" else 10,
            worker_factory=factory,
        )
    assert not psutil.pid_exists(int((tmp_path / "owned.pid").read_text()))
    assert not (tmp_path / "result.json").exists()


def test_source_ast_limit_is_a_saved_refusal(tmp_path):
    from graphunslopify.source_imports import import_source, save_source_import

    source = ("x=[" + "0," * 51000 + "]\n").encode()
    proposal = import_source(source)
    assert not proposal.report["convertible"]
    assert proposal.report["unsupported"][0]["category"] == "resource"
    result = save_source_import(proposal, tmp_path / "refused")
    assert result["exit_code"] == 1
    assert (tmp_path / "refused/original-source.py").read_bytes() == source
    assert json.loads((tmp_path / "refused/source-import.json").read_text())["import"][
        "original_bytes"
    ] == len(source)
