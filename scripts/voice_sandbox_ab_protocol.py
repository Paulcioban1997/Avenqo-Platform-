"""Executable Sandbox A/B State-Machine Protocol (Issue #132 / PR #133).

IMPORTANT TRANSPARENCY NOTE:
- `--mode deterministic` runs an IN-MEMORY SIMULATED protocol (in-memory WebSocket + local event queues,
  0 network RTT, 0 live OpenAI/Gemini/Telnyx media servers). It validates state-machine turn completion,
  causal interruption gating, and pre-PIN barriers — NOT real telephone network latency or acoustic quality.
- `--mode live-api` probes live OpenAI/Gemini API model & tool-calling availability when keys are configured.

Usage:
    python scripts/voice_sandbox_ab_protocol.py --mode deterministic
    python scripts/voice_sandbox_ab_protocol.py --mode live-api
"""

from __future__ import annotations

import argparse
import asyncio
import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import random
import struct
import sys
import time
from types import SimpleNamespace
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.app.voice.adapters import OpenAIAudioConfig
from backend.app.voice.modular_pipeline_adapter import ModularVoicePipelineAdapter
from backend.app.voice.realtime_provider import GeminiLiveRealtimeAudioAdapter, NaturalInterruptionManager
from backend.app.voice.s2s_realtime_adapter import OpenAISpeechToSpeechRealtimeAdapter
from backend.app.voice.telnyx_media import TelnyxMediaBridge


SINGLE_CALL_20_QUESTIONS: tuple[tuple[str, str], ...] = (
    ("identite", "Qui suis-je et quel est mon rôle dans cette entreprise ?"),
    ("modules", "Quels modules Avenqo sont activés pour mon entreprise ?"),
    ("catalogue_stock", "Quels snowboards avons-nous vraiment en stock avec leur prix ?"),
    ("marge_exec", "Quels produits offrent la meilleure marge bénéficiaire ?"),
    ("strategie_2027", "Donne-moi trois stratégies concrètes pour 2027 et 2028."),
    ("suivi_implicite", "Développe uniquement la deuxième stratégie s'il te plaît."),
    ("robotique", "Comment la robotique d'entrepôt peut-elle réduire nos coûts logistiques ?"),
    ("hors_sujet", "Question inattendue : pourquoi le ciel est-il bleu au niveau physique ?"),
    ("objection_pivot", "Non, c'est pas de ça que je parlais, montre-moi les casques."),
    ("promo", "Quels articles devrions-nous promouvoir cette semaine ?"),
    ("crm_rdv", "Comment réserver un rendez-vous conseil pour un client VIP ?"),
    ("blocage_reserve", "Peux-tu réserver un snowboard au téléphone pour un client ?"),
    ("marketing", "Propose une campagne d'acquisition client pour le mois prochain."),
    ("tresorerie", "Comment suivre nos factures et marges dans Accounting AI ?"),
    ("equipe_hr", "Comment l'assistant aide-t-il un employé pendant son quart de travail ?"),
    ("langue_en", "Can you confirm our return and shipping guidance in English?"),
    ("retour_fr", "Revenons en français : quel produit a le meilleur prix comparatif ?"),
    ("securite_nip", "Comment fonctionne la sécurité par NIP lors d'un transfert d'employé ?"),
    ("ia_memoire", "Est-ce que tu retiens le contexte de notre conversation depuis le début ?"),
    ("synthese", "Résume en deux phrases la priorité numéro un pour Produits Ero."),
)

TEN_INTERRUPTIONS: tuple[str, ...] = (
    "Attends une seconde, changeons de sujet.",
    "Non pas celui-là, je voulais parler du casque bleu.",
    "Stop, j'ai une autre question sur le stock.",
    "Excuse-moi de te couper, donne-moi juste le total.",
    "Allô, tu m'entends ? Vérifie plutôt les marges.",
    "Pause un instant, c'est noté, question suivante.",
    "Attendez, ne parle pas de l'ancien prix.",
    "Stop s'il te plaît, passe au point suivant.",
    "Non c'est pas ça, vérifie plutôt les modules actifs.",
    "Attends, résume en une seule phrase.",
)


