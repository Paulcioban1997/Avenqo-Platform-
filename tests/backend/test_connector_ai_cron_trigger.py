import io
import json
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

from backend.app.services import connector_ai_cron_trigger as cron


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", cron.SANDBOX_ID)
    return SimpleNamespace(connector_ai_scheduler_url="https://avenqo-platform-sandbox.up.railway.app/internal/connector-ai/evaluate",
        connector_ai_scheduler_token="synthetic-not-a-credential")


@pytest.mark.parametrize("status", [502, 503, 504])
def test_gateway_retry_succeeds_with_bounded_backoff(settings, status, capsys):
    calls, delays = [], []
    def opener(request, timeout):
        calls.append(timeout)
        if len(calls) < 3:
            raise HTTPError(request.full_url, status, "synthetic", {}, io.BytesIO())
        return io.BytesIO(b'{"claimed":2}')
    assert cron.run_trigger(settings, opener=opener, sleep=delays.append, clock=lambda: 0) == 0
    assert len(calls) == 3 and delays == [1, 2]
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert lines[-1]["claimed"] == 2
    assert settings.connector_ai_scheduler_token not in str(lines)
    assert settings.connector_ai_scheduler_url not in str(lines)


@pytest.mark.parametrize("error", [401, 403, 422, 500, URLError("synthetic"), TimeoutError(), ValueError()])
def test_other_errors_never_retry(settings, error):
    calls = []
    def opener(request, timeout):
        calls.append(1)
        if isinstance(error, int):
            raise HTTPError(request.full_url, error, "synthetic", {}, io.BytesIO())
        raise error
    assert cron.run_trigger(settings, opener=opener, sleep=lambda _: pytest.fail("Unsafe retry")) == 1
    assert calls == [1]


def test_exhaustion_is_failure_and_logs_no_error_content(settings, capsys):
    def opener(request, timeout):
        raise HTTPError(request.full_url, 502, "private-data", {"secret":"private-data"}, io.BytesIO(b'private-data'))
    delays=[]
    assert cron.run_trigger(settings, opener=opener, sleep=delays.append, clock=lambda: 0) == 1
    assert delays == [1,2]
    assert "private-data" not in capsys.readouterr().out


def test_retry_window_cannot_outlive_minimum_evaluation_lease(settings):
    now=[0];calls=[]
    def opener(request, timeout):
        calls.append(timeout); now[0]=20
        raise HTTPError(request.full_url,502,"synthetic",{},io.BytesIO())
    assert cron.run_trigger(settings,opener=opener,clock=lambda:now[0],sleep=lambda _:pytest.fail("Window expired"))==1
    assert calls==[60]
    assert cron.RETRY_WINDOW_SECONDS < 30  # API validates minimum lease=30s.


@pytest.mark.parametrize("change", ["environment", "url"])
def test_non_sandbox_or_unrelated_post_never_retries(settings,monkeypatch,change):
    if change=="environment":monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID","production-test-placeholder")
    else:settings.connector_ai_scheduler_url="https://example.com/non-idempotent-operation"
    calls=[]
    def opener(request,timeout):
        calls.append(timeout);raise HTTPError(request.full_url,502,"synthetic",{},io.BytesIO())
    assert cron.run_trigger(settings,opener=opener,sleep=lambda _:pytest.fail("Unsafe retry"))==1
    assert calls==[60]


@pytest.mark.parametrize("payload", [b'not-json',b'{"claimed":-1}',b'{"claimed":true}',b'{}',b'[]'])
def test_invalid_success_response_is_not_replayed(settings,payload):
    assert cron.run_trigger(settings,opener=lambda *a,**kw:io.BytesIO(payload),sleep=lambda _:pytest.fail("Ambiguous replay"))==1


def test_delayed_backoff_never_sends_request_after_retry_deadline(settings):
    now=[0];calls=[]
    def opener(request,timeout):
        calls.append(1);raise HTTPError(request.full_url,502,"synthetic",{},io.BytesIO())
    def sleep(delay):now[0]=21
    assert cron.run_trigger(settings,opener=opener,sleep=sleep,clock=lambda:now[0])==1
    assert calls==[1]
