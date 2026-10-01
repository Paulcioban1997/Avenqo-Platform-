from __future__ import annotations

import json
from pathlib import Path
import re

from backend.app.core.locale_catalog import LOCALES, locale_info, resolve_locale

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