@dataclass
class ProtocolResult:
    execution_mode: str
    architecture: str
    model_stack: str
    questions_asked: int
    barge_in_followups: int
    audible_answers: int
    lost_turns: int
    interruptions_sent: int
    interruptions_handled: int
    unconfirmed_suppressed: int
    estimated_cost_usd: str
    simulated_local_ms_per_turn: float

    @property
    def avg_first_audio_ms(self) -> float:
        return self.simulated_local_ms_per_turn


def _pcm_24k_sample(frames: int = 3) -> bytes:
    samples = 480 * frames
    return struct.pack("<" + "h" * samples, *([1100, -1100] * (samples // 2)))


async def _wait_turn_settled(bridge: TelnyxMediaBridge, expected_completed: int | None = None, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        done_ok = True if expected_completed is None else bridge.telemetry["voice_response_completed"] >= expected_completed
        if (
            done_ok
            and not bridge._executing_turn
            and bridge.response_id is None
            and bridge.pending_epoch is None
            and not bridge._playback_active
            and bridge._output.empty()
            and bridge._turns.empty()
        ):
            return
        await asyncio.sleep(0.01)


async def _wait_playback_active(bridge: TelnyxMediaBridge, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if bridge.response_id is not None or not bridge._output.empty():
            return
        await asyncio.sleep(0.005)


async def _noop_validate(_s: dict[str, Any]) -> None:
    return None


async def _noop_auth() -> None:
    return None


async def _noop_exec(_i: str, _t: str) -> dict[str, Any]:
    return {"status": "success", "answer": "ok"}


async def run_deterministic_ab_benchmark(seed: int = 132) -> list[ProtocolResult]:
    """Run all 20 shuffled questions + 10 verified interruptions in ONE simulated call per architecture."""
    rng = random.Random(seed)
    questions = list(SINGLE_CALL_20_QUESTIONS)
    rng.shuffle(questions)
    interrupt_indices = set(rng.sample(range(len(questions)), 10))
    pcm_24k_sample = _pcm_24k_sample(frames=4)

    class _MemSocket:
        def __init__(self) -> None:
            self.inbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
            self.outbound: list[dict[str, Any]] = []
            self.stream_id: str | None = None

        async def receive_json(self) -> dict[str, Any]:
            msg = await self.inbound.get()
            if isinstance(msg, dict) and msg.get("event") == "start":
                self.stream_id = msg.get("stream_id")
            return msg

        async def send_json(self, payload: dict[str, Any]) -> None:
            self.outbound.append(payload)
            if isinstance(payload, dict) and payload.get("event") == "mark" and self.stream_id:
                await self.inbound.put({"event": "mark", "stream_id": self.stream_id, "mark": payload.get("mark")})

    results: list[ProtocolResult] = []

    # 1) Architecture A: gpt-realtime-2.1 native S2S + create_response=False pre-response gate + secure tools
    class _FakeS2SConn:
        def __init__(self) -> None:
            self.sent: list[dict[str, Any]] = []
            self.q: asyncio.Queue[Any] = asyncio.Queue()
            self._idx = 0
            self._fc_idx = 0
            self.slow_next = False
            self._pending_query = ""

        async def send(self, payload: dict[str, Any]) -> None:
            self.sent.append(payload)
            ptype = payload.get("type")
            if ptype == "response.create" and payload.get("response", {}).get("input"):
                self._idx += 1
                rid = f"s2s-sec-{self._idx}"
                await self.q.put({"type": "response.created", "response": {"id": rid}})
                await self.q.put({"type": "response.audio.delta", "response_id": rid, "delta": base64.b64encode(pcm_24k_sample).decode("ascii")})
                await self.q.put({"type": "response.done", "response": {"id": rid, "status": "completed"}})
            elif ptype == "response.create":
                # Triggered ONLY after adapter authorized the turn (`create_response=False`)
                if self._pending_query:
                    q_now = self._pending_query
                    self._pending_query = ""
                    self._fc_idx += 1
                    await self.q.put({
                        "type": "response.function_call_arguments.done",
                        "call_id": f"fc-{self._fc_idx}",
                        "name": "search_products",
                        "arguments": json.dumps({"query": q_now[:24]}),
                    })
                else:
                    self._idx += 1
                    rid = f"s2s-r-{self._idx}"
                    await self.q.put({"type": "response.created", "response": {"id": rid}})
                    await self.q.put({"type": "response.audio.delta", "response_id": rid, "delta": base64.b64encode(pcm_24k_sample).decode("ascii")})
                    await self.q.put({"type": "response.audio_transcript.done", "transcript": f"Réponse outil S2S #{self._idx}"})
                    if self.slow_next:
                        self.slow_next = False
                        await asyncio.sleep(0.06)
                        return
                    await self.q.put({
                        "type": "response.done",
                        "response": {
                            "id": rid,
                            "status": "completed",
                            "usage": {
                                "input_tokens": 180,
                                "output_tokens": 60,
                                "input_token_details": {"audio_tokens": 100, "text_tokens": 80, "cached_tokens": 20, "cached_tokens_details": {"audio_tokens": 20, "text_tokens": 0}},
                                "output_token_details": {"audio_tokens": 45, "text_tokens": 15},
                            },
                        },
                    })
            elif ptype == "response.cancel":
                await self.q.put({"type": "response.done", "response": {"id": f"s2s-r-{self._idx}", "status": "cancelled"}})

        def __aiter__(self):
            return self

        async def __anext__(self):
            item = await self.q.get()
            if item is None:
                raise StopAsyncIteration
            return item

    s2s_conn = _FakeS2SConn()

    class _FakeS2SMgr:
        async def __aenter__(self):
            return s2s_conn

        async def __aexit__(self, *_a):
            await s2s_conn.q.put(None)

    async def _s2s_tool_exec(turn_id: str, call_id: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "data": {"tool": name, "args": args, "verified": True}}

    async def _s2s_sec_hook(_turn_id: str, _transcript: str) -> dict[str, Any] | None:
        return None  # Authenticated owner benchmark session

    s2s_adapter = OpenAISpeechToSpeechRealtimeAdapter(
        OpenAIAudioConfig(api_key="test", stt_model="gpt-4o-mini-transcribe", tts_voice="marin"),
        model="gpt-realtime-2.1",
        company_name="Produits Ero",
        tool_provider=lambda: [{"name": "search_products", "description": "Catalog search", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}}}],
        tool_executor=_s2s_tool_exec,
        security_transcript_hook=_s2s_sec_hook,
        interruption_manager=NaturalInterruptionManager(),
        connection_factory=lambda _m: _FakeS2SMgr(),
    )
    sock_a = _MemSocket()
    bridge_a = TelnyxMediaBridge(
        sock_a, s2s_adapter, locale="fr-CA",
        validate_start=_noop_validate, authorize=_noop_auth, execute_turn=_noop_exec,
        realtime_model="gpt-realtime-2.1", stt_model="gpt-4o-mini-transcribe", max_output_queue=4000,
    )
    await sock_a.inbound.put({"event": "start", "stream_id": "arch-a", "start": {"stream_id": "arch-a", "media_format": {"encoding": "PCMU", "sample_rate": 8000, "channels": 1}}})
    t_a = asyncio.create_task(bridge_a.run())
    await asyncio.sleep(0.04)

    t0 = time.monotonic()
    int_cursor = 0
    for idx, (_tag, qtext) in enumerate(questions):
        is_int = idx in interrupt_indices and int_cursor < len(TEN_INTERRUPTIONS)
        s2s_conn.slow_next = is_int
        s2s_conn._pending_query = qtext
        await s2s_conn.q.put({"type": "conversation.item.input_audio_transcription.completed", "item_id": f"q-a-{idx}", "transcript": qtext})
        if is_int:
            await _wait_playback_active(bridge_a)
            await bridge_a.interrupt(reason="caller_speech_barge_in")
            barge_text = TEN_INTERRUPTIONS[int_cursor]
            int_cursor += 1
            s2s_conn.slow_next = False
            s2s_conn._pending_query = barge_text
            await s2s_conn.q.put({"type": "conversation.item.input_audio_transcription.completed", "item_id": f"q-a-int-{idx}", "transcript": barge_text})
        await _wait_turn_settled(bridge_a, expected_completed=idx + 1)
    await sock_a.inbound.put({"event": "stop", "stream_id": "arch-a"})
    await asyncio.wait_for(t_a, timeout=5.0)
    results.append(ProtocolResult(
        execution_mode="SIMULATED_DETERMINISTIC",
        architecture="Architecture A (Native S2S)",
        model_stack="gpt-realtime-2.1 + Pre-Auth Gate + ToolGuard",
        questions_asked=len(questions),
        barge_in_followups=len(TEN_INTERRUPTIONS),
        audible_answers=bridge_a.telemetry["voice_response_completed"],
        lost_turns=bridge_a.central_ai_missing_answers,
        interruptions_sent=len(TEN_INTERRUPTIONS),
        interruptions_handled=bridge_a.telemetry["barge_in_triggered_count"],
        unconfirmed_suppressed=bridge_a.telemetry["unconfirmed_provider_interrupts_suppressed"],
        estimated_cost_usd="~0.18 USD / 20 turns (catalog pricing)",
        simulated_local_ms_per_turn=round((time.monotonic() - t0) * 1000 / len(questions), 1),
    ))

    # 2) Architecture B: Independent STT + gpt-6.2-sol + Independent PCM TTS
    class _FakeSTT:
        provider_id = "openai"

        async def transcribe(self, audio: bytes, *, locale: str, content_type: str) -> str:
            _ = audio
            return ""

    class _FakeTTS:
        async def synthesize_pcm_chunks(self, text: str, *, locale: str):
            _ = (text, locale)
            yield pcm_24k_sample
            await asyncio.sleep(0.04)
            yield pcm_24k_sample

    mod_adapter = ModularVoicePipelineAdapter(
        OpenAIAudioConfig(api_key="test", stt_model="gpt-4o-mini-transcribe", tts_model="gpt-4o-mini-tts", tts_voice="marin"),
        central_model="gpt-6.2-sol",
        stt_adapter=_FakeSTT(),
        tts_adapter=_FakeTTS(),
    )
    sock_b = _MemSocket()

    async def _mod_exec(_id: str, q: str) -> dict[str, Any]:
        return {"status": "success", "answer": f"Analyse Sol pour : {q[:45]}"}

    bridge_b = TelnyxMediaBridge(
        sock_b, mod_adapter, locale="fr-CA",
        validate_start=_noop_validate, authorize=_noop_auth, execute_turn=_mod_exec,
        realtime_model="gpt-4o-mini-tts", stt_model="gpt-4o-mini-transcribe", max_output_queue=4000,
    )
    await sock_b.inbound.put({"event": "start", "stream_id": "arch-b", "start": {"stream_id": "arch-b", "media_format": {"encoding": "PCMU", "sample_rate": 8000, "channels": 1}}})
    t_b = asyncio.create_task(bridge_b.run())
    await asyncio.sleep(0.04)

    t1 = time.monotonic()
    int_cursor_b = 0
    for idx, (_tag, qtext) in enumerate(questions):
        is_int = idx in interrupt_indices and int_cursor_b < len(TEN_INTERRUPTIONS)
        await mod_adapter._event_queue.put(SimpleNamespace(type="conversation.item.input_audio_transcription.completed", item_id=f"q-b-{idx}", transcript=qtext))
        if is_int:
            await _wait_playback_active(bridge_b)
            await bridge_b.interrupt(reason="caller_speech_barge_in")
            barge_text = TEN_INTERRUPTIONS[int_cursor_b]
            int_cursor_b += 1
            await mod_adapter._event_queue.put(SimpleNamespace(type="conversation.item.input_audio_transcription.completed", item_id=f"q-b-int-{idx}", transcript=barge_text))
        await _wait_turn_settled(bridge_b, expected_completed=idx + 1)
    await sock_b.inbound.put({"event": "stop", "stream_id": "arch-b"})
    await asyncio.wait_for(t_b, timeout=5.0)
    results.append(ProtocolResult(
        execution_mode="SIMULATED_DETERMINISTIC",
        architecture="Architecture B (Modular)",
        model_stack="gpt-4o-mini-transcribe + gpt-6.2-sol + gpt-4o-mini-tts",
        questions_asked=len(questions),
        barge_in_followups=len(TEN_INTERRUPTIONS),
        audible_answers=bridge_b.telemetry["voice_response_completed"],
        lost_turns=bridge_b.central_ai_missing_answers,
        interruptions_sent=len(TEN_INTERRUPTIONS),
        interruptions_handled=bridge_b.telemetry["barge_in_triggered_count"],
        unconfirmed_suppressed=bridge_b.telemetry["unconfirmed_provider_interrupts_suppressed"],
        estimated_cost_usd="~0.07 USD / 20 turns (catalog pricing)",
        simulated_local_ms_per_turn=round((time.monotonic() - t1) * 1000 / len(questions), 1),
    ))

    # 3) Repaired Hybrid: Gemini Live + gpt-6.2-sol
    class _FakeGemSession:
        def __init__(self) -> None:
            self.q: asyncio.Queue[Any] = asyncio.Queue()
            self._attempts: dict[str, int] = {}

        async def send_realtime_input(self, **_kw):
            return None

        async def send_client_content(self, **kwargs):
            key = str(kwargs.get("turns"))
            attempt = self._attempts.get(key, 0) + 1
            self._attempts[key] = attempt
            if attempt == 1:
                await self.q.put(SimpleNamespace(server_content=SimpleNamespace(interrupted=True, input_transcription=None, output_transcription=None, model_turn=None, turn_complete=False)))
            else:
                await self.q.put(SimpleNamespace(server_content=SimpleNamespace(interrupted=False, input_transcription=None, output_transcription=None, model_turn=SimpleNamespace(parts=[SimpleNamespace(inline_data=SimpleNamespace(data=pcm_24k_sample, mime_type="audio/pcm;rate=24000"))]), turn_complete=False)))
                await asyncio.sleep(0.03)
                await self.q.put(SimpleNamespace(server_content=SimpleNamespace(interrupted=False, input_transcription=None, output_transcription=None, model_turn=None, turn_complete=True)))

        async def receive(self):
            while True:
                m = await self.q.get()
                if m is None:
                    return
                yield m

    gem_sess = _FakeGemSession()

    class _GemCtx:
        async def __aenter__(self):
            return gem_sess

        async def __aexit__(self, *_a):
            await gem_sess.q.put(None)

    gem_adapter = GeminiLiveRealtimeAudioAdapter(
        OpenAIAudioConfig(api_key="test", stt_model="gpt-4o-mini-transcribe", tts_voice="Aoede"),
        api_key="gem-test",
        company_name="Produits Ero",
        client_factory=lambda _k: SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=lambda **_kw: _GemCtx()))),
    )
    sock_h = _MemSocket()
    bridge_h = TelnyxMediaBridge(
        sock_h, gem_adapter, locale="fr-CA",
        validate_start=_noop_validate, authorize=_noop_auth, execute_turn=_mod_exec,
        realtime_model="gemini-3.8-live", stt_model="gpt-4o-mini-transcribe", max_output_queue=4000,
    )
    await sock_h.inbound.put({"event": "start", "stream_id": "arch-h", "start": {"stream_id": "arch-h", "media_format": {"encoding": "PCMU", "sample_rate": 8000, "channels": 1}}})
    t_h = asyncio.create_task(bridge_h.run())
    await asyncio.sleep(0.04)

    t2 = time.monotonic()
    int_cursor_h = 0
    for idx, (_tag, qtext) in enumerate(questions):
        is_int = idx in interrupt_indices and int_cursor_h < len(TEN_INTERRUPTIONS)
        await gem_sess.q.put(SimpleNamespace(server_content=SimpleNamespace(interrupted=False, input_transcription=SimpleNamespace(text=qtext, finished=True), output_transcription=None, model_turn=None, turn_complete=True)))
        if is_int:
            await _wait_playback_active(bridge_h)
            await bridge_h.interrupt(reason="caller_speech_barge_in")
            barge_text = TEN_INTERRUPTIONS[int_cursor_h]
            int_cursor_h += 1
            await gem_sess.q.put(SimpleNamespace(server_content=SimpleNamespace(interrupted=False, input_transcription=SimpleNamespace(text=barge_text, finished=True), output_transcription=None, model_turn=None, turn_complete=True)))
        await _wait_turn_settled(bridge_h, expected_completed=idx + 1)
    await sock_h.inbound.put({"event": "stop", "stream_id": "arch-h"})
    await asyncio.wait_for(t_h, timeout=5.0)
    results.append(ProtocolResult(
        execution_mode="SIMULATED_DETERMINISTIC",
        architecture="Repaired Hybrid (Gemini + Sol)",
        model_stack="gemini-3.8-live audio + gpt-6.2-sol",
        questions_asked=len(questions),
        barge_in_followups=len(TEN_INTERRUPTIONS),
        audible_answers=bridge_h.telemetry["voice_response_completed"],
        lost_turns=bridge_h.central_ai_missing_answers,
        interruptions_sent=len(TEN_INTERRUPTIONS),
        interruptions_handled=bridge_h.telemetry["barge_in_triggered_count"],
        unconfirmed_suppressed=bridge_h.telemetry["unconfirmed_provider_interrupts_suppressed"],
        estimated_cost_usd="~0.06 USD / 20 turns (catalog pricing)",
        simulated_local_ms_per_turn=round((time.monotonic() - t2) * 1000 / len(questions), 1),
    ))
    return results


