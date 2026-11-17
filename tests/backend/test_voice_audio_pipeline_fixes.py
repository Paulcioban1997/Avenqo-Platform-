"""Audio pipeline, interruption, module routing, catalog, and pronunciation regressions.

These tests do not dial, log transcripts, or call a paid provider.
"""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import audioop
import base64
import pytest

from backend.app.ai.central.routing import CentralAIIntentRouter
from backend.app.ai.central.universal_planner import MODULE_TOPIC_KEYWORDS, UniversalCapabilityPlanner
from backend.app.assistants.registry import build_default_assistant_registry
from backend.app.voice.audio_diagnostics import encode_diagnostic_phrase, run_offline_audio_diagnostics
from backend.app.voice.direct_answers import (
    is_module_access_question,
    is_open_catalog_question,
    resolve_direct_voice_answer,
    spoken_catalog_answer,
    spoken_module_answer,
)
from backend.app.voice.messages import apply_spoken_pronunciation, pronunciation_preview, voice_speech_name
from backend.app.voice.telnyx_media import TelnyxMediaBridge
from backend.app.voice.turn_control import adjudicate_transcript


def test_diagnostic_phrase_is_pcmu_20ms_and_audible():
    report = encode_diagnostic_phrase()
    assert report["valid"] is True
    assert report["codec"] == "PCMU"
    assert report["sample_rate_hz"] == 8000
    assert report["frame_bytes"] == 160
    assert report["audible_frames"] > 0
    event = report["events"][0]
    assert event["event"] == "media"
    assert set(event["media"]) == {"payload"}
    frame = base64.b64decode(event["media"]["payload"])
    assert len(frame) == 160
    assert audioop.rms(audioop.ulaw2lin(frame, 2), 2) > 0
    offline = run_offline_audio_diagnostics()
    assert offline["calls_placed"] is False
    assert offline["provider_requests"] == 0
    assert offline["test_a_direct_audio"]["valid"] is True
    assert offline["test_b_tts_encoding"]["valid"] is True


def test_employee_module_question_does_not_select_legal():
    question = "Quels modules Avenqo sont accessibles à mon entreprise ?"
    assert is_module_access_question(question)
    router = CentralAIIntentRouter(build_default_assistant_registry())
    selected = router.select(question)
    assert selected is not None
    assert selected.slug == "tenant_capabilities"
    assert "avenqo" not in MODULE_TOPIC_KEYWORDS["legal"]
    planner = UniversalCapabilityPlanner(build_default_assistant_registry())
    scope = planner.plan_tool_scope(
        question,
        active_modules=frozenset({"legal", "retail", "crm"}),
    )
    assert "legal" not in scope.targeted_modules


def test_module_answer_uses_only_the_supplied_names():
    spoken = spoken_module_answer(["Retail", "CRM"], plan_code="professional", locale="fr-CA")
    assert spoken.startswith("Votre abonnement professional est actif.")
    assert "Votre entreprise dispose actuellement des modules suivants : Retail, CRM." in spoken
    assert "Legal" not in spoken
    empty = spoken_module_answer([], plan_code="base", locale="fr")
    assert "aucun module actif" in empty


def test_catalog_answer_uses_real_rows_and_stays_on_one_company(monkeypatch):
    question = "Quels produits avez-vous en vente et à quels prix ?"
    assert is_open_catalog_question(question)
    company_a = uuid4()
    company_b = uuid4()
    catalogs = {
        company_a: [{"name": "Savon", "price": 12.5, "currency": "CAD", "in_stock": True, "inventory_count": 4}],
        company_b: [],
    }

    class Service:
        def __init__(self, _db):
            pass

        def get_profile(self, company_id):
            return SimpleNamespace(
                has_retail_commerce=True,
                active_modules=("retail",),
                public_products=tuple(catalogs[company_id]),
                currency_code="CAD",
            )

    monkeypatch.setattr(
        "backend.app.services.company_intelligence_service.CompanyIntelligenceService",
        Service,
    )
    heard_a = resolve_direct_voice_answer(
        None, company_id=company_a, transcript=question,
        authenticated_staff=False, staff_role=None, locale="fr",
    )
    heard_b = resolve_direct_voice_answer(
        None, company_id=company_b, transcript=question,
        authenticated_staff=False, staff_role=None, locale="fr",
    )
    assert "Savon" in heard_a
    assert "12.5" in heard_a
    assert "CAD" in heard_a
    assert "Savon" not in heard_b
    assert "aucun produit" in heard_b
    disabled = spoken_catalog_answer([{"name": "Secret"}], retail_enabled=False, locale="fr")
    assert "Secret" not in disabled
    assert "n'est pas disponible" in disabled


