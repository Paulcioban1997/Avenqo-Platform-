import asyncio
from unittest.mock import AsyncMock

import pytest

from backend.app.voice.telnyx_media import TelnyxMediaBridge


def bridge(*, seconds=0.03, valid=True, open_error=None):
    class Socket:
        started = False

        async def receive_json(self):
            if not self.started:
                self.started = True
                return {"event": "start", "stream_id": "synthetic-stream", "start": {
                    "media_format": {"encoding": "PCMU", "sample_rate": 8000, "channels": 1}}}
            await asyncio.Event().wait()

    class Adapter:
        closed = False

        async def open(self, **kwargs):
            if open_error:
                raise open_error

        async def events(self):
            await asyncio.Event().wait()
            yield None

        async def close(self):
            self.closed = True

    async def validate(event):
        if not valid:
            raise PermissionError("Synthetic ticket denied")

    adapter = Adapter()
    hangup = AsyncMock()
    ledger = type("Ledger", (), {"settle_pending": lambda self: setattr(self, "settled", True)})()
    result = TelnyxMediaBridge(Socket(), adapter, locale="fr", validate_start=validate,
        authorize=AsyncMock(), execute_turn=AsyncMock(), hangup_call=hangup,
        usage_ledger=ledger, max_session_seconds=seconds)
    return result, adapter, hangup, ledger


@pytest.mark.asyncio
async def test_duration_stops_authorized_media_closes_audio_and_settles_usage():
    session, adapter, hangup, ledger = bridge()
    await asyncio.wait_for(session.run(), timeout=1)
    hangup.assert_awaited_once()
    assert adapter.closed and ledger.settled
    assert session.telemetry["final_state"] == "DURATION_LIMIT"
    await session.request_stop()
    hangup.assert_awaited_once()


@pytest.mark.asyncio
async def test_manual_stop_is_idempotent_and_finishes_media():
    session, adapter, hangup, ledger = bridge(seconds=90)
    running = asyncio.create_task(session.run())
    for _ in range(100):
        if session._background:
            break
        await asyncio.sleep(0)
    assert session._background
    await session.request_stop()
    await asyncio.wait_for(running, timeout=1)
    await session.request_stop()
    hangup.assert_awaited_once()
    assert adapter.closed and ledger.settled


@pytest.mark.asyncio
async def test_invalid_ticket_cannot_hang_up_another_call():
    session, adapter, hangup, ledger = bridge(valid=False)
    with pytest.raises(PermissionError):
        await session.run()
    await session.request_stop()
    hangup.assert_not_awaited()
    assert adapter.closed and ledger.settled


@pytest.mark.asyncio
async def test_provider_timeout_is_not_misreported_as_duration_limit():
    session, adapter, hangup, ledger = bridge(seconds=90, open_error=TimeoutError())
    with pytest.raises(TimeoutError):
        await session.run()
    assert session.telemetry["final_state"] != "DURATION_LIMIT"
    hangup.assert_not_awaited()
    assert adapter.closed and ledger.settled
