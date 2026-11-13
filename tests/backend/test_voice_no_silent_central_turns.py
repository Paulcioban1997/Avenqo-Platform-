"""Regression: a recognized caller must not get silent Central AI or VAD cancellation.

No PIN, transcripts, audio blobs, or tenant data are written to runtime logs.
"""
import asyncio
from types import SimpleNamespace

import pytest

from backend.app.voice.telnyx_media import TelnyxMediaBridge


class FakeAdapter:
    def __init__(self):
        self.spoken = []
        self.was_interrupted = False

    async def speak(self, text):
        self.spoken.append(text)

    async def interrupt(self):
        self.was_interrupted = True

    async def clear_input(self):
        pass

    async def events(self):
        yield SimpleNamespace(type="input_audio_buffer.speech_started", item_id="turn-2")


async def noop(*_args, **_kwargs):
    return None


class FakeSocket:
    def __init__(self):
        self.sent = []

    async def send_json(self, value):
        self.sent.append(value)


def make_bridge(execute, adapter=None):
    adapter = adapter or FakeAdapter()
    bridge = TelnyxMediaBridge(
        socket=FakeSocket(), adapter=adapter, locale="fr",
        validate_start=noop, authorize=noop, execute_turn=execute,
        allow_natural_interruptions=True,
    )
    return bridge, adapter


@pytest.mark.asyncio
async def test_slow_central_ai_has_audible_timeout_instead_of_silence():
    async def slow(_item, _text):
        await asyncio.sleep(0.3)
        return {"status": "success", "answer": "unreachable"}

    bridge, adapter = make_bridge(slow)
    bridge.central_ai_timeout = 0.02
    await bridge._execute("timeout-case", "question", 0)
    assert bridge.central_ai_timeouts == 1
    assert bridge.central_ai_replies_queued == 1
    assert any("trop de temps" in t for t in adapter.spoken)


@pytest.mark.asyncio
async def test_central_ai_non_success_status_is_explained_not_silent():
    async def unavailable(_item, _text):
        return {"status": "error", "answer": "private backend error"}

    bridge, adapter = make_bridge(unavailable)
    await bridge._execute("error-case", "question", 0)
    assert bridge.central_ai_missing_answers == 1
    assert len(adapter.spoken) == 1
    assert "private backend error" not in adapter.spoken[0]
    assert "Je n'ai pas pu" in adapter.spoken[0]


@pytest.mark.asyncio
async def test_vad_during_central_thinking_does_not_discard_valid_answer():
    started = asyncio.Event()

    async def slow(_item, _text):
        started.set()
        await asyncio.sleep(0.05)
        return {"status": "success", "answer": "Voici votre réponse."}

    bridge, adapter = make_bridge(slow)
    assert bridge.pending_epoch is None
    assert bridge.response_id is None
    assert bridge._output.empty()
    task = asyncio.create_task(bridge._execute("turn-1", "question", bridge.epoch))
    await started.wait()
    await bridge._provider_events()
    assert bridge.epoch == 0
    assert not adapter.was_interrupted
    await task
    assert adapter.spoken == ["Voici votre réponse."]
    assert bridge.central_ai_replies_queued == 1


@pytest.mark.asyncio
async def test_vad_during_playback_does_not_cancel_audio():
    bridge, adapter = make_bridge(noop)
    bridge.pending_epoch = bridge.epoch
    bridge.response_id = "playing"
    bridge.phase = "PLAYING"
    await bridge._provider_events()
    assert bridge.epoch == 0
    assert not adapter.was_interrupted


@pytest.mark.asyncio
async def test_confirmed_transcript_can_barge_in_during_playback():
    class SpeakingAdapter(FakeAdapter):
        async def events(self):
            yield SimpleNamespace(
                type="conversation.item.input_audio_transcription.completed",
                item_id="barge-turn",
                transcript="Je voudrais poser une autre question maintenant",
            )

    bridge, adapter = make_bridge(noop, SpeakingAdapter())
    bridge.pending_epoch = bridge.epoch
    bridge.response_id = "playing"
    bridge.phase = "PLAYING"
    bridge._last_spoken = "Voici la reponse en cours de lecture pour le client."
    await bridge._provider_events()
    assert bridge.epoch == 1
    assert adapter.was_interrupted


@pytest.mark.asyncio
async def test_staff_pin_gate_still_never_bypassed_for_auth_required():
    async def challenge(_item, _text):
        return {"auth_required": True}

    bridge, adapter = make_bridge(challenge)
    with pytest.raises(PermissionError, match="Keypad authentication unavailable"):
        await bridge._execute("auth-case", "details privés", 0)
    assert adapter.spoken == []
