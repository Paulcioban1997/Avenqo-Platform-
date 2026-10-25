from backend.app.config.settings import Settings
from backend.app.services.account_notifications import AccountNotificationService


class _CaptureTransport:
    def __init__(self) -> None:
        self.body = ""

    def send(self, recipient, subject, text_body, html_body) -> None:
        self.body = text_body


def test_sandbox_reset_link_keeps_frontend_host_and_marks_sandbox_env(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "sandbox")
    frontend = "https://web-git-promotion-sandbox.example.vercel.app"
    settings = Settings(
        AUTH_JWT_SECRET="e" * 32,
        ENVIRONMENT="sandbox",
        FRONTEND_URL=frontend,
    )
    transport = _CaptureTransport()
    AccountNotificationService(settings, transport).send_password_reset(
        "probe@example.test",
        "reset-token-value",
    )
    assert frontend in transport.body
    assert "/reset-password?" in transport.body
    assert "token=reset-token-value" in transport.body
    assert "env=sandbox" in transport.body
    assert settings.public_api_origin() == "https://avenqo-platform-sandbox.up.railway.app"


def test_production_reset_link_does_not_add_sandbox_env(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    settings = Settings(
        AUTH_JWT_SECRET="e" * 32,
        ENVIRONMENT="development",
        FRONTEND_URL="http://localhost:3000",
    )
    transport = _CaptureTransport()
    AccountNotificationService(settings, transport).send_password_reset(
        "probe@example.test",
        "reset-token-value",
    )
    assert "http://localhost:3000/reset-password?" in transport.body
    assert "env=sandbox" not in transport.body