def test_customer_cannot_hear_another_tenant_modules(monkeypatch):
    question = "Quels modules Avenqo sont accessibles à mon entreprise ?"
    seen = {}

    class Entitlements:
        def __init__(self, _db):
            pass

        def summary(self, tenant):
            seen["company_id"] = tenant.company_id
            return SimpleNamespace(
                plan_code="base",
                active_modules=("retail",),
                modules=(SimpleNamespace(display_name="Retail", active=True), SimpleNamespace(display_name="Legal", active=False)),
            )

    monkeypatch.setattr("backend.app.services.module_entitlement_service.ModuleEntitlementService", Entitlements)
    company_id = uuid4()
    refused = resolve_direct_voice_answer(
        None, company_id=company_id, transcript=question,
        authenticated_staff=False, staff_role=None, locale="fr",
    )
    assert "réservée aux employés" in refused
    assert "company_id" not in seen
    spoken = resolve_direct_voice_answer(
        None, company_id=company_id, transcript=question,
        authenticated_staff=True, staff_role="owner", locale="fr",
    )
    assert seen["company_id"] == company_id
    assert "Retail" in spoken
    assert "Legal" not in spoken


def test_pronunciation_alias_is_spoken_and_stored_name_is_kept():
    stored = SimpleNamespace(
        business_name="Produits Ero",
        voice_display_name="Produits Ero",
        effective_voice_name="Produits Ero",
        custom_pronunciation=None,
        preferred_language="fr",
    )
    assert voice_speech_name(stored) == "Produits, Ero"
    assert stored.business_name == "Produits Ero"
    preview = pronunciation_preview(stored)
    assert preview["stored_name"] == "Produits Ero"
    assert preview["spoken_name"] == "Produits, Ero"
    assert preview["telnyx_ivr"] == preview["gemini_live"] == preview["welcome"]
    assert "Zéro" not in preview["spoken_name"]
    assert "Hero" not in preview["spoken_name"]
    aliased = SimpleNamespace(
        business_name="Produits Ero",
        voice_display_name="Produits Ero",
        effective_voice_name="Produits, Éro",
        custom_pronunciation='{"company":"Produits, Éro"}',
        preferred_language="fr",
    )
    spoken = apply_spoken_pronunciation("Bienvenue chez Produits Ero.", aliased)
    assert spoken == "Bienvenue chez Produits, Éro."
    other = SimpleNamespace(
        business_name="Garage Nord",
        voice_display_name="Garage Nord",
        effective_voice_name="Garage Nord",
        custom_pronunciation=None,
        preferred_language="fr",
    )
    assert voice_speech_name(other) == "Garage Nord"
    assert apply_spoken_pronunciation("Bienvenue chez Garage Nord.", other) == "Bienvenue chez Garage Nord."


def test_vad_and_partial_transcripts_do_not_replace_an_answer():
    assert adjudicate_transcript(
        "euh", phase="PLAYING", in_flight_transcript=None,
        last_spoken="Voici votre réponse complète.", allow_barge_in=True,
    ) == "ignore"
    assert adjudicate_transcript(
        "Quels modules sont accessibles à mon entreprise",
        phase="THINKING",
        in_flight_transcript="Quels modules sont accessibles",
        last_spoken=None,
        allow_barge_in=True,
    ) == "ignore"
    assert adjudicate_transcript(
        "Je voudrais poser une autre question maintenant",
        phase="PLAYING",
        in_flight_transcript=None,
        last_spoken="Voici la liste des produits.",
        allow_barge_in=True,
    ) == "replace"
    assert adjudicate_transcript(
        "Je voudrais poser une autre question maintenant",
        phase="PLAYING",
        in_flight_transcript=None,
        last_spoken="Voici la liste des produits.",
        allow_barge_in=False,
    ) == "accept"


