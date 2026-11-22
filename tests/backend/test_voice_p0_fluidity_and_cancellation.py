import asyncio
import time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config.settings import Settings
from backend.app.models.base import Base
from backend.app.models.company import Company
from backend.app.models.company_module import CompanyModule, CompanyModuleStatus
from backend.app.models.module import Module
from backend.app.models.voice import VoiceBusinessConfig, VoiceCall
from backend.app.voice.direct_answers import (
    is_business_contact_question,
    is_business_hours_question,
    is_business_location_question,
    is_services_overview_question,
    resolve_direct_voice_answer,
)
from backend.app.voice.telnyx_media import TelnyxMediaBridge
from backend.app.voice.turn_control import (
    adjudicate_transcript,
    is_backchannel,
    is_explicit_interruption,
    is_playback_echo,
    is_substantive_utterance,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


class MockStreamingAdapter:
    def __init__(self, events_queue: asyncio.Queue):
        self._events_queue = events_queue
        self.spoken_texts = []
        self.interrupted_count = 0

    async def speak(self, text):
        self.spoken_texts.append(text)

    async def interrupt(self):
        self.interrupted_count += 1

    async def clear_input(self):
        pass

    async def events(self):
        while True:
            ev = await self._events_queue.get()
            if ev is None:
                break
            yield ev


def _make_test_company_and_call(db_session: Session):
    uid = uuid4().hex[:8]
    company = Company(
        id=uuid4(),
        name="Ski Shop Mont-Tremblant",
        slug=f"ski-shop-{uid}",
        email=f"contact-{uid}@skishop.example.com",
        country="CA",
        timezone="America/Toronto",
        industry="retail",
        subscription_plan="enterprise",
        website="https://skishop-tremblant.example.com",
    )
    db_session.add(company)
    mod_voice = Module(id=uuid4(), name="Voice AI", code="voice", is_active=True)
    db_session.add(mod_voice)
    db_session.flush()

    from datetime import datetime, timezone
    cm = CompanyModule(
        company_id=company.id,
        module_id=mod_voice.id,
        status=CompanyModuleStatus.ACTIVE,
        activated_at=datetime.now(timezone.utc),
    )
    db_session.add(cm)

    voice_config = VoiceBusinessConfig(
        id=uuid4(),
        company_id=company.id,
        business_name="Ski Shop Mont-Tremblant",
        preferred_language="fr-CA",
        opening_hours={"monday": "9h à 18h", "tuesday": "9h à 18h", "wednesday": "9h à 18h"},
        services=[{"name": "Location de skis", "price": 45, "currency": "CAD", "duration_minutes": 60}],
        call_policy={
            "business_address": "1000 Chemin des Voyageurs, Mont-Tremblant, QC",
            "website": "https://skishop-tremblant.example.com",
        },
        greeting_message="Bonjour et bienvenue chez Ski Shop Mont-Tremblant !",
        voice_api_key_hash=f"hash_{uid}",
        voice_api_key_last4="1234",
        enabled=True,
    )
    db_session.add(voice_config)

    call = VoiceCall(
        id=uuid4(),
        company_id=company.id,
        config_id=voice_config.id,
        telnyx_call_control_id=f"v-call-{uid}",
        caller_phone="+15145551234",
        status="in_progress",
    )
    db_session.add(call)
    db_session.commit()
    return company, voice_config, call


# =====================================================================
# 1. Double Cancellation Idempotence & Queue Protection
# =====================================================================

@pytest.mark.asyncio
async def test_double_cancellation_idempotence():
    """Verify that response.interrupted followed by response.done(status='cancelled')
    for the exact same response_id calls interrupt() only once and bumps epoch only once."""
    events_queue: asyncio.Queue = asyncio.Queue()
    adapter = MockStreamingAdapter(events_queue)
    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=AsyncMock(),
    )
    bridge.stream_id = "test-stream-1"
    bridge.epoch = 1
    resp_id = "resp-item-999"
    bridge.response_id = resp_id
    bridge.response_epoch = 1
    bridge._responses[resp_id] = ("item-1", 1, None)

    drain_task = asyncio.create_task(bridge._drain_provider_events())

    # Step 1: Provider emits response.interrupted
    await events_queue.put(SimpleNamespace(type="response.interrupted", response_id=resp_id))
    await asyncio.sleep(0.05)

    assert resp_id in bridge._cancelled_responses
    epoch_after_first_cancel = bridge.epoch
    assert epoch_after_first_cancel == 2
    assert mock_socket.send_json.await_count == 1
    mock_socket.send_json.assert_awaited_with({"event": "clear"})

    # Step 2: Provider emits response.done(status='cancelled') for SAME resp_id
    resp_done_obj = SimpleNamespace(id=resp_id, status="cancelled")
    await events_queue.put(SimpleNamespace(type="response.done", response=resp_done_obj))
    await asyncio.sleep(0.05)

    # Epoch must NOT be bumped again, and socket.send_json({"event": "clear"}) must NOT be sent again
    assert bridge.epoch == epoch_after_first_cancel
    assert mock_socket.send_json.await_count == 1, "Duplicate clear must NOT be sent to Telnyx!"

    # Clean up
    await events_queue.put(None)
    await drain_task


