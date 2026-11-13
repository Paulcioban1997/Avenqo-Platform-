"""Offline audio-path checks. They do not dial, spend provider credits, or read secrets.

Telnyx bidirectional media, as started by TelnyxClient.media_stream_payload, is
stream_bidirectional_mode=rtp and stream_bidirectional_codec=PCMU: mono G.711
μ-law at 8 kHz. One 20 ms frame is 160 bytes. The realtime providers deliver
16-bit little-endian PCM at 24 kHz, which TelnyxAudioCodec.outbound_pcm converts.
"""
from __future__ import annotations

import audioop
import base64
import math
import struct

from backend.app.voice.audio_codec import TelnyxAudioCodec

PCMU_FRAME_BYTES = 160
PCM_SAMPLE_RATE = 24000


def diagnostic_pcm24(*, sample_rate: int = PCM_SAMPLE_RATE) -> bytes:
    """Deterministic 24 kHz PCM16 tone used as the synthetic test phrase."""
    frames = []
    for index in range(sample_rate // 2):
        freq = 440 if index < sample_rate // 4 else 554
        sample = int(8000 * math.sin(2 * math.pi * freq * index / sample_rate))
        frames.append(struct.pack("<h", sample))
    return b"".join(frames)


def encode_diagnostic_phrase() -> dict[str, object]:
    """Test A: known PCM through the real Telnyx outbound encoder and event shape."""
    codec = TelnyxAudioCodec()
    pcm = diagnostic_pcm24()
    payload = base64.b64encode(pcm).decode("ascii")
    pcmu = codec.outbound_pcm(payload)
    frames = [pcmu[index:index + PCMU_FRAME_BYTES] for index in range(0, len(pcmu), PCMU_FRAME_BYTES)]
    if frames and len(frames[-1]) < PCMU_FRAME_BYTES:
        frames[-1] = frames[-1].ljust(PCMU_FRAME_BYTES, b"\xff")
    events = [
        {"event": "media", "media": {"payload": base64.b64encode(frame).decode("ascii")}}
        for frame in frames
    ]
    audible = 0
    for frame in frames:
        if audioop.rms(audioop.ulaw2lin(frame, 2), 2) > 0:
            audible += 1
    return {
        "test": "A",
        "codec": "PCMU",
        "sample_rate_hz": 8000,
        "frame_bytes": PCMU_FRAME_BYTES,
        "frames": len(frames),
        "audible_frames": audible,
        "bytes": len(pcmu),
        "events": events,
        "valid": bool(frames) and all(len(frame) == PCMU_FRAME_BYTES for frame in frames) and audible > 0,
    }


def encode_tts_pcm(pcm24: bytes) -> dict[str, object]:
    """Test B: provider PCM through the same encoder, without calling a provider."""
    if len(pcm24) < 4 or len(pcm24) % 2:
        return {"test": "B", "valid": False, "frames": 0}
    codec = TelnyxAudioCodec()
    pcmu = codec.outbound_pcm(base64.b64encode(pcm24).decode("ascii"))
    audible = audioop.rms(audioop.ulaw2lin(pcmu, 2), 2) > 0 if pcmu else False
    return {
        "test": "B",
        "frames": len(pcmu) // PCMU_FRAME_BYTES,
        "bytes": len(pcmu),
        "valid": len(pcmu) >= PCMU_FRAME_BYTES and audible,
    }


def run_offline_audio_diagnostics() -> dict[str, object]:
    phrase = encode_diagnostic_phrase()
    tts = encode_tts_pcm(diagnostic_pcm24())
    return {
        "calls_placed": False,
        "provider_requests": 0,
        "test_a_direct_audio": {key: phrase[key] for key in ("test", "codec", "sample_rate_hz", "frame_bytes", "frames", "audible_frames", "valid")},
        "test_b_tts_encoding": {key: tts[key] for key in ("test", "frames", "valid")},
    }
