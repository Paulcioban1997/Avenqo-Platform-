from types import SimpleNamespace
import secrets

from scripts import provider_readiness_probe


def test_read_only_probe_blocks_wrong_environment_and_live_stripe_key(monkeypatch, capsys):
    key = "sk_live_" + secrets.token_urlsafe(40)
    settings = SimpleNamespace(environment="sandbox", stripe_secret_key=key, telnyx_api_key=None)
    monkeypatch.setattr("backend.app.config.settings.get_settings", lambda: settings)
    def forbidden(*args, **kwargs):
        raise AssertionError("No external request expected")
    monkeypatch.setattr("requests.get", forbidden)
    assert provider_readiness_probe.main(["--confirm-environment","production"]) == 2
    assert provider_readiness_probe.main(["--confirm-environment","sandbox"]) == 1
    captured = capsys.readouterr()
    assert key not in captured.out + captured.err
    assert "blocked_live_key_in_test_environment" in captured.out


def test_probe_only_reads_and_never_prints_provider_payload(monkeypatch, capsys):
    key = "sk_test_" + secrets.token_urlsafe(40)
    private_payload = secrets.token_urlsafe(40)
    settings = SimpleNamespace(environment="sandbox", stripe_secret_key=key, telnyx_api_key=key)
    monkeypatch.setattr("backend.app.config.settings.get_settings", lambda: settings)
    calls = []
    def get(url, **kwargs):
        calls.append((url,kwargs))
        return SimpleNamespace(status_code=200, text=private_payload)
    monkeypatch.setattr("requests.get", get)
    assert provider_readiness_probe.main(["--confirm-environment","sandbox"]) == 0
    assert len(calls)==2 and all(call[1]["allow_redirects"] is False for call in calls)
    output=capsys.readouterr().out
    assert key not in output and private_payload not in output