@pytest.mark.asyncio
async def test_queue_protection_never_drops_new_question_on_cancellation():
    """Verify that when a caller barge-in queues a valid new question in _turns,
    a subsequent provider cancellation event NEVER purges that turn from the queue."""
    events_queue: asyncio.Queue = asyncio.Queue()
    adapter = MockStreamingAdapter(events_queue)
    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=AsyncMock(),
    )
    bridge.stream_id = "test-stream-q"
    bridge.epoch = 5

    # New validated question placed in queue with current epoch 5
    new_turn = ("item-new-question", "Combien coûte le fartage de skis ?", 5)
    bridge._turns.put_nowait(new_turn)

    assert bridge._turns.qsize() == 1

    # An old response cancellation arrives from an earlier epoch (epoch 4)
    await bridge.interrupt(originating_response_id="old-resp-4", reason="old_cancel")

    # The new turn with epoch updated to bridge.epoch MUST still be present in the queue!
    assert bridge._turns.qsize() == 1
    queued_item = bridge._turns.get_nowait()
    assert queued_item[0] == "item-new-question"
    assert queued_item[1] == "Combien coûte le fartage de skis ?"
    assert queued_item[2] == bridge.epoch


# =====================================================================
# 2. Turn Control Adjudication: Barge-in vs Backchannels vs Echo
# =====================================================================

def test_speech_adjudication_filters_synthetic_echo():
    """Verify that acoustic echo from the synthetic voice is detected and ignored."""
    last_spoken = "Nous sommes ouverts du lundi au vendredi de 9 heures à 18 heures."
    
    # Near exact or normalized substring echo
    assert is_playback_echo("du lundi au vendredi de 9 heures", last_spoken) is True
    assert is_playback_echo("ouverts du lundi au vendredi", last_spoken) is True
    
    # Adjudication during PLAYING returns 'ignore'
    decision = adjudicate_transcript(
        "ouverts du lundi au vendredi",
        phase="PLAYING",
        in_flight_transcript="",
        last_spoken=last_spoken,
        allow_barge_in=True,
    )
    assert decision == "ignore"


def test_speech_adjudication_filters_backchannels():
    """Verify that short affirmations or hesitations do not interrupt speaking or thinking."""
    assert is_backchannel("d'accord") is True
    assert is_backchannel("oui") is True
    assert is_backchannel("merci") is True
    assert is_backchannel("euh") is True
    assert is_backchannel("parfait") is True
    assert is_backchannel("super") is True
    assert is_backchannel("got it") is True

    # During PLAYING, backchannels are ignored
    assert adjudicate_transcript("d'accord", phase="PLAYING") == "ignore"
    assert adjudicate_transcript("oui", phase="PLAYING") == "ignore"
    assert adjudicate_transcript("merci", phase="PLAYING") == "ignore"

    # During THINKING, backchannels are ignored (protects Central AI in-flight)
    assert adjudicate_transcript("euh", phase="THINKING") == "ignore"
    assert adjudicate_transcript("oui", phase="THINKING") == "ignore"


def test_speech_adjudication_detects_explicit_interruption():
    """Verify that explicit stop/wait words trigger replace across phases."""
    assert is_explicit_interruption("attends") is True
    assert is_explicit_interruption("stop") is True
    assert is_explicit_interruption("attendez s'il vous plaît") is True
    assert is_explicit_interruption("j'ai une autre question") is True

    assert adjudicate_transcript("attends une seconde", phase="PLAYING") == "replace"
    assert adjudicate_transcript("stop s'il te plaît", phase="PLAYING") == "replace"
    assert adjudicate_transcript("attends", phase="THINKING") == "replace"


