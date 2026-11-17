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
})


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", ascii_text)).strip()


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


def is_backchannel(text: str) -> bool:
    words = _words(text)
    if not words:
        return True
    if len(words) == 1 and words[0] in _BACKCHANNELS:
        return True
    if len(words) <= 2 and all(word in _BACKCHANNELS for word in words):
        return True
    return False


def adjudicate_transcript(
    transcript: str,
    *,
    phase: str,
    in_flight_transcript: str | None,
    last_spoken: str | None,
    allow_barge_in: bool,
) -> str:
    """Return ignore, accept, or replace.

    replace supersedes an in-flight answer. accept queues the question without
    cancelling audio. ignore drops noise, duplicates, and echoes.
    """
    if not transcript or not transcript.strip():
        return "ignore"
    if in_flight_transcript and same_utterance(transcript, in_flight_transcript):
        return "ignore"
    if last_spoken and same_utterance(transcript, last_spoken):
        return "ignore"
    active = phase in {"THINKING", "SYNTHESIZING", "PLAYING"}
    if not active:
        return "accept"
    if is_backchannel(transcript):
        return "ignore"
    if phase == "PLAYING" and not allow_barge_in:
        return "accept"
    return "replace"
