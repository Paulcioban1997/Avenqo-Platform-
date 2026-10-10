from scripts.check_secrets import violations


def test_guard_blocks_literal_database_credentials_without_echoing_them():
    import secrets
    from sqlalchemy.engine import URL
    value = URL.create("postgresql", username="test_user", password=secrets.token_urlsafe(40), host="db.test.invalid").render_as_string(hide_password=False)
    assert violations("header\n" + value) == [2]


def test_guard_accepts_only_explicit_fictional_fixture():
    from sqlalchemy.engine import URL
    fixture = URL.create("postgresql", username="test_user", password="test-only-password", host="db.test.invalid").render_as_string(hide_password=False)
    assert violations(fixture) == []


def test_guard_blocks_historical_connector_key_patterns_without_echoing_values():
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    for source in (
        'ConnectorSecretCipher(["' + key + '"])',
        'CONNECTOR_ENCRYPTION_KEYS=' + key,
        'CONNECTOR_ENCRYPTION_KEYS = ["' + key + '"]',
        "CONNECTOR_ENCRYPTION_KEYS='[\"" + key + "\"]'",
    ):
        assert violations("header\n" + source) == [2]


def test_guard_allows_environment_configuration_and_generated_test_keys():
    assert violations('CONNECTOR_ENCRYPTION_KEYS=${CONNECTOR_ENCRYPTION_KEYS}') == []
    assert violations('ConnectorSecretCipher([Fernet.generate_key().decode()])') == []


def test_guard_blocks_literal_woocommerce_signing_secret_fallbacks():
    import secrets

    value = secrets.token_urlsafe(48)
    assert violations('header\nwoo_creds.get("webhook_secret", "' + value + '")') == [2]
    assert violations('wh_secret = "' + value + '"') == [1]
    assert violations('{"webhook_secret": "' + value + '"}') == [1]
    assert violations('woo_creds.get("webhook_secret", "test-only-fictional-value")') == []
