from __future__ import annotations

import json
from pathlib import Path
import re

from backend.app.core.locale_catalog import (
    LOCALES,
    detect_locale_from_text,
    detect_spoken_language,
    locale_info,
    resolve_locale,
    voice_language_detection_support,
)
from backend.app.ai.tools.natural_confirmation import (
    SUPPORTED_CONFIRMATION_LOCALES,
    is_natural_confirmation,
)

ROOT = Path(__file__).resolve().parents[2]
CANONICAL = json.loads((ROOT / "shared/locales/canonical_locales.json").read_text(encoding="utf-8"))


def test_canonical_locale_contract_is_exactly_44_and_all_representations_match() -> None:
    codes = [item["code"] for item in CANONICAL]
    assert len(codes) == 44
    assert len(set(codes)) == 44
    assert [item.locale for item in LOCALES] == codes

    flutter_codes = [
        item["code"]
        for item in json.loads((ROOT / "frontend/assets/i18n/_locales.json").read_text(encoding="utf-8"))
    ]
    assert flutter_codes == codes

    web_source = (ROOT / "web/src/lib/i18n/canonical-locales.generated.ts").read_text(encoding="utf-8")
    assert re.findall(r'"code": "([^"]+)"', web_source) == codes
    for code in codes:
        assert (ROOT / "frontend/assets/i18n" / f"{code}.json").exists()


def test_locale_aliases_normalize_without_creating_new_locales() -> None:
    assert resolve_locale("fr_FR") == "fr-FR"
    assert resolve_locale("fr-CA") == "fr"
    assert resolve_locale("en_US") == "en"
    assert resolve_locale("es-LatAm") == "es"
    assert resolve_locale("pt-BR") == "pt"
    assert resolve_locale("unsupported-XX") == "fr"
    assert locale_info("ar-EG").direction == "rtl"
    assert locale_info("ur").direction == "rtl"


def test_canonical_fallbacks_and_metadata_are_valid() -> None:
    by_code = {item["code"]: item for item in CANONICAL}
    assert all(item["fallback"] in by_code for item in CANONICAL)
    assert {item["direction"] for item in CANONICAL} == {"ltr", "rtl"}
    assert {item["code"] for item in CANONICAL if item["direction"] == "rtl"} == {
        "ar", "ar-EG", "he", "fa", "ur",
    }


def test_natural_confirmation_catalog_covers_all_44_locales_exactly() -> None:
    codes = {item["code"] for item in CANONICAL}
    assert SUPPORTED_CONFIRMATION_LOCALES == codes
    for locale in codes:
        assert is_natural_confirmation(locale, "") is False


def test_natural_confirmation_is_exact_and_does_not_accept_ambiguous_text() -> None:
    assert is_natural_confirmation("fr", "Oui, confirme.") is True
    assert is_natural_confirmation("en", "Yes, confirm it.") is True
    assert is_natural_confirmation("fr", "oui") is False
    assert is_natural_confirmation("en", "yesterday confirm it") is False
    assert is_natural_confirmation("es", "No, cancela") is False
    assert is_natural_confirmation("fr", "123") is False


def test_free_text_detection_is_conservative_and_canonical() -> None:
    assert detect_locale_from_text("Ahora respóndeme en español") == "es"
    assert detect_locale_from_text("Please answer in English") == "en"
    assert detect_locale_from_text("これは日本語の質問です") == "ja"
    assert detect_locale_from_text("OK") is None
    assert detect_locale_from_text("123") is None


def test_spoken_language_detection_is_per_utterance_and_ignores_ui_locale() -> None:
    utterances = (
        ("fr", "Combien de commandes avons-nous ?"),
        ("en", "How many orders do we have?"),
        ("ro", "Câte comenzi avem?"),
        ("es", "¿Cuántos pedidos tenemos?"),
    )
    previous = "fr"
    for expected, transcript in utterances:
        detection = detect_spoken_language(transcript, preferred_locale=previous)
        assert detection.locale == expected
        assert detection.language_code == expected
        assert detection.confidence is not None and detection.confidence >= 0.80
        previous = detection.locale

    ui_french_spoken_english = detect_spoken_language(
        "How many orders do we have?", preferred_locale="fr"
    )
    ui_english_spoken_french = detect_spoken_language(
        "Combien de commandes avons-nous ?", preferred_locale="en"
    )
    assert ui_french_spoken_english.locale == "en"
    assert ui_english_spoken_french.locale == "fr"

    same_session = [
        detect_spoken_language(text, preferred_locale=previous).locale
        for previous, text in zip(
            ("fr", "fr", "en", "ro"),
            (
                "Combien de commandes avons-nous ?",
                "Now answer me in English.",
                "Acum răspunde-mi în română.",
                "Ahora respóndeme en español.",
            ),
        )
    ]
    assert same_session == ["fr", "en", "ro", "es"]


def test_explicit_language_override_beats_detected_utterance_language() -> None:
    detection = detect_spoken_language(
        "Please answer me in Romanian.", preferred_locale="en"
    )

    assert detection.locale == "ro"
    assert detection.source == "explicit_request"


def test_spoken_language_audit_covers_canonical_locales_without_faking_detector_support() -> None:
    support = voice_language_detection_support()

    assert set(support) == {item.locale for item in LOCALES}
    assert len(support) == 44
    assert support["my"] == "script"
    assert support["ha"] == "lexical"

    hausa = detect_spoken_language(
        "Yaya kake? Ina son taimako da bayanin odar.", preferred_locale="fr"
    )
    assert hausa.locale == "ha"
    assert hausa.source == "lexical"

    unsupported = detect_spoken_language(
        "qzx vvv jjj", preferred_locale="fr"
    )
    assert unsupported.locale is None
    assert unsupported.source == "undetermined"
