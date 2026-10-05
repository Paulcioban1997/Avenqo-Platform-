from backend.app.core.locale_catalog import BY_LOCALE


def voice_language_matrix() -> list[dict[str, object]]:
    return [{
        "locale": locale,
        "UI_TRANSLATION_SUPPORTED": True,
        "STT_SUPPORTED": None,
        "LLM_LANGUAGE_SUPPORTED": None,
        "TTS_SUPPORTED": None,
        "LIVE_AUDIO_VALIDATED": False,
        "FULLY_SUPPORTED": False,
        "fallback": "text",
    } for locale in BY_LOCALE]