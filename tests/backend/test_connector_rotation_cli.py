import secrets


def test_configuration_failure_never_echoes_sensitive_exception(monkeypatch, capsys):
    from backend.app.config import settings
    from scripts.rotate_connector_secrets import main

    private_value = secrets.token_urlsafe(32)

    def invalid_configuration():
        raise ValueError(private_value)

    monkeypatch.setattr(settings, "get_settings", invalid_configuration)
    monkeypatch.setattr("sys.argv", ["rotate_connector_secrets.py"])
    assert main() == 1
    captured = capsys.readouterr()
    assert private_value not in captured.out + captured.err
    assert "Secret details withheld" in captured.err


def test_apply_requires_matching_environment_before_rotation(monkeypatch, capsys):
    from scripts.rotate_connector_secrets import main

    monkeypatch.setattr("sys.argv", ["rotate_connector_secrets.py", "--apply",
                                    "--confirm-environment", "wrong-environment"])
    assert main() == 2
    assert "no changes applied" in capsys.readouterr().err
