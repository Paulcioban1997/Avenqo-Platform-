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


def test_ivr_invalid_pronunciation_falls_back_to_display_name():
    cfg = SimpleNamespace(effective_voice_name="Cabinet Exemple", custom_pronunciation="{invalid")
    assert voice_ivr_spoken_name(cfg) == "Cabinet Exemple"