def test_speech_adjudication_substantive_questions():
    """Verify that substantive new queries trigger replace during PLAYING and THINKING."""
    query = "Quels sont vos tarifs pour la location de skis ?"
    assert is_substantive_utterance(query) is True

    assert adjudicate_transcript(query, phase="PLAYING", allow_barge_in=True) == "replace"
    assert adjudicate_transcript(query, phase="THINKING", allow_barge_in=True) == "replace"

    # Non-substantive short noise during THINKING is ignored
    assert adjudicate_transcript("ah", phase="THINKING") == "ignore"
    assert adjudicate_transcript("hum", phase="THINKING") == "ignore"


# =====================================================================
# 3. Non-Blocking Asynchronous Turn Cancellation
# =====================================================================

@pytest.mark.asyncio
async def test_slow_turn_cancelled_immediately_without_blocking_subsequent_turn():
    """Verify that a slow 10-second Central AI turn is cancelled cooperatively
    when a new turn arrives, allowing the new turn to run immediately without delay."""
    executed_turns = []
    first_turn_cancelled = False

    async def mock_execute_turn(item_id, transcript):
        nonlocal first_turn_cancelled
        if item_id == "slow-turn-1":
            try:
                await asyncio.sleep(10.0)
                executed_turns.append(item_id)
                return {"status": "success", "answer": "Analyse longue terminée."}
            except asyncio.CancelledError:
                first_turn_cancelled = True
                raise
        else:
            await asyncio.sleep(0.01)
            executed_turns.append(item_id)
            return {"status": "success", "answer": "Horaires 9h à 18h."}

    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()
    events_queue: asyncio.Queue = asyncio.Queue()
    adapter = MockStreamingAdapter(events_queue)

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=mock_execute_turn,
    )
    bridge.stream_id = "test-stream-async"
    bridge.epoch = 1

    # Start turn execution consumer
    turns_task = asyncio.create_task(bridge._execute_turns())

    # Put slow turn into queue with epoch 1
    bridge._turns.put_nowait(("slow-turn-1", "Donnez-moi une longue analyse", 1))
    await asyncio.sleep(0.05)

    # Slow turn should now be executing in bridge._current_turn_task
    assert bridge._current_turn_task is not None
    assert not bridge._current_turn_task.done()

    # New turn arrives! Caller interrupts
    bridge.epoch = 2
    if bridge._current_turn_task and not bridge._current_turn_task.done():
        bridge._current_turn_task.cancel()
    bridge._turns.put_nowait(("fast-turn-2", "Quels sont vos horaires ?", 2))

    # Wait shortly for processing
    await asyncio.sleep(0.1)

    # Verify first turn was cancelled and fast turn executed
    assert first_turn_cancelled is True
    assert "fast-turn-2" in executed_turns
    assert "slow-turn-1" not in executed_turns

    # Clean up
    turns_task.cancel()


# =====================================================================
# 4. Fast-Path Direct Answers (< 100ms)
# =====================================================================

def test_fast_path_direct_answers_sub_100ms(db_session: Session):
    """Verify that common business queries resolve directly from DB in < 100ms."""
    company, voice_config, call = _make_test_company_and_call(db_session)

    # 1. Opening hours
    t0 = time.perf_counter()
    res_hours = resolve_direct_voice_answer(
        db_session,
        company_id=company.id,
        transcript="Quels sont vos horaires d'ouverture ?",
        authenticated_staff=False,
        locale="fr-CA",
        call=call,
    )
    elapsed_hours_ms = (time.perf_counter() - t0) * 1000
    assert res_hours is not None
    assert "9h à 18h" in res_hours
    assert elapsed_hours_ms < 100, f"Hours fast-path took {elapsed_hours_ms}ms, target < 100ms"

    # 2. Location / Address
    t0 = time.perf_counter()
    res_loc = resolve_direct_voice_answer(
        db_session,
        company_id=company.id,
        transcript="Où êtes-vous situés ? Quelle est votre adresse ?",
        authenticated_staff=False,
        locale="fr-CA",
        call=call,
    )
    elapsed_loc_ms = (time.perf_counter() - t0) * 1000
    assert res_loc is not None
    assert "1000 Chemin des Voyageurs" in res_loc
    assert elapsed_loc_ms < 100, f"Location fast-path took {elapsed_loc_ms}ms, target < 100ms"

    # 3. Services overview
    t0 = time.perf_counter()
    res_serv = resolve_direct_voice_answer(
        db_session,
        company_id=company.id,
        transcript="Quels sont vos services ?",
        authenticated_staff=False,
        locale="fr-CA",
        call=call,
    )
    elapsed_serv_ms = (time.perf_counter() - t0) * 1000
    assert res_serv is not None
    assert "Location de skis" in res_serv
    assert elapsed_serv_ms < 100, f"Services fast-path took {elapsed_serv_ms}ms, target < 100ms"

    # 4. Contact / Website
    t0 = time.perf_counter()
    res_contact = resolve_direct_voice_answer(
        db_session,
        company_id=company.id,
        transcript="Quel est votre site internet ou courriel ?",
        authenticated_staff=False,
        locale="fr-CA",
        call=call,
    )
    elapsed_contact_ms = (time.perf_counter() - t0) * 1000
    assert res_contact is not None
    assert "skishop-tremblant.example.com" in res_contact
    assert elapsed_contact_ms < 100, f"Contact fast-path took {elapsed_contact_ms}ms, target < 100ms"


