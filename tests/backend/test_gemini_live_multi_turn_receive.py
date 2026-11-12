"""Gemini Live SDK receive() is turn-scoped; the adapter must listen again.

A single audio greeting ends the first Gemini turn. Without a second call
to session.receive() the event producer closes and the Telnyx bridge exits.
"""
import asyncio
from types import SimpleNamespace

import pytest

from backend.app.config.settings import Settings
from backend.app.voice.realtime_provider import GeminiLiveRealtimeAudioAdapter


class FakeOneTurnReceiveSession:
    """SDK-like: each receive() call yields just one completed model turn."""

    def __init__(self) -> None:
        self.receive_calls = 0
        self.more = asyncio.Event()

    async def receive(self):
        self.receive_calls += 1
        n = self.receive_calls
        if n <= 2:
            yield SimpleNamespace(
                server_content=SimpleNamespace(
                    input_transcription=SimpleNamespace(
                        text=f"question {n}", finished=True
                    ),
                    turn_complete=True,
                    model_turn=None,
                    interrupted=False,
                ),
                usage_metadata=None,
            )
        else:
            await self.more.wait()
            if False:
                yield None


@pytest.mark.asyncio
async def test_gemini_live_receive_continues_across_two_turns():
    adapter = GeminiLiveRealtimeAudioAdapter(Settings(), company_name="Test Company")
    fake = FakeOneTurnReceiveSession()
    adapter._session = fake
    worker = asyncio.create_task(adapter._receive_loop())
    try:
        transcriptions = []
        async def collect():
            while len(transcriptions) < 2:
                event = await adapter._event_queue.get()
                if getattr(event, "type", "") == "conversation.item.input_audio_transcription.completed":
                    transcriptions.append(event.transcript)
        await asyncio.wait_for(collect(), timeout=2.0)
        assert transcriptions == ["question 1", "question 2"]
        assert fake.receive_calls >= 2
        assert not worker.done(), "A completed model turn must not end the websocket receive worker"
    finally:
        worker.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker


@pytest.mark.asyncio
async def test_gemini_live_empty_receive_stream_does_not_spin():
    class EmptySession:
        def __init__(self):
            self.calls = 0

        async def receive(self):
            self.calls += 1
            if False:
                yield None

    adapter = GeminiLiveRealtimeAudioAdapter(Settings(), company_name="Test Company")
    fake = EmptySession()
    adapter._session = fake
    await adapter._receive_loop()
    assert fake.calls == 1
    event = await adapter._event_queue.get()
    assert event.type == "error"
    assert event.error.code == "gemini_live_stream_error"
