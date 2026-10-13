"""Bounded Realtime renewal at quiet boundaries; never replay ambiguous audio.

The audio adapter has no tools or business conversation memory. The existing
tenant-owned Central conversation survives in the caller, outside this socket.
Renewal can cause an audible gap; a mid-turn disconnect terminates safely.
"""
import asyncio
import copy
import time


class RotatingRealtimeAdapter:
    provider_id = "openai"

    def __init__(self, factory, authorize, *, rotation_seconds=3000, clock=time.monotonic):
        if not 1 <= rotation_seconds <= 3300:
            raise ValueError("Renewal must precede the provider session limit")
        self.factory, self.authorize = factory, authorize
        self.rotation_seconds, self.clock = rotation_seconds, clock
        self.adapter = None
        self.generation = 0
        self.opened_at = 0
        self.locale = None
        self.speech_pending = self.response_pending = False
        self.closed = False
        self.lock = asyncio.Lock()
        self.queue = asyncio.Queue(maxsize=256)
        self.pump = self.timer = None

    async def open(self, *, locale):
        self.locale = locale
        async with self.lock:
            await self._connect()
        self.timer = asyncio.create_task(self._watch())

    async def _connect(self):
        await self.authorize()
        candidate = self.factory()
        try:
            await asyncio.wait_for(candidate.open(locale=self.locale), 10)
        except BaseException:
            await asyncio.wait_for(candidate.close(), 5)
            raise
        self.adapter = candidate
        self.generation += 1
        self.opened_at = self.clock()
        self.pump = asyncio.create_task(self._events(candidate, self.generation))

    async def _events(self, adapter, generation):
        try:
            async for original in adapter.events():
                if generation != self.generation or self.closed:
                    return
                event = copy.deepcopy(original)
                kind = getattr(event, "type", "")
                if kind == "input_audio_buffer.speech_started":
                    self.speech_pending = True
                if kind in {"conversation.item.input_audio_transcription.completed", "conversation.item.input_audio_transcription.failed"}:
                    self.speech_pending = False
                if kind == "response.done":
                    self.response_pending = False
                # Provider IDs may repeat after reconnection. Namespace all usage and response links.
                for field in ("item_id", "response_id", "event_id"):
                    value = getattr(event, field, None)
                    if isinstance(value, str):
                        setattr(event, field, f"r{generation}:{value}")
                response = getattr(event, "response", None)
                if response is not None and isinstance(getattr(response, "id", None), str):
                    response.id = f"r{generation}:{response.id}"
                await self.queue.put(event)
            if not self.closed and generation == self.generation:
                await self.queue.put(ConnectionError("Realtime session ended; no ambiguous turn replayed"))
        except asyncio.CancelledError:
            raise
        except Exception:
            await self.queue.put(ConnectionError("Realtime transport disconnected; no ambiguous turn replayed"))

    async def renew_if_due(self):
        async with self.lock:
            if self.closed or self.clock() - self.opened_at < self.rotation_seconds:
                return False
            if self.speech_pending or self.response_pending:
                # Wait for a quiet boundary; never cut a response and replay its tool effects.
                if self.clock() - self.opened_at >= 3500:
                    raise TimeoutError("No safe renewal boundary before provider expiry")
                return False
            await self.authorize()
            self.pump.cancel()
            await asyncio.gather(self.pump, return_exceptions=True)
            await asyncio.wait_for(self.adapter.close(), 5)
            for attempt in range(3):
                try:
                    await self._connect()
                    return True
                except PermissionError:
                    raise
                except Exception:
                    if attempt == 2:
                        raise ConnectionError("Realtime renewal failed after bounded retries") from None
                    await asyncio.sleep(0.25 * 2 ** attempt)

    async def _watch(self):
        try:
            while not self.closed:
                await asyncio.sleep(0.5)
                await self.renew_if_due()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Safe exception class only; no provider bodies or keys in diagnostics.
            await self.queue.put(RuntimeError("Realtime renewal stopped: " + type(exc).__name__))

    async def send_audio(self, audio):
        async with self.lock:
            await asyncio.wait_for(self.adapter.send_audio(audio), 5)

    async def speak(self, text):
        async with self.lock:
            await self.authorize()
            self.response_pending = True
            await asyncio.wait_for(self.adapter.speak(text), 5)

    async def interrupt(self):
        async with self.lock:
            await asyncio.wait_for(self.adapter.interrupt(), 5)

    async def clear_input(self):
        async with self.lock:
            await asyncio.wait_for(self.adapter.clear_input(), 5)
            self.speech_pending = False

    async def events(self):
        while not self.closed:
            event = await self.queue.get()
            if isinstance(event, Exception):
                raise event
            yield event

    async def close(self):
        self.closed = True
        tasks = [task for task in (self.timer, self.pump) if task is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self.adapter is not None:
            await asyncio.wait_for(self.adapter.close(), 5)
