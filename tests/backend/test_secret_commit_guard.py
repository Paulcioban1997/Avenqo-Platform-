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
