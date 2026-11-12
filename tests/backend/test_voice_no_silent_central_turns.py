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


def make_bridge(execute, adapter=None):
    adapter = adapter or FakeAdapter()
    bridge = TelnyxMediaBridge(
        socket=None, adapter=adapter, locale="fr",
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
    async def quick(_item, _text):
        return {"status": "success", "answer": "Voici votre réponse."}

    bridge, adapter = make_bridge(quick)
    assert bridge.pending_epoch is None
    assert bridge.response_id is None
    assert bridge._output.empty()
    await bridge._provider_events()
    assert bridge.epoch == 0
    assert not adapter.was_interrupted
    await bridge._execute("turn-1", "question", 0)
    assert adapter.spoken == ["Voici votre réponse."]
    assert bridge.central_ai_replies_queued == 1


@pytest.mark.asyncio
async def test_staff_pin_gate_still_never_bypassed_for_auth_required():
    async def challenge(_item, _text):
        return {"auth_required": True}

    bridge, adapter = make_bridge(challenge)
    with pytest.raises(PermissionError, match="Keypad authentication unavailable"):
        await bridge._execute("auth-case", "details privés", 0)
    assert adapter.spoken == []
