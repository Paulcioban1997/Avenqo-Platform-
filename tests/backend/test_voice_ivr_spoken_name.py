"""IVR company pronunciation is driven by individual tenant configuration."""
from types import SimpleNamespace

from backend.app.voice.messages import voice_ivr_spoken_name


def test_ivr_preserves_exact_display_name():
    cfg = SimpleNamespace(effective_voice_name="Produits Ero", custom_pronunciation=None)
    assert voice_ivr_spoken_name(cfg) == "Produits Ero"


def test_ivr_respects_explicit_phonetic_alias_without_changing_brand():
    cfg = SimpleNamespace(effective_voice_name="Produits Ero", custom_pronunciation="Produits, Ero")
    assert voice_ivr_spoken_name(cfg) == "Produits, Ero"


def test_ivr_json_pronunciation_is_scoped_per_tenant():
    a = SimpleNamespace(effective_voice_name="Produits Ero", custom_pronunciation='{"company": "Produits, Ero"}')
    b = SimpleNamespace(effective_voice_name="Garage Nord", custom_pronunciation=None)
    assert voice_ivr_spoken_name(a) == "Produits, Ero"
    assert voice_ivr_spoken_name(b) == "Garage Nord"


def test_empty_pronunciation_object_reaches_telnyx_with_a_pause():
    from backend.app.voice.messages import voice_ivr_greeting, voice_speech_name

    cfg = SimpleNamespace(
        business_name="Produits Ero",
        voice_display_name="Produits Ero",
        effective_voice_name="Produits Ero",
        custom_pronunciation="{}",
        preferred_language="fr",
        call_policy={},
    )
    assert voice_speech_name(cfg) == "Produits, Ero"
    greeting = voice_ivr_greeting(cfg)
    assert "Bienvenue chez Produits, Ero." in greeting
    assert "Produits Ero" not in greeting


def test_ivr_invalid_pronunciation_falls_back_to_display_name():
    cfg = SimpleNamespace(effective_voice_name="Cabinet Exemple", custom_pronunciation="{invalid")
    assert voice_ivr_spoken_name(cfg) == "Cabinet Exemple"


def test_ivr_professional_template_injects_tenant_voice_alias():
    from backend.app.voice.messages import voice_ivr_greeting
    cfg = SimpleNamespace(
        business_name="Produits Ero", voice_display_name="Produits Ero",
        effective_voice_name="Produits, Éro",
        custom_pronunciation='{"company":"Produits, Éro"}',
        preferred_language="fr",
        call_policy={"ivr_greeting": (
            "Bonjour et bienvenue chez {company}. Cet appel est pris en charge "
            "par un assistant vocal automatisé. Pour les employés, composez le 1. "
            "Pour le service clientèle, composez le 2."
        )},
    )
    greeting = voice_ivr_greeting(cfg)
    assert "Produits, Éro" in greeting
    assert "assistant vocal automatisé" in greeting
    assert "composez le 1" in greeting and "composez le 2" in greeting
    assert "Zéro" not in greeting


def test_ivr_custom_name_without_hardcoded_business_special_case():
    from backend.app.voice.messages import voice_ivr_greeting
    cfg = SimpleNamespace(
        business_name="Garage Nord", voice_display_name="Garage Nord",
        effective_voice_name="Garage Nord", custom_pronunciation=None,
        preferred_language="fr", call_policy={
            "ivr_greeting": "Bonjour chez {entreprise}. Heures : lundi à vendredi."
        },
    )
    assert voice_ivr_greeting(cfg) == "Bonjour chez Garage Nord. Heures : lundi à vendredi."


def test_ivr_legacy_default_still_routes_staff_and_public():
    from backend.app.voice.messages import voice_ivr_greeting
    cfg = SimpleNamespace(
        business_name="Autre compagnie", effective_voice_name="Autre compagnie",
        custom_pronunciation=None, preferred_language="fr", call_policy={},
    )
    greeting = voice_ivr_greeting(cfg)
    assert "Autre compagnie" in greeting
    assert "composez le 1" in greeting and "composez le 2" in greeting