# =====================================================================
# 5. True Latency Instrumentation & Telemetry
# =====================================================================

@pytest.mark.asyncio
async def test_turn_metrics_and_first_audible_latency_fallback():
    """Verify that get_turn_metrics returns all required fields and first_audible_response_latency_ms
    falls back cleanly to _last_transcription_at when speech_stopped event was omitted."""
    events_queue: asyncio.Queue = asyncio.Queue()
    adapter = MockStreamingAdapter(events_queue)
    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=AsyncMock(),
    )
    bridge.stream_id = "test-stream-metrics"
    drain_task = asyncio.create_task(bridge._drain_provider_events())

    # Step 1: Input transcription completed (NO speech_stopped event sent by carrier)
    transcription_event = SimpleNamespace(
        type="conversation.item.input_audio_transcription.completed",
        item_id="item-metric-1",
        transcript="Bonjour quelle est votre adresse ?",
    )
    await events_queue.put(transcription_event)
    await asyncio.sleep(0.02)

    metrics = bridge.get_turn_metrics("item-metric-1")
    assert metrics is not None
    assert metrics["transcript_final_at"] is not None
    assert bridge._last_transcription_at is not None

    # Step 2: Response created
    bridge.response_id = "resp-metric-1"
    bridge.response_epoch = bridge.epoch
    bridge._responses["resp-metric-1"] = ("item-metric-1", bridge.epoch, None)

    import base64
    # Step 3: Audio delta arrives
    delta_event = SimpleNamespace(
        type="response.output_audio.delta",
        response_id="resp-metric-1",
        delta=base64.b64encode(b"\x00" * 320).decode("utf-8"),
    )
    await events_queue.put(delta_event)
    await asyncio.sleep(0.02)

    # Telemetry first_audible_response_latency_ms MUST be computed using _last_transcription_at
    assert bridge.telemetry["first_audible_response_latency_ms"] > 0
    metrics_after_audio = bridge.get_turn_metrics("item-metric-1")
    assert metrics_after_audio["first_pcm_sent_at"] is not None

    # Step 4: Response done
    done_event = SimpleNamespace(
        type="response.done",
        response=SimpleNamespace(id="resp-metric-1", status="completed"),
    )
    await events_queue.put(done_event)
    await asyncio.sleep(0.02)

    metrics_after_done = bridge.get_turn_metrics("item-metric-1")
    assert metrics_after_done["playback_completed_at"] is not None

    # Clean up
    await events_queue.put(None)
    await drain_task


# =====================================================================
# 6. Robustness: 20 Consecutive Questions
# =====================================================================

@pytest.mark.asyncio
async def test_twenty_consecutive_questions_no_silent_drops():
    """Verify that a sequence of 20 consecutive questions produces 20 executed responses
    without dropping any items or deadlock."""
    executed = []

    async def mock_execute(item_id, transcript):
        await asyncio.sleep(0.005)
        executed.append((item_id, transcript))
        return {"status": "success", "answer": f"Réponse à {transcript}"}

    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()
    events_queue: asyncio.Queue = asyncio.Queue()
    adapter = MockStreamingAdapter(events_queue)

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=mock_execute,
    )
    bridge.stream_id = "test-stream-20"

    turns_task = asyncio.create_task(bridge._execute_turns())

    # Feed 20 questions sequentially as consumer processes them
    async def feeder():
        for i in range(1, 21):
            await bridge._turns.put((f"item-{i}", f"Question {i}", bridge.epoch))

    feed_task = asyncio.create_task(feeder())

    # Give enough time for all 20 to complete
    timeout = 4.0
    start_t = time.monotonic()
    while len(executed) < 20 and (time.monotonic() - start_t) < timeout:
        await asyncio.sleep(0.05)

    await feed_task
    assert len(executed) == 20, f"Expected 20 executed turns, got {len(executed)}"
    assert executed[0][0] == "item-1"
    assert executed[19][0] == "item-20"

    turns_task.cancel()
