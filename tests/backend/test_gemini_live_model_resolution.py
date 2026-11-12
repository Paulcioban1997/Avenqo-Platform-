"""Contracts for Gemini Live model resolution — no silent remapping of retired IDs."""

from __future__ import annotations

import pytest

from backend.app.voice.realtime_provider import (
    DEFAULT_GEMINI_LIVE_MODEL,
    SUPPORTED_GEMINI_LIVE_MODELS,
    UnsupportedGeminiLiveModelError,
    resolve_gemini_live_model,
)


def test_default_gemini_live_model_is_3_8() -> None:
    assert DEFAULT_GEMINI_LIVE_MODEL == "gemini-3.8-live"
    assert resolve_gemini_live_model(None) == "gemini-3.8-live"
    assert resolve_gemini_live_model("") == "gemini-3.8-live"
    assert "gemini-3.8-live-extended-thinking" in SUPPORTED_GEMINI_LIVE_MODELS


def test_supported_gemini_live_models_accepted() -> None:
    assert resolve_gemini_live_model("gemini-3.8-live") == "gemini-3.8-live"
    assert (
        resolve_gemini_live_model("gemini-3.8-live-extended-thinking")
        == "gemini-3.8-live-extended-thinking"
    )


@pytest.mark.parametrize(
    "retired",
    [
        "gemini-2.0-flash-live-001",
        "gemini-2.5-flash-native-audio-preview-12-2025",
        "gemini-2.0-flash-exp",
    ],
)
def test_retired_gemini_live_models_raise(retired: str) -> None:
    with pytest.raises(UnsupportedGeminiLiveModelError, match="retired"):
        resolve_gemini_live_model(retired)


def test_unknown_gemini_live_model_raises() -> None:
    with pytest.raises(UnsupportedGeminiLiveModelError, match="not supported"):
        resolve_gemini_live_model("gemini-1.5-flash-bogus")
