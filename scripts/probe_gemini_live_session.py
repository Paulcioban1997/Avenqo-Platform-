"""Real Gemini Live session probe — no secrets, PIN, or spoken content logged.

Usage (inside API container with GOOGLE_AI_API_KEY):
  python scripts/probe_gemini_live_session.py
  python scripts/probe_gemini_live_session.py --model gemini-3.8-live
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

SUPPORTED = ("gemini-3.8-live", "gemini-3.8-live-extended-thinking")
RETIRED = {
    "gemini-2.0-flash-live-001",
    "gemini-2.5-flash-native-audio-preview-12-2025",
    "gemini-2.0-flash-exp",
}
DEFAULT = "gemini-3.8-live"


def resolve_model(requested: str | None) -> str:
    model = (requested or DEFAULT).strip() or DEFAULT
    if model in SUPPORTED:
        return model
    if model in RETIRED:
        raise SystemExit("PROBE=fail reason=retired_model model=%s" % model)
    raise SystemExit("PROBE=fail reason=unsupported_model model=%s" % model)


async def _probe(model: str) -> int:
    api_key = (
        os.environ.get("GOOGLE_AI_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_AI_STUDIO_API_KEY")
        or ""
    ).strip()
    if not api_key:
        print("PROBE=fail reason=missing_google_ai_api_key")
        return 2

    model = resolve_model(model)
    print("PROBE=start model=%s key_len=%d" % (model, len(api_key)))

    from google import genai
    from google.genai import types

    # Official Live API get-started uses v1beta + minimal AUDIO config.
    client = genai.Client(
        api_key=api_key,
        http_options={"api_version": "v1beta"},
    )
    config: dict = {"response_modalities": ["AUDIO"]}

    started = time.perf_counter()
    audio_bytes = 0
    turns = 0
    try:
        async with client.aio.live.connect(model=model, config=config) as session:
            await session.send_realtime_input(text="Reply with a short hello only.")
            async for event in session.receive():
                turns += 1
                data = getattr(event, "data", None)
                if isinstance(data, (bytes, bytearray)) and data:
                    audio_bytes += len(data)
                sc = getattr(event, "server_content", None)
                if sc is not None:
                    model_turn = getattr(sc, "model_turn", None)
                    if model_turn is not None:
                        for part in getattr(model_turn, "parts", None) or []:
                            inline = getattr(part, "inline_data", None)
                            if inline is not None and getattr(inline, "data", None):
                                audio_bytes += len(inline.data)
                    if getattr(sc, "turn_complete", False):
                        break
                if turns >= 40:
                    break
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        status = getattr(exc, "status", None)
        message = str(exc)
        for secret in filter(None, [api_key]):
            if secret and secret in message:
                message = message.replace(secret, "[redacted]")
        message = message.replace("\n", " ")[:240]
        print(
            "PROBE=fail model=%s error_code=%s http=%s status=%s elapsed_ms=%d detail=%s"
            % (model, type(exc).__name__, code, status, elapsed_ms, message)
        )
        return 1

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    print(
        "PROBE=ok model=%s elapsed_ms=%d audio_bytes=%d events=%d"
        % (model, elapsed_ms, audio_bytes, turns)
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=os.environ.get("GEMINI_LIVE_MODEL") or DEFAULT)
    args = parser.parse_args()
    return asyncio.run(_probe(args.model))


if __name__ == "__main__":
    raise SystemExit(main())
