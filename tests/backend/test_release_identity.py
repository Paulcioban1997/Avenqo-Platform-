from backend.app.routers import health


def test_embedded_source_identity_overrides_stale_environment(tmp_path, monkeypatch):
    source = tmp_path / "build-info.json"
    monkeypatch.setattr(health, "BUILD_INFO_PATH", source)
    monkeypatch.setenv("GIT_SHA", "old-image")
    assert health._git_sha() == "old-image"
    source.write_text('{"git_sha":"' + "a" * 40 + '"}', encoding="utf-8")
    assert health._git_sha() == "a" * 40
    source.write_text('{"git_sha":"invalid"}', encoding="utf-8")
    assert health._git_sha() == "old-image"
