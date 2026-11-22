"""Decide whether a transcript may replace an in-flight voice answer.

Voice activity alone is not a new question. A pending answer is replaced only
when a confirmed transcript is a distinct utterance, and playback is cut only
when barge-in is enabled.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

_BACKCHANNELS = frozenset({
    "euh", "heu", "hum", "hm", "um", "uh", "ah", "oh", "ok", "okay", "hein",
    "allo", "allô", "hello", "oui", "ouais", "yeah", "yes", "bon", "quoi", "pardon",
    "d'accord", "daccord", "dac", "exactement", "parfait", "super", "merci",
    "tres bien", "très bien", "cool", "right", "sure", "got it", "i see",
    "entendu", "compris", "ah oui", "ah ok", "ouais d'accord", "da", "si", "vale",
})

_QUERY_KEYWORDS = frozenset({
    "prix", "price", "cout", "coute", "tarif", "tarifs", "combien",
    "horaire", "horaires", "heure", "heures", "ouvert", "ouverture", "fermeture",
    "produit", "produits", "article", "articles", "catalogue", "catalog",
    "acheter", "vendre", "commande", "stock", "disponible", "disponibles",
    "reserver", "reservation", "rendez-vous", "rdv", "appointment", "booking",
    "service", "services", "prestation", "prestations", "adresse", "contact",
    "nip", "pin", "attends", "stop", "annuler", "pause",
})


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    contracted = re.sub(r"['’`]", "", ascii_text)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", contracted)).strip()


def _words(text: str) -> list[str]:
    normalized = _normalize(text)
    return normalized.split() if normalized else []


def same_utterance(left: str, right: str) -> bool:
    """True when two transcripts are the same question, a partial, or an echo."""
    a = _normalize(left)
    b = _normalize(right)
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    # A short greeting such as "bonjour" must not be treated as an echo of the
    # full welcome sentence. Partials still match when they cover most of it.
    if shorter in longer and len(shorter) >= max(12, int(len(longer) * 0.6)):
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.82


def is_playback_echo(transcript: str, last_spoken: str | None) -> bool:
    """Detect acoustic echo where synthesized voice audio bleeds back into the microphone."""
    if not transcript or not last_spoken:
        return False
    a = _normalize(transcript)
    b = _normalize(last_spoken)
    if not a or not b:
        return False
    if a == b:
        return True
    # If a multi-word slice of the agent's speech is heard on the mic:
    words_a = a.split()
    if len(words_a) >= 2 and a in b:
        return True
    if len(a) >= 10 and a in b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.78


def is_backchannel(text: str) -> bool:
    """Detect brief caller acknowledgements, hesitations, or filler tokens."""
    norm = _normalize(text)
    if not norm:
        return True
    if norm in _BACKCHANNELS:
        return True
    words = norm.split()
    if not words:
        return True
    if len(words) == 1 and (words[0] in _BACKCHANNELS or words[0] in {"daccord", "merci", "parfait", "super"}):
        return True
    if len(words) <= 2 and all(word in _BACKCHANNELS or word in {"daccord", "merci", "parfait", "super"} for word in words):
        return True
    if len(words) <= 3 and all(w in _BACKCHANNELS or w in {"daccord", "merci", "parfait", "super", "bien"} for w in words):
        return True
    return False


def is_substantive_utterance(transcript: str) -> bool:
    """True when utterance has enough content to represent a genuine new caller question."""
    words = _words(transcript)
    if len(words) >= 3:
        return True
    # If 1-2 words, check for clear query intent keywords
    return any(w in _QUERY_KEYWORDS for w in words)


def is_explicit_interruption(text: str) -> bool:
    """Detect clear caller barge-in cues intended to halt agent playback."""
    normalized = _normalize(text)
    if not normalized:
        return False
    patterns = [
        r"\b(excusez\s*moi|excuse\s*moi|pardon|desole)\b.{0,25}\b(couper|coupe|interrompre|interromps|arreter|arrete|parler)\b",
        r"\b(attendez|attends|stop|arretez|arrete|une seconde|une minute|un instant|pause)\b",
        r"\b(wait|hold on|stop talking|excuse me for interrupting|let me speak)\b",
        r"\b(stai|stai putin|opriti|opreste|scuzati|scuza ma ca te intrerup)\b",
        r"\b(espera|espere|para|disculpe que lo interrumpa)\b",
        r"\b(autre\s+question|une\s+autre\s+question|jai\s+une\s+autre\s+question)\b",
    ]
    return any(re.search(p, normalized) for p in patterns)


def adjudicate_transcript(
    transcript: str,
    *,
    phase: str,
    in_flight_transcript: str | None = None,
    last_spoken: str | None = None,
    allow_barge_in: bool = True,
) -> str:
    """Return ignore, accept, or replace.

    replace supersedes an in-flight answer. accept queues the question without
    cancelling audio. ignore drops noise, duplicates, and echoes.
    """
    if not transcript or not transcript.strip():
        return "ignore"
    if in_flight_transcript and same_utterance(transcript, in_flight_transcript):
        return "ignore"
    if last_spoken and (same_utterance(transcript, last_spoken) or is_playback_echo(transcript, last_spoken)):
        return "ignore"
    if is_backchannel(transcript):
        return "ignore"

    active = phase in {"THINKING", "SYNTHESIZING", "PLAYING"}
    if not active:
        return "accept"

    if is_explicit_interruption(transcript):
        return "replace" if allow_barge_in else "accept"

    if phase in {"THINKING", "SYNTHESIZING"}:
        # Protect in-flight Central AI computation from short noise, throat clears or hesitations.
        # Only replace if caller spoke a substantive new question.
        if is_substantive_utterance(transcript):
            return "replace"
        return "ignore"

    if phase == "PLAYING":
        if not allow_barge_in:
            return "accept"
        # During audio playback, only substantive speech or explicit interruption causes barge-in.
        if is_substantive_utterance(transcript):
            return "replace"
        return "ignore"

    return "accept"
