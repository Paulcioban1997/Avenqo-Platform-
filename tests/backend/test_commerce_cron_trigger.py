"""No provider calls, database or scheduler credentials used by these tests."""
import json
import secrets
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

from backend.app.services import commerce_reconciliation_cron_trigger as trigger
from backend.app.services import scheduler_http as http


class Response:
    def read(self, limit=None): return b'{"claimed": 0}'
    def __enter__(self): return self
    def __exit__(self, *args): pass


@pytest.mark.parametrize("error", [TimeoutError("private failure"), URLError(ConnectionResetError("private failure")), HTTPError("https://private.invalid",502,"private failure",None,None), HTTPError("https://private.invalid",401,"private failure",None,None)])
def test_ambiguous_post_or_auth_is_never_retried_and_logs_are_safe(monkeypatch,capsys,error):
    token=secrets.token_urlsafe(32);seen=[]
    def fail(request,timeout): seen.append(request);raise error
    monkeypatch.setattr(http,"urlopen",fail)
    with pytest.raises((TimeoutError,URLError)):
        http.post_scheduler_json("https://private.invalid/internal/commerce/reconcile",token,timeout=600,attempts=3,
            preconnect_retries_only=True,diagnostics=True)
    assert len(seen)==1
    output=capsys.readouterr().out
    assert token not in output and "private.invalid" not in output and "private failure" not in output
    assert "scheduler_failed" in output


def test_only_dns_and_refused_connections_retry_with_same_correlation(monkeypatch,capsys):
    seen=[];slept=[]
    def open_request(request,timeout):
        seen.append(request)
        if len(seen)==1: raise URLError(socket.gaierror("fixture"))
        if len(seen)==2: raise URLError(ConnectionRefusedError("fixture"))
        return Response()
    monkeypatch.setattr(http,"urlopen",open_request)
    monkeypatch.setattr(http.time,"sleep",slept.append)
    assert http.post_scheduler_json("https://example.invalid/internal/commerce/reconcile",secrets.token_urlsafe(32),timeout=600,
        attempts=3,preconnect_retries_only=True,diagnostics=True,retry_window_seconds=660)=={"claimed":0}
    assert len(seen)==3 and slept==[1,2]
    assert len({r.get_header("X-request-id") for r in seen})==1
    assert all(r.method=="POST" for r in seen)


def test_retry_window_blocks_another_request(monkeypatch):
    now=[0];seen=[]
    monkeypatch.setattr(http.time,"monotonic",lambda:now[0])
    monkeypatch.setattr(http.time,"sleep",lambda seconds:now.__setitem__(0,10))
    def refused(*args,**kwargs): seen.append(1);raise URLError(ConnectionRefusedError())
    monkeypatch.setattr(http,"urlopen",refused)
    with pytest.raises(TimeoutError):
        http.post_scheduler_json("https://example.invalid","fixture",timeout=5,attempts=3,preconnect_retries_only=True,retry_window_seconds=8)
    assert len(seen)==1


@pytest.mark.parametrize("claimed,expected",[(0,0),(2,0),(-1,1),(True,1),("0",1),(None,1)])
def test_process_exit_and_structured_diagnostics(monkeypatch,capsys,claimed,expected):
    token=secrets.token_urlsafe(32)
    monkeypatch.setenv("COMMERCE_RECONCILIATION_SCHEDULER_URL","https://example.invalid/internal/commerce/reconcile")
    monkeypatch.setenv("CONNECTOR_AI_SCHEDULER_TOKEN",token)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_ID",raising=False)
    def post(url,secret,**kwargs):
        assert secret==token and kwargs["preconnect_retries_only"] and kwargs["timeout"]==600
        return {"claimed":claimed}
    monkeypatch.setattr(trigger,"post_scheduler_json",post)
    assert trigger.main()==expected
    output=capsys.readouterr().out
    events=[json.loads(x) for x in output.splitlines() if x.startswith("{")]
    assert events[0]["event"]=="commerce_cron_started"
    assert events[-1]["exit_status"]==expected and "elapsed_seconds" in events[-1]
    assert token not in output and "example.invalid" not in output


def test_sandbox_cannot_target_production(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID","e5adc24d-23b9-4275-84de-91a7801649b8")
    monkeypatch.setenv("COMMERCE_RECONCILIATION_SCHEDULER_URL","https://api.avenqo.ca/internal/commerce/reconcile")
    monkeypatch.setenv("CONNECTOR_AI_SCHEDULER_TOKEN",secrets.token_urlsafe(32))
    monkeypatch.setattr(trigger,"post_scheduler_json",lambda *a,**k:pytest.fail("Must not send request"))
    assert trigger.main()==1


def test_worker_starts_without_site_packages_or_api_image(tmp_path,monkeypatch):
    import os
    root=Path(__file__).resolve().parents[2]/"backend/app/services"
    target=tmp_path/"backend/app/services";target.mkdir(parents=True)
    for name in ["commerce_reconciliation_cron_trigger.py","scheduler_http.py"]:
        shutil.copy(root/name,target/name)
    env={k:v for k,v in os.environ.items() if k not in {"CONNECTOR_AI_SCHEDULER_TOKEN","COMMERCE_RECONCILIATION_SCHEDULER_URL","PYTHONPATH"}}
    result=subprocess.run([sys.executable,"-S","-m","backend.app.services.commerce_reconciliation_cron_trigger"],cwd=tmp_path,env=env,capture_output=True,text=True,timeout=10)
    assert result.returncode==1 and not result.stderr
    assert json.loads(result.stdout.splitlines()[0])["event"]=="commerce_cron_started"
    assert json.loads(result.stdout.splitlines()[-1])["category"]=="configuration"
