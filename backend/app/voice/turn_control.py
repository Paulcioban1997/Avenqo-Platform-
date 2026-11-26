"""Centralized conversational turn control, barge-in adjudication, and objection understanding.

Voice activity alone is not a new question. A pending answer is replaced when:
1. A confirmed or partial non-echo transcript contains an explicit interruption,
   human objection/correction, attention check ("Allô, tu m'entends ?"), or
   substantive new question.
2. Backchannels ("euh", "oui", "d'accord", "merci") and playback echoes are
   filtered so they never disrupt active speech.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import StrEnum
import math
import re
import time
import unicodedata


class ConversationState(StrEnum):
    """Canonical conversational turn states for Avenqo Voice."""

    LISTENING = "LISTENING"
    USER_SPEAKING = "USER_SPEAKING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    INTERRUPTED = "INTERRUPTED"
    RECOVERING = "RECOVERING"


_PHASE_TO_STATE: dict[str, ConversationState] = {
    "LISTENING": ConversationState.LISTENING,
    "USER_SPEAKING": ConversationState.USER_SPEAKING,
    "PROCESSING": ConversationState.THINKING,
    "THINKING": ConversationState.THINKING,
    "SYNTHESIZING": ConversationState.SPEAKING,
    "PLAYING": ConversationState.SPEAKING,
    "SPEAKING": ConversationState.SPEAKING,
    "RESPONDING": ConversationState.SPEAKING,
    "INTERRUPTED": ConversationState.INTERRUPTED,
    "RECOVERING": ConversationState.RECOVERING,
}


def canonical_conversation_state(phase: str) -> ConversationState:
    return _PHASE_TO_STATE.get((phase or "").upper(), ConversationState.LISTENING)


# NOTE: "allo" / "allô" / "hello" are intentionally NOT in _BACKCHANNELS so a
# caller trying to get attention during a monologue or after silence is never ignored.
_BACKCHANNELS = frozenset({
    "euh", "heu", "hum", "hm", "um", "uh", "ah", "oh", "ok", "okay", "hein",
    "oui", "ouais", "yeah", "yes", "bon", "quoi", "pardon",
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
    "nip", "pin", "attends", "stop", "annuler", "pause", "marge", "rentable",
    "rentables", "promouvoir", "opportunite", "opportunites",
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


def is_attention_check(text: str) -> bool:
    """Detect caller attention checks ('Allô ?', 'Allô, tu m'entends ?', 'Hello? Can you hear me?')."""
    normalized = _normalize(text)
    if not normalized:
        return False
    if normalized in {"allo", "allo allo", "hello", "hello hello", "alo", "alo alo"}:
        return True
    patterns = [
        r"\b(allo|alo|hello)\b.{0,25}\b(entends|entendez|la|ici|hear|there|escuchas|escucha|auzi|auziti)\b",
        r"\b(tu\s+m\s*entends|vous\s+m\s*entendez|est\s+ce\s+que\s+tu\s+m\s*entends|tu\s+es\s+la|vous\s+etes\s+la)\b",
        r"\b(can\s+you\s+hear\s+me|do\s+you\s+hear\s+me|are\s+you\s+there|are\s+you\s+listening)\b",
        r"\b(me\s+escuchas|me\s+escucha|estas\s+ahi|me\s+oyes)\b",
        r"\b(ma\s+auzi|ma\s+auziti|esti\s+acolo|sunteti\s+acolo)\b",
    ]
    return any(re.search(p, normalized) for p in patterns)


def extract_request_after_attention_check(text: str) -> str | None:
    """Extract an embedded substantive request following a leading attention check.

    Examples:
        "Allô, tu m'entends ? Quel est le prix des casques ?" -> "Quel est le prix des casques ?"
        "Hello, can you hear me? What are your opening hours?" -> "What are your opening hours?"
        "Allô, tu m'entends ?" -> None
    """
    if not text or not is_attention_check(text):
        return None

    stripped = text.strip()
    remainder = stripped
    clause_patterns = [
        # Greeting/attention prefixes (FR/EN/ES/RO)
        r"^[¿¡\s]*(?:all[oô]|al[oó]|hello)(?:[\s,?!.:;\-]+(?:all[oô]|al[oó]|hello))*[\s,?!.:;\-]+",
        r"^[¿¡\s]*(?:est[- ]ce\s+que\s+)?(?:tu\s+m['’]?entends|vous\s+m['’]?entendez|tu\s+es\s+l[aà]|vous\s+[eê]tes\s+l[aà])[\s,?!.:;\-]+",
        r"^[¿¡\s]*(?:can\s+you\s+hear\s+me|do\s+you\s+hear\s+me|are\s+you\s+there|are\s+you\s+listening)[\s,?!.:;\-]+",
        r"^[¿¡\s]*(?:me\s+escuchas?|est[aá]s\s+ah[ií]|me\s+oyes?)[\s,?!.:;\-]+",
        r"^[¿¡\s]*(?:m[aă]\s+auzi(?:[tț]i)?|e[sș]ti\s+acolo|sunte[tț]i\s+acolo)[\s,?!.:;\-]+",
    ]

    for _ in range(4):
        changed = False
        for pat in clause_patterns:
            updated = re.sub(pat, "", remainder, flags=re.IGNORECASE).strip()
            if updated != remainder:
                remainder = updated
                changed = True
                break
        if not changed:
            break

    # Remove optional leading transition connectors after the attention check
    remainder = re.sub(
        r"^(?:et|mais|alors|donc|dis[- ]moi|dites[- ]moi|and|so|well|y|pero|si|și)\s+",
        "",
        remainder,
        flags=re.IGNORECASE,
    ).strip()

    if not remainder or remainder == stripped:
        return None
    if is_attention_check(remainder) or is_backchannel(remainder):
        return None
    if is_substantive_utterance(remainder) or is_correction_or_objection(remainder):
        return remainder
    return None


def is_correction_or_objection(text: str) -> bool:
    """Context-aware multilingual detection of human objections and corrections (FR/EN/ES/RO)."""
    normalized = _normalize(text)
    if not normalized:
        return False

    explicit_patterns = [
        # French
        r"\b(non\s+)?(ce\s+nest|cest|ce\s+n\s+est)\s+pas\s+(de\s+)?ca(\s+que\s+je\s+(parlais|voulais|demandais|disais))?\b",
        r"\b(non\s+)?pas\s+de\s+ca\b",
        r"\b(je\s+ne\s+parlais\s+pas\s+de\s+ca|je\s+parlais\s+pas\s+de\s+ca|je\s+voulais\s+pas\s+dire\s+ca|je\s+ne\s+voulais\s+pas\s+dire\s+ca)\b",
        r"\b(tu\s+mas|vous\s+mavez)\s+mal\s+compris\b",
        r"\b(tu\s+nas|tu\s+as|vous\s+navez)\s+pas\s+compris\b",
        r"\b(attends|attendez|arrete|arretez|stop)\s*,?\s*(ecoute\s*moi|ecoutez\s*moi|je\s+veux\s+autre\s+chose|autre\s+chose)\b",
        r"\b(ecoute\s*moi|ecoutez\s*moi|tu\s+ne\s+mecoutes\s+pas|tu\s+mecoutes\s+pas)\b",
        r"\b(je\s+veux\s+dire\s+autre\s+chose|je\s+voulais\s+dire\s+autre\s+chose|je\s+parle\s+dautre\s+chose|je\s+parlais\s+dautre\s+chose)\b",
        r"\b(cest\s+pas\s+ma\s+question|ce\s+nest\s+pas\s+ma\s+question|pas\s+du\s+tout\s+ca|rien\s+a\s+voir)\b",
        # English
        r"\b(thats|that\s+is|its|it\s+is)\s+not\s+what\s+i\s+(meant|asked|said|was\s+talking\s+about)\b",
        r"\bnot\s+what\s+i\s+(meant|asked|said)\b",
        r"\b(you\s+misunderstood|you\s+didnt\s+understand|you\s+did\s+not\s+understand)\b",
        r"\b(stop|wait|hold\s+on)\s*,?\s*(listen\s+to\s+me|i\s+meant|i\s+want\s+something\s+else)\b",
        r"\blisten\s+to\s+me\b",
        r"\bi\s+meant\s+something\s+else\b",
        r"\bthats\s+not\s+it\b",
        # Spanish
        r"\b(no\s+es\s+eso\s+lo\s+que\s+(queria\s+decir|decia|preguntaba|hablaba)|no\s+hablaba\s+de\s+eso|no\s+es\s+eso)\b",
        r"\b(espera|espere|para)\s*,?\s*(escuchame|escucheme)\b",
        r"\b(me\s+entendiste\s+mal|no\s+me\s+entendiste|me\s+entendio\s+mal|no\s+me\s+entendio)\b",
        r"\bquiero\s+decir\s+otra\s+cosa\b",
        # Romanian
        r"\b(nu\s+asta\s+am\s+vrut\s+sa\s+spun|nu\s+despre\s+asta\s+vorbeam|nu\s+asta\s+am\s+intrebat)\b",
        r"\b(stai\s+putin|stai|opreste)\s*,?\s*(asculta\s*ma|ascultati\s*ma)\b",
        r"\b(m\s*ai\s+inteles\s+gresit|nu\s+m\s*ai\s+inteles|ati\s+inteles\s+gresit)\b",
        r"\bvreau\s+sa\s+spun\s+altceva\b",
    ]
    if any(re.search(p, normalized) for p in explicit_patterns):
        return True

    # Semantic fallback: negation + communicative/reference verb + misunderstanding/correction context
    words = set(normalized.split())
    has_negation = bool(words & {"non", "pas", "no", "not", "nu", "mal", "wrong", "gresit"})
    has_comm = bool(words & {
        "parlais", "parle", "voulais", "compris", "demandais", "question", "ecoute", "ecoutez",
        "meant", "misunderstood", "understand", "listen", "asked",
        "queria", "hablaba", "entendiste", "escuchame",
        "vrut", "vorbeam", "inteles", "asculta",
    })
    has_target = bool(words & {
        "ca", "cela", "autre", "chose", "moi", "that", "else", "me", "eso", "otra", "cosa", "asta", "altceva",
    })
    return has_negation and has_comm and has_target


def extract_reformulation_after_correction(text: str) -> str | None:
    """If the caller combined an objection with a new request, extract the reformulated request.

    Example:
        "Non, c'est pas de ça que je parlais, je veux voir les produits les plus rentables"
        -> "je veux voir les produits les plus rentables"
    Returns None if the utterance is a pure objection without a substantive reformulation.
    """
    if not text or not is_correction_or_objection(text):
        return None

    # Split on clause delimiters or conjunctions after the objection clause
    stripped = text.strip()
    prefix_patterns = [
        r"^(?:non[\s,]+)?(?:ce\s+n['’]est|c['’]est)\s+pas\s+(?:de\s+)?[çc]a(?:\s+que\s+je\s+(?:parlais|voulais|demandais|disais))?[\s,;:.!\-]+",
        r"^(?:non[\s,]+)?(?:je\s+ne\s+parlais\s+pas\s+de\s+[çc]a|je\s+parlais\s+pas\s+de\s+[çc]a)[\s,;:.!\-]+",
        r"^(?:non[\s,]+)?(?:tu\s+m['’]as|vous\s+m['’]avez)\s+mal\s+compris[\s,;:.!\-]+",
        r"^(?:attends|attendez|arr[eê]te|arr[eê]tez|stop)[\s,]+(?:[eé]coute[- ]moi|[eé]coutez[- ]moi)?[\s,;:.!\-]+",
        r"^(?:no[\s,]+)?(?:that['’]?s|that\s+is)\s+not\s+what\s+i\s+(?:meant|asked|said)[\s,;:.!\-]+",
        r"^(?:stop|wait|hold\s+on)[\s,]+(?:listen\s+to\s+me)?[\s,;:.!\-]+",
        r"^(?:you\s+misunderstood(?:\s+my\s+question|\s+me)?)[\s,;:.!\-]+",
        r"^(?:no\s+es\s+eso\s+lo\s+que\s+quer[ií]a\s+decir|espera[\s,]+esc[uú]chame)[\s,;:.!\-]+",
        r"^(?:nu\s+asta\s+am\s+vrut\s+s[aă]\s+spun|stai\s+pu[tț]in[\s,]+ascult[aă][- ]m[aă])[\s,;:.!\-]+",
    ]
    remainder = stripped
    for pat in prefix_patterns:
        updated = re.sub(pat, "", remainder, flags=re.IGNORECASE).strip()
        if updated != remainder:
            remainder = updated
            break

    # Strip leading discourse connectors ("mais", "but", "pero", "dar")
    remainder = re.sub(r"^(?:mais|but|pero|dar|en\s+fait|actually)\s+", "", remainder, flags=re.IGNORECASE).strip()

    if not remainder or remainder == stripped:
        return None
    if is_correction_or_objection(remainder) or is_backchannel(remainder) or is_attention_check(remainder):
        return None
    if is_substantive_utterance(remainder):
        return remainder
    return None


def build_correction_clarification(
    locale: str,
    *,
    last_topic: str | None = None,
    is_attention: bool = False,
) -> str:
    """Build a short, natural clarification after stopping an unwanted response."""
    loc = (locale or "fr-CA").casefold()
    if is_attention:
        if loc.startswith("es"):
            return "Sí, le escucho bien. ¿En qué puedo ayudarle?"
        if loc.startswith("ro"):
            return "Da, vă aud bine. Cu ce vă pot ajuta?"
        if loc.startswith("en"):
            return "Yes, I hear you clearly. How can I help?"
        return "Oui, je vous entends bien. De quoi souhaitez-vous parler ?"

    is_retail_topic = (last_topic or "") in {"retail_catalog", "retail_commercial_clarification", "retail"}
    if is_retail_topic:
        if loc.startswith("es"):
            return "De acuerdo, entendí mal. ¿Qué tipo de productos buscas exactamente?"
        if loc.startswith("ro"):
            return "Bine, am înțeles greșit. Ce tip de produse cauți mai exact?"
        if loc.startswith("en"):
            return "Got it, I misunderstood. What kind of products are you looking for exactly?"
        return "D'accord, j'ai mal compris. Tu cherches quels types de produits exactement ?"

    if loc.startswith("es"):
        return "De acuerdo, entendí mal. ¿De qué querías hablar exactamente?"
    if loc.startswith("ro"):
        return "Bine, am înțeles greșit. Despre ce voiai să vorbim mai exact?"
    if loc.startswith("en"):
        return "Got it, I misunderstood. What did you want to talk about?"
    return "D'accord, j'ai mal compris. De quoi voulais-tu parler exactement ?"


def is_backchannel(text: str) -> bool:
    """Detect brief caller acknowledgements, hesitations, or filler tokens."""
    norm = _normalize(text)
    if not norm:
        return True
    if is_attention_check(norm) or is_correction_or_objection(norm):
        return False
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


_GREETING_WORDS = frozenset({
    "allo", "bonjour", "bonsoir", "buna", "hello", "hi", "hola", "salut",
})


def is_substantive_utterance(transcript: str) -> bool:
    """True when utterance has enough content to represent a genuine new caller question."""
    if is_correction_or_objection(transcript) or is_attention_check(transcript):
        return True
    words = _words(transcript)
    if len(words) >= 3:
        return True
    if words and all(word in _GREETING_WORDS for word in words):
        return True
    return any(word in _QUERY_KEYWORDS for word in words)


def is_explicit_interruption(text: str) -> bool:
    """Detect clear caller barge-in cues intended to halt agent playback."""
    normalized = _normalize(text)
    if not normalized:
        return False
    if is_correction_or_objection(normalized) or is_attention_check(normalized):
        return True
    patterns = [
        r"\b(excusez\s*moi|excuse\s*moi|pardon|desole)\b.{0,25}\b(couper|coupe|interrompre|interromps|arreter|arrete|parler)\b",
        r"\b(attendez|attends|stop|arretez|arrete|une seconde|une minute|un instant|pause)\b",
        r"\b(wait|hold on|stop talking|excuse me for interrupting|let me speak)\b",
        r"\b(stai|stai putin|opriti|opreste|scuzati|scuza ma ca te intrerup)\b",
        r"\b(espera|espere|para|disculpe que lo interrumpa)\b",
        r"\b(autre\s+question|une\s+autre\s+question|jai\s+une\s+autre\s+question)\b",
    ]
    return any(re.search(p, normalized) for p in patterns)


_DANGLING_CONTINUATION_TAILS = frozenset({
    "et", "ou", "pour", "avec", "sans", "dans", "sur", "de", "du", "des",
    "a", "au", "aux", "en", "par", "chez", "vers",
    "and", "or", "for", "with", "in", "to", "of", "by",
})
_LEADING_CONTINUATION_WORDS = frozenset({
    "et", "ou", "pour", "avec", "sans", "puis", "aussi", "en", "sur", "par",
    "dans", "de", "du", "des", "a", "au", "aux",
    "and", "or", "for", "with", "also", "to", "in", "on",
})


def adjudicate_transcript(
    transcript: str,
    *,
    phase: str,
    in_flight_transcript: str | None = None,
    last_spoken: str | None = None,
    allow_barge_in: bool = True,
    seconds_since_last_turn: float = 0.0,
    in_flight_age_seconds: float | None = None,
) -> str:
    """Return ignore, accept, coalesce, queue, or replace.

    replace supersedes an in-flight answer. coalesce merges a split continuation
    into the active thinking turn. queue schedules a follow-up turn without
    aborting current work or playback. ignore drops noise, duplicates, and echoes.
    """
    if not transcript or not transcript.strip():
        return "ignore"
    if in_flight_transcript and same_utterance(transcript, in_flight_transcript):
        return "ignore"
    if last_spoken and (same_utterance(transcript, last_spoken) or is_playback_echo(transcript, last_spoken)):
        return "ignore"

    active = phase in {"THINKING", "SYNTHESIZING", "PLAYING", "SPEAKING"}

    # Attention checks ("Allô ? Tu m'entends ?") are NEVER ignored as backchannels
    if is_attention_check(transcript):
        if active:
            return "replace" if allow_barge_in else "accept"
        return "accept"

    if is_correction_or_objection(transcript):
        if active:
            return "replace" if allow_barge_in else "accept"
        return "accept"

    if is_backchannel(transcript):
        return "ignore"

    if not active:
        return "accept"

    if is_explicit_interruption(transcript):
        return "replace" if allow_barge_in else "accept"

    if phase in {"THINKING", "SYNTHESIZING"}:
        # Distinguishes a split continuation fragment from a distinct back-to-back question.
        in_words = _words(in_flight_transcript) if in_flight_transcript else []
        new_words = _words(transcript)
        has_continuation_link = (
            (bool(in_words) and in_words[-1] in _DANGLING_CONTINUATION_TAILS)
            or (bool(new_words) and new_words[0] in _LEADING_CONTINUATION_WORDS)
        )
        if (
            in_flight_transcript
            and has_continuation_link
            and (in_flight_age_seconds is None or in_flight_age_seconds <= 3.5)
            and len(new_words) <= 6
        ):
            return "coalesce"
        if is_substantive_utterance(transcript):
            if in_flight_transcript:
                return "queue"
            return "replace"
        return "ignore"

    if phase in {"PLAYING", "SPEAKING"}:
        if not allow_barge_in:
            return "accept"
        # During audio playback, substantive speech triggers barge-in; short non-query noise is ignored.
        if is_substantive_utterance(transcript):
            return "replace"
        return "ignore"

    return "accept"


def compute_percentile(samples: list[float], pct: float) -> float | None:
    """Compute nearest-rank percentile (e.g. p50, p95) for latency measurements."""
    if not samples:
        return None
    ordered = sorted(samples)
    idx = max(0, min(len(ordered) - 1, math.ceil((pct / 100.0) * len(ordered)) - 1))
    return round(ordered[idx], 2)


@dataclass
class VoiceTurnOrchestrator:
    """Centralized conversational turn state machine with idempotent cancellation and latency metrics."""

    state: ConversationState = ConversationState.LISTENING
    epoch: int = 0
    active_turn_id: str | None = None
    active_response_id: str | None = None
    cancelled_response_ids: set[str] = field(default_factory=set)
    barge_in_latencies_ms: list[float] = field(default_factory=list)
    first_audio_latencies_ms: list[float] = field(default_factory=list)
    central_ai_latencies_ms: list[float] = field(default_factory=list)
    last_transition_at: float = field(default_factory=time.monotonic)
    last_user_turn_at: float = field(default_factory=time.monotonic)
    last_speech_started_at: float | None = None

    def transition(self, next_state: ConversationState | str) -> ConversationState:
        resolved = next_state if isinstance(next_state, ConversationState) else canonical_conversation_state(next_state)
        self.state = resolved
        self.last_transition_at = time.monotonic()
        return self.state

    def begin_turn(self, turn_id: str, epoch: int) -> None:
        self.active_turn_id = turn_id
        self.epoch = epoch
        self.last_user_turn_at = time.monotonic()
        self.transition(ConversationState.THINKING)

    def bind_response(self, response_id: str, turn_id: str) -> None:
        self.active_response_id = response_id
        self.active_turn_id = turn_id
        self.transition(ConversationState.SPEAKING)

    def mark_response_cancelled(self, response_id: str | None) -> bool:
        """Idempotent cancellation guard. Returns False if response_id was already cancelled."""
        if not response_id:
            return True
        if response_id in self.cancelled_response_ids:
            return False
        self.cancelled_response_ids.add(response_id)
        if len(self.cancelled_response_ids) > 500:
            self.cancelled_response_ids.clear()
        if self.active_response_id == response_id:
            self.active_response_id = None
        return True

    def record_barge_in_latency(self, ms: float) -> None:
        if ms >= 0:
            self.barge_in_latencies_ms.append(float(ms))

    def record_first_audio_latency(self, ms: float) -> None:
        if ms >= 0:
            self.first_audio_latencies_ms.append(float(ms))

    def record_central_ai_latency(self, ms: float) -> None:
        if ms >= 0:
            self.central_ai_latencies_ms.append(float(ms))

    def latency_summary(self) -> dict[str, dict[str, float | int | None]]:
        return {
            "barge_in_reaction_ms": {
                "count": len(self.barge_in_latencies_ms),
                "p50": compute_percentile(self.barge_in_latencies_ms, 50),
                "p95": compute_percentile(self.barge_in_latencies_ms, 95),
            },
            "first_audio_latency_ms": {
                "count": len(self.first_audio_latencies_ms),
                "p50": compute_percentile(self.first_audio_latencies_ms, 50),
                "p95": compute_percentile(self.first_audio_latencies_ms, 95),
            },
            "central_ai_latency_ms": {
                "count": len(self.central_ai_latencies_ms),
                "p50": compute_percentile(self.central_ai_latencies_ms, 50),
                "p95": compute_percentile(self.central_ai_latencies_ms, 95),
            },
        }