class _Socket:
    def __init__(self):
        self.sent = []

    async def send_json(self, value):
        self.sent.append(value)


class _Adapter:
    def __init__(self):
        self.spoken = []

    async def speak(self, text):
        self.spoken.append(text)

    async def interrupt(self):
        pass

    async def clear_input(self):
        pass

    async def events(self):
        if False:
            yield None


@pytest.mark.asyncio
async def test_partial_transcript_does_not_drop_the_in_flight_answer():
    started = asyncio.Event()

    async def slow(_item, _text):
        started.set()
        await asyncio.sleep(0.05)
        return {"status": "success", "answer": "Voici les modules actifs."}

    adapter = _Adapter()
    bridge = TelnyxMediaBridge(
        _Socket(), adapter, locale="fr",
        validate_start=lambda *_a, **_k: _async_none(),
        authorize=lambda *_a, **_k: _async_none(),
        execute_turn=slow,
        allow_natural_interruptions=True,
    )

    async def events():
        yield SimpleNamespace(
            type="conversation.item.input_audio_transcription.completed",
            item_id="partial-turn",
            transcript="Quels modules sont accessibles à mon entreprise",
        )

    bridge.adapter.events = events
    task = asyncio.create_task(bridge._execute("turn-1", "Quels modules sont accessibles", 0))
    await started.wait()
    await bridge._provider_events()
    await task
    assert bridge.epoch == 0
    assert bridge.central_ai_discarded_epochs == 0
    assert adapter.spoken == ["Voici les modules actifs."]


async def _async_none(*_args, **_kwargs):
    return None


@pytest.mark.asyncio
async def test_complete_turn_sends_audible_telnyx_frames():
    """Test D without a phone call: text answer, PCM, PCMU frames on the socket."""
    socket = _Socket()
    pcm = encode_diagnostic_phrase()
    delta = base64.b64encode(
        # 20 ms of 24 kHz silence is not used; the diagnostic tone is the provider chunk.
        __import__("backend.app.voice.audio_diagnostics", fromlist=["diagnostic_pcm24"]).diagnostic_pcm24()
    ).decode("ascii")

    class Adapter(_Adapter):
        async def speak(self, text):
            await super().speak(text)
            await self._events.put(SimpleNamespace(type="response.created", response=SimpleNamespace(id="resp-d")))
            await self._events.put(SimpleNamespace(type="response.output_audio.delta", response_id="resp-d", delta=delta))
            await self._events.put(SimpleNamespace(
                type="response.done",
                response=SimpleNamespace(id="resp-d", status="completed", usage=None),
            ))

        def __init__(self):
            super().__init__()
            self._events = asyncio.Queue()

        async def events(self):
            while True:
                yield await self._events.get()

    adapter = Adapter()

    async def execute(_item, _text):
        return {"status": "success", "answer": "Le savon coûte 12 dollars."}

    bridge = TelnyxMediaBridge(
        socket, adapter, locale="fr",
        validate_start=_async_none, authorize=_async_none, execute_turn=execute,
    )
    writer = asyncio.create_task(bridge._write_audio())
    listener = asyncio.create_task(bridge._provider_events())
    await bridge._execute("turn-d", "Quel est le prix ?", 0)
    for _ in range(50):
        if any(item.get("event") == "media" for item in socket.sent):
            break
        await asyncio.sleep(0.02)
    media = [item for item in socket.sent if item.get("event") == "media"]
    assert adapter.spoken == ["Le savon coûte 12 dollars."]
    assert media
    payload = base64.b64decode(media[0]["media"]["payload"])
    assert len(payload) == 160
    assert bridge.telemetry["central_ai_response_ready"] == 1
    assert bridge.telemetry["tts_request_started"] == 1
    assert bridge.telemetry["tts_first_audio_chunk_received"] == 1
    assert bridge.telemetry["audio_encoding_completed"] >= 1
    assert bridge.telemetry["outbound_audio_frames_sent"] >= 1
    assert bridge.telemetry["outbound_audio_bytes_sent"] >= 160
    writer.cancel()
    listener.cancel()
    await asyncio.gather(writer, listener, return_exceptions=True)
    assert pcm["valid"] is True
