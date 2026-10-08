"""Region-aware language resolution and per-call Language Lock for Avenqo Voice.

Assure la détermination déterministe des langues régionales selon la subdivision
géographique et protège chaque appel contre les bascules intempestives via un
verrou linguistique robuste (Language Lock).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from backend.app.core.locale_catalog import LOCALES, detect_spoken_language, resolve_locale

# Données géographiques et linguistiques régionales vérifiables (BCP-47)
# Ne suppose JAMAIS qu'un pays ou une région n'a qu'une seule langue.
REGION_LANGUAGE_DATA: dict[str, dict[str, Any]] = {
    "CA": {
        "name": "Canada",
        "default_primary": "en-CA",
        "default_secondary": ["fr-CA"],
        "subdivisions": {
            "QC": {
                "name": "Québec",
                "primary": "fr-CA",
                "secondary": ["en-CA"],
                "localities": {
                    "montreal": {"primary": "fr-CA", "secondary": ["en-CA"]},
                    "quebec": {"primary": "fr-CA", "secondary": ["en-CA"]},
                    "gatineau": {"primary": "fr-CA", "secondary": ["en-CA"]},
                },
            },
            "NB": {
                "name": "Nouveau-Brunswick / New Brunswick",
                "primary": "fr-CA",
                "secondary": ["en-CA"],
            },
            "ON": {
                "name": "Ontario",
                "primary": "en-CA",
                "secondary": ["fr-CA"],
                "localities": {
                    "ottawa": {"primary": "en-CA", "secondary": ["fr-CA"]},
                    "toronto": {"primary": "en-CA", "secondary": ["fr-CA"]},
                },
            },
            "BC": {
                "name": "British Columbia",
                "primary": "en-CA",
                "secondary": ["fr-CA", "zh-CN", "pa-IN"],
                "localities": {
                    "vancouver": {"primary": "en-CA", "secondary": ["fr-CA", "zh-CN"]},
                },
            },
            "AB": {
                "name": "Alberta",
                "primary": "en-CA",
                "secondary": ["fr-CA"],
            },
            "MB": {
                "name": "Manitoba",
                "primary": "en-CA",
                "secondary": ["fr-CA"],
            },
        },
    },
    "US": {
        "name": "United States",
        "default_primary": "en-US",
        "default_secondary": ["es-US"],
        "subdivisions": {
            "PR": {
                "name": "Puerto Rico",
                "primary": "es-US",
                "secondary": ["en-US"],
            },
            "FL": {
                "name": "Florida",
                "primary": "en-US",
                "secondary": ["es-US"],
                "localities": {
                    "miami": {"primary": "en-US", "secondary": ["es-US"]},
                },
            },
            "TX": {
                "name": "Texas",
                "primary": "en-US",
                "secondary": ["es-US"],
            },
            "CA": {
                "name": "California",
                "primary": "en-US",
                "secondary": ["es-US"],
            },
            "NY": {
                "name": "New York",
                "primary": "en-US",
                "secondary": ["es-US"],
            },
        },
    },
    "FR": {
        "name": "France",
        "default_primary": "fr-FR",
        "default_secondary": ["en-US"],
        "subdivisions": {},
    },
    "RO": {
        "name": "România",
        "default_primary": "ro-RO",
        "default_secondary": ["en-US", "fr-FR", "hu-HU"],
        "subdivisions": {
            "CJ": {
                "name": "Cluj",
                "primary": "ro-RO",
                "secondary": ["en-US", "hu-HU"],
            },
        },
    },
    "ES": {
        "name": "España",
        "default_primary": "es-ES",
        "default_secondary": ["en-US"],
        "subdivisions": {
            "CT": {
                "name": "Cataluña",
                "primary": "es-ES",
                "secondary": ["ca-ES", "en-US"],
            },
        },
    },
    "MX": {
        "name": "México",
        "default_primary": "es-ES",  # ou variante es-MX si présente
        "default_secondary": ["en-US"],
        "subdivisions": {},
    },
}

# Emprunts courants, termes techniques, noms propres internationaux à ignorer pour éviter les faux basculements
_UNIVERSAL_LOANWORDS = frozenset({
    "parking", "weekend", "week-end", "meeting", "rendez-vous", "croissant", "merci",
    "bonjour", "hello", "hi", "hey", "bye", "okay", "ok", "cool", "super", "drive-in",
    "sandwich", "fastfood", "fast-food", "email", "mail", "post", "online", "live",
    "call", "store", "shop", "shopping", "business", "deal", "cash", "planning",
    "briefing", "feedback", "boss", "manager", "lead", "client", "service", "apple",
    "google", "avenqo", "uber", "telnyx", "openai", "crm", "retail", "vip",
})

# Motifs de demande explicite de changement de langue
_EXPLICIT_SWITCH_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Demandes vers l'anglais
    (re.compile(r"\b(can we (speak|continue|switch to|talk)( in)? english|let'?s speak english|in english please|switch to english|parlons (en )?anglais|passons (a l'|en )anglais|en anglais s'?il vous pla[iî]t|putem vorbi [iî]n englez[aă]|vorbi[tț]i [iî]n englez[aă]|podemos hablar en ingl[eé]s)\b", re.IGNORECASE), "en-US"),
    # Demandes vers le français
    (re.compile(r"\b(can we (speak|continue|switch to|talk)( in)? french|let'?s speak french|in french please|switch to french|revenons en fran[cç]ais|parlons (en )?fran[cç]ais|en fran[cç]ais s'?il vous pla[iî]t|passons (au|en) fran[cç]ais|putem vorbi [iî]n francez[aă]|vorbi[tț]i [iî]n francez[aă]|podemos hablar en franc[eé]s)\b", re.IGNORECASE), "fr-CA"),
    # Demandes vers l'espagnol
    (re.compile(r"\b(can we (speak|continue|switch to|talk)( in)? spanish|let'?s speak spanish|in spanish please|switch to spanish|parlons (en )?espagnol|en espagnol s'?il vous pla[iî]t|podemos hablar en espa[nñ]ol|hablemos en espa[nñ]ol|en espa[nñ]ol por favor|vorbi[tț]i [iî]n spaniol[aă])\b", re.IGNORECASE), "es-ES"),
    # Demandes vers le roumain
    (re.compile(r"\b(can we (speak|continue|switch to|talk)( in)? romanian|let'?s speak romanian|in romanian please|switch to romanian|parlons (en )?roumain|en roumain s'?il vous pla[iî]t|putem vorbi [iî]n rom[aâ]n[aă]|vorbi[tț]i [iî]n rom[aâ]n[aă]|vorbim [iî]n rom[aâ]n[aă]|podemos hablar en rumano)\b", re.IGNORECASE), "ro-RO"),
]



def to_bcp47(code: str | None) -> str:
    cleaned = (code or "").strip().replace("_", "-")
    case = cleaned.casefold()
    if case in {"fr", "fr-ca"}:
        return "fr-CA"
    if case == "fr-fr":
        return "fr-FR"
    if case in {"en-ca"}:
        return "en-CA"
    if case in {"en", "en-us"}:
        return "en-US"
    if case in {"es", "es-es", "es-419", "es-latam"}:
        return "es-ES"
    if case in {"ro", "ro-ro"}:
        return "ro-RO"
    if "-" in cleaned:
        parts = cleaned.split("-", 1)
        return f"{parts[0].lower()}-{parts[1].upper()}"
    return cleaned or "fr-CA"


@dataclass(frozen=True, slots=True)
class RegionLanguageRecommendation:
    country_code: str
    region: str | None
    locality: str | None
    primary_locale: str
    secondary_locales: list[str]
    allowed_locales: list[str]
    source: str = "regional_directory"


class RegionLanguageResolver:
    """Résout les recommandations linguistiques régionales à partir du pays et de la subdivision."""

    @classmethod
    def resolve(
        cls,
        country_code: str,
        region: str | None = None,
        locality: str | None = None,
    ) -> RegionLanguageRecommendation:
        c_code = (country_code or "").strip().upper()
        country_data = REGION_LANGUAGE_DATA.get(c_code)
        if country_data is None:
            # Fallback vers locale catalogue
            primary = to_bcp47(f"en-{c_code}" if len(c_code) == 2 else "en-US")
            return RegionLanguageRecommendation(
                country_code=c_code,
                region=region,
                locality=locality,
                primary_locale=primary,
                secondary_locales=["en-US"] if primary != "en-US" else ["fr-FR"],
                allowed_locales=[primary, "en-US", "fr-FR", "es-ES", "ro-RO"],
                source="fallback",
            )

        subdivisions = country_data.get("subdivisions", {})
        sub_key = (region or "").strip().upper()
        sub_data = subdivisions.get(sub_key)

        loc_key = (locality or "").strip().lower()
        loc_data = sub_data.get("localities", {}).get(loc_key) if sub_data else None

        if loc_data:
            primary = loc_data["primary"]
            secondary = list(loc_data.get("secondary", []))
        elif sub_data:
            primary = sub_data["primary"]
            secondary = list(sub_data.get("secondary", []))
        else:
            primary = country_data["default_primary"]
            secondary = list(country_data.get("default_secondary", []))

        # Assure des codes BCP-47 résolus
        canonical_primary = to_bcp47(primary)
        canonical_secondary = [to_bcp47(s) for s in secondary if to_bcp47(s) != canonical_primary]

        all_allowed = [canonical_primary] + canonical_secondary
        for extra in ("fr-CA", "en-CA", "en-US", "es-ES", "ro-RO"):
            if extra not in all_allowed:
                all_allowed.append(extra)

        return RegionLanguageRecommendation(
            country_code=c_code,
            region=region,
            locality=locality,
            primary_locale=canonical_primary,
            secondary_locales=canonical_secondary,
            allowed_locales=all_allowed,
            source="regional_directory",
        )


@dataclass
class CallLanguageSession:
    """Gère le verrou linguistique par appel téléphonique (Language Lock).

    Garantit que la conversation conserve la langue active sans dériver
    à cause d'accents, de mots d'emprunt, d'erreurs STT ou de noms propres.
    """

    tenant_id: UUID
    call_session_id: str
    primary_locale: str
    active_locale: str
    allowed_locales: tuple[str, ...]
    language_lock_state: str = "LOCKED"  # LOCKED | PENDING_CONFIRMATION | SWITCHED
    explicit_switch_requested: bool = False
    confidence: float | None = 1.0
    evidence: str = "initial_configuration"
    last_confirmed_locale: str = ""
    consecutive_evidence_count: int = 0
    pending_candidate_locale: str | None = None

    def __post_init__(self) -> None:
        self.primary_locale = to_bcp47(self.primary_locale)
        self.active_locale = to_bcp47(self.active_locale or self.primary_locale)
        self.last_confirmed_locale = self.active_locale
        if not self.allowed_locales:
            self.allowed_locales = (self.primary_locale, "en-US", "fr-CA", "es-ES", "ro-RO")
        else:
            self.allowed_locales = tuple(to_bcp47(loc) for loc in self.allowed_locales)

    def _normalize(self, text: str) -> str:
        safe = (text or "").strip().lower()
        return "".join(
            c for c in unicodedata.normalize("NFKD", safe)
            if not unicodedata.combining(c)
        )

    def check_explicit_switch(self, transcript: str) -> str | None:
        """Vérifie si l'énoncé contient une demande explicite de changement de langue."""
        norm = self._normalize(transcript)
        for pattern, target_locale in _EXPLICIT_SWITCH_PATTERNS:
            if pattern.search(norm):
                # Adapter la variante régionale si l'entreprise a une préférence dans allowed_locales
                target_lang = target_locale.split("-")[0]
                matching_allowed = next(
                    (loc for loc in self.allowed_locales if loc.split("-")[0] == target_lang),
                    target_locale,
                )
                return to_bcp47(matching_allowed)
        return None

    def process_utterance(self, transcript: str) -> str:
        """Traite un énoncé de l'appelant avec verrouillage strict."""
        if not transcript or not transcript.strip():
            # Garder la langue active verrouillée durant les silences
            return self.active_locale

        # 1. Priorité absolue : Demande explicite de changement de langue
        explicit_target = self.check_explicit_switch(transcript)
        if explicit_target:
            self.active_locale = explicit_target
            self.last_confirmed_locale = explicit_target
            self.explicit_switch_requested = True
            self.language_lock_state = "LOCKED"
            self.confidence = 1.0
            self.evidence = f"explicit_switch_request: {transcript}"
            self.consecutive_evidence_count = 0
            self.pending_candidate_locale = None
            return self.active_locale

        norm = self._normalize(transcript)
        words = set(re.findall(r"\b\w+\b", norm))

        # 2. Ignorer un mot unique ambigu ou d'emprunt universel
        if len(words) <= 1:
            return self.active_locale

        # Si tous les mots ou la majorité sont des emprunts universels / noms propres
        non_loanwords = words - _UNIVERSAL_LOANWORDS
        if not non_loanwords:
            return self.active_locale

        # 3. Détection statistique de l'énoncé
        detection = detect_spoken_language(transcript, preferred_locale=self.active_locale)
        detected_locale = detection.locale

        if not detected_locale:
            # Erreur STT ou texte court / ambigu -> maintien verrouillé
            return self.active_locale

        detected_bcp47 = to_bcp47(detected_locale)
        detected_lang = detected_bcp47.split("-")[0]
        active_lang = self.active_locale.split("-")[0]

        # Si l'énoncé correspond à la langue active, réinitialiser tout candidat en attente
        if detected_lang == active_lang:
            self.consecutive_evidence_count = 0
            self.pending_candidate_locale = None
            return self.active_locale

        # 4. Énoncé dans une autre langue : requiert 3 énoncés consécutifs à haute confiance
        # pour un changement implicite, afin d'éviter les bascules dues à un accent ou à un emprunt.
        if detection.confidence and detection.confidence >= 0.90 and len(words) >= 4:
            if self.pending_candidate_locale == detected_bcp47:
                self.consecutive_evidence_count += 1
            else:
                self.pending_candidate_locale = detected_bcp47
                self.consecutive_evidence_count = 1

            if self.consecutive_evidence_count >= 3:
                # Bascule implicite après preuves robustes accumulées
                self.active_locale = detected_bcp47
                self.last_confirmed_locale = detected_bcp47
                self.language_lock_state = "SWITCHED"
                self.confidence = detection.confidence
                self.evidence = f"consecutive_implicit_detection_{self.consecutive_evidence_count}_turns"
                self.consecutive_evidence_count = 0
                self.pending_candidate_locale = None
                return self.active_locale

        # Maintien de la langue active par défaut (Language Lock)
        return self.active_locale

    def as_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": str(self.tenant_id),
            "call_session_id": self.call_session_id,
            "primary_locale": self.primary_locale,
            "active_locale": self.active_locale,
            "allowed_locales": list(self.allowed_locales),
            "language_lock_state": self.language_lock_state,
            "explicit_switch_requested": self.explicit_switch_requested,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "last_confirmed_locale": self.last_confirmed_locale,
        }