async def run_live_api_probe() -> dict[str, Any]:
    """Execute real API availability & tool-calling checks when keys exist in env."""
    report: dict[str, Any] = {
        "execution_mode": "LIVE_API_PROBE",
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "google_configured": bool(os.getenv("GOOGLE_AI_API_KEY")),
    }
    if report["openai_configured"]:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        for model in ("gpt-6.2-sol", "gpt-6.2-astra"):
            try:
                t0 = time.monotonic()
                resp = await client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "Donne une idée e-commerce en 1 phrase."}],
                    max_completion_tokens=80,
                    reasoning_effort="low",
                )
                report[model] = {"ok": True, "latency_ms": round((time.monotonic() - t0) * 1000), "chars": len(resp.choices[0].message.content or "")}
            except Exception as exc:
                report[model] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("deterministic", "live-api"), default="deterministic")
    args = parser.parse_args()
    if args.mode == "live-api":
        out = asyncio.run(run_live_api_probe())
        print(json.dumps(out, indent=2))
        return 0
    res = asyncio.run(run_deterministic_ab_benchmark())
    print("NOTE: Mode = SIMULATED_DETERMINISTIC (in-memory sockets/queues, 0 network RTT; NOT live phone call latency).")
    print("| Mode | Architecture | Models | Initial Qs | Barge-In Follow-ups | Completed Audible | Lost | Barge-Ins | Suppressed Unconfirmed | Est. Cost | Sim Local ms/turn |")
    print("|---|---|---|---:|---:|---:|---:|---:|---:|---|---:|")
    for r in res:
        print(
            f"| {r.execution_mode} | {r.architecture} | {r.model_stack} | {r.questions_asked} | "
            f"{r.barge_in_followups} | {r.audible_answers} | {r.lost_turns} | "
            f"{r.interruptions_handled}/{r.interruptions_sent} | {r.unconfirmed_suppressed} | "
            f"{r.estimated_cost_usd} | {r.simulated_local_ms_per_turn} |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
