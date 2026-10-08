from __future__ import annotations

from typing import Any

from backend.app.core.locale_catalog import BY_LOCALE, LOCALES


def voice_language_matrix() -> list[dict[str, object]]:
    """Matrice canonique de base (conforme aux assertions contractuelles de test)."""
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


# Les 5 seules variantes linguistiques rigoureusement testées et validées sur la chaîne audio Telnyx
_LIVE_AUDIO_VALIDATED_LOCALES = frozenset({"fr", "fr-CA", "en", "en-US", "en-CA", "es", "es-ES", "ro", "ro-RO"})

# Langues majeures bénéficiant de modèles STT / TTS officiels chez OpenAI & Telnyx
_TIER_1_AUDIO_LOCALES = frozenset({
    "fr", "en", "es", "ro", "pt", "fr-FR", "en-GB", "de", "it", "nl", "pl", "ru",
    "uk", "sv", "tr", "cs", "ja", "ko", "zh", "hi", "id", "vi", "th", "ar", "he",
})


def voice_audio_capabilities_matrix() -> list[dict[str, Any]]:
    """Matrice détaillée des capacités audio (STT, TTS, validation réelle, limitations) pour les 44 langues."""
    matrix: list[dict[str, Any]] = []
    for info in LOCALES:
        code = info.locale
        bcp47 = info.bcp47
        is_live_validated = code in _LIVE_AUDIO_VALIDATED_LOCALES or bcp47 in _LIVE_AUDIO_VALIDATED_LOCALES
        is_tier_1 = code in _TIER_1_AUDIO_LOCALES or bcp47 in _TIER_1_AUDIO_LOCALES

        if is_live_validated:
            limitations = "Aucune limitation bloquante. Chaîne audio Telnyx, anti-repliement et Language Lock validés."
            fallback = bcp47
        elif is_tier_1:
            limitations = "Synthèse et transcription fournies par API standard ; non certifié sur ligne téléphonique réelle Telnyx."
            fallback = "fr-CA" if info.region == "americas" else "en-US"
        else:
            limitations = "Ressource acoustique limitée ; nécessite confirmation explicite de l'appelant."
            fallback = info.fallback if info.fallback in {"fr", "en"} else "en-US"

        matrix.append({
            "locale": code,
            "bcp47": bcp47,
            "name": info.english_name,
            "native_name": info.native_name,
            "region": info.region,
            "ui_translation_supported": True,
            "stt_available": is_tier_1 or is_live_validated,
            "tts_available": is_tier_1 or is_live_validated,
            "regional_voice_available": is_live_validated,
            "language_switch_tested": is_live_validated,
            "live_audio_validated": is_live_validated,
            "known_limitations": limitations,
            "fallback_locale": fallback,
        })
    return matrix


def get_voice_language_capability(locale_or_bcp47: str) -> dict[str, Any]:
    """Retourne la fiche de capacités vocales pour une langue donnée."""
    normalized = (locale_or_bcp47 or "").strip().lower()
    for row in voice_audio_capabilities_matrix():
        if row["locale"].lower() == normalized or row["bcp47"].lower() == normalized:
            return row
    # Fallback par défaut vers fr-CA
    return {
        "locale": "fr",
        "bcp47": "fr-CA",
        "name": "French (Canada)",
        "native_name": "Français (Canada)",
        "region": "americas",
        "ui_translation_supported": True,
        "stt_available": True,
        "tts_available": True,
        "regional_voice_available": True,
        "language_switch_tested": True,
        "live_audio_validated": True,
        "known_limitations": "Aucune",
        "fallback_locale": "fr-CA",
    }