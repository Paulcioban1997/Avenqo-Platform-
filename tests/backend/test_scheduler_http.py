from urllib.error import HTTPError
from io import BytesIO

from backend.app.services.scheduler_http import post_scheduler_json


class _Response:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None


def test_scheduler_post_retries_502_then_succeeds(monkeypatch) -> None:
    attempts = {"n": 0}

    def fake_urlopen(request, timeout=0):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise HTTPError(request.full_url, 502, "Bad Gateway", hdrs=None, fp=BytesIO())
        return _Response(b'{"claimed": 2}')

    monkeypatch.setattr("backend.app.services.scheduler_http.urlopen", fake_urlopen)
    monkeypatch.setattr("backend.app.services.scheduler_http.time.sleep", lambda _seconds: None)
    payload = post_scheduler_json("https://sandbox.example/internal", "token", timeout=5)
    assert payload == {"claimed": 2}
    assert attempts["n"] == 3


def test_scheduler_post_does_not_retry_unauthorized(monkeypatch) -> None:
    def fake_urlopen(request, timeout=0):
        raise HTTPError(request.full_url, 401, "Unauthorized", hdrs=None, fp=BytesIO())

    monkeypatch.setattr("backend.app.services.scheduler_http.urlopen", fake_urlopen)
    try:
        post_scheduler_json("https://sandbox.example/internal", "token", timeout=5, attempts=4)
    except HTTPError as exc:
        assert exc.code == 401
    else:
        raise AssertionError("401 must fail closed")
