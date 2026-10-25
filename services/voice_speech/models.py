"""Lazy GPU imports keep speech dependencies out of the Avenqo API image."""
from __future__ import annotations

import io
import wave
from pathlib import Path

from backend.app.voice.open_speech_catalog import (
    CHATTERBOX, CHATTERBOX_CHECKPOINT, KOKORO, PARAKEET, language_code, pcm_wav,
)


def decode_wav(data: bytes) -> tuple[bytes, int]:
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getcomptype() != "NONE":
                raise ValueError("Expected uncompressed mono PCM16 WAV")
            rate = wav.getframerate()
            if rate not in {8000, 16000, 24000, 48000}:
                raise ValueError("Unsupported sample rate")
            if not 0 < wav.getnframes() <= rate * 30:
                raise ValueError("Utterance must be between zero and 30 seconds")
            audio = wav.readframes(wav.getnframes())
            if len(audio) != wav.getnframes() * 2:
                raise ValueError("Truncated WAV")
            return audio, rate
    except (wave.Error, EOFError) as exc:
        raise ValueError("Invalid WAV") from exc


class ParakeetEngine:
    artifact = PARAKEET

    def __init__(self, *, cache_dir: str | None = None, device: str = "cuda"):
        import torch
        from transformers import AutoModelForTDT, AutoProcessor

        self.processor = AutoProcessor.from_pretrained(
            PARAKEET.model_id, revision=PARAKEET.revision,
            cache_dir=cache_dir, local_files_only=True, trust_remote_code=False,
        )
        self.model = AutoModelForTDT.from_pretrained(
            PARAKEET.model_id, revision=PARAKEET.revision,
            cache_dir=cache_dir, local_files_only=True, trust_remote_code=False,
            dtype=torch.float32,
        ).to(device).eval()

    def transcribe(self, data: bytes, locale: str) -> dict:
        import numpy as np
        import torch
        from scipy.signal import resample_poly

        pcm, rate = decode_wav(data)
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
        if rate != 16000:
            from math import gcd
            divisor = gcd(rate, 16000)
            audio = resample_poly(audio, 16000 // divisor, rate // divisor)
        inputs = self.processor(audio, sampling_rate=16000, return_tensors="pt")
        inputs = inputs.to(self.model.device, dtype=self.model.dtype)
        with torch.inference_mode():
            output = self.model.generate(**inputs, return_dict_in_generate=True, max_new_tokens=1280)
        text = self.processor.batch_decode(output.sequences, skip_special_tokens=True)[0]
        return {"text": text, "audio_seconds": len(pcm) / (rate * 2)}


class ChatterboxEngine:
    artifact = CHATTERBOX

    def __init__(self, *, cache_dir: str | None = None, device: str = "cuda"):
        from huggingface_hub import snapshot_download
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        path = snapshot_download(
            CHATTERBOX.model_id, revision=CHATTERBOX.revision,
            cache_dir=cache_dir, local_files_only=True,
        )
        if not (Path(path) / CHATTERBOX_CHECKPOINT).is_file():
            raise RuntimeError("Pinned multilingual V3 checkpoint unavailable")
        self.model = ChatterboxMultilingualTTS.from_local(path, device, t3_model="v3")

    def synthesize(self, text: str, locale: str) -> bytes:
        import numpy as np
        from scipy.signal import resample_poly

        # Use only the model's shipped voice. No uploaded reference, cloning or tenant voice state.
        wav = self.model.generate(text, language_id=language_code(locale))
        audio = wav.detach().cpu().numpy().reshape(-1)
        if self.model.sr != 24000:
            from math import gcd
            divisor = gcd(self.model.sr, 24000)
            audio = resample_poly(audio, 24000 // divisor, self.model.sr // divisor)
        if not 0 < len(audio) <= 24000 * 40 or not np.isfinite(audio).all():
            raise ValueError("Generated audio outside bounded output contract")
        return (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()


class KokoroEngine:
    artifact = KOKORO

    def __init__(self, *, cache_dir: str | None = None, device: str = "cpu"):
        from huggingface_hub import snapshot_download
        from kokoro import KModel, KPipeline

        self.path = Path(snapshot_download(KOKORO.model_id, revision=KOKORO.revision,
                         cache_dir=cache_dir, local_files_only=True))
        self.model = KModel(config=str(self.path / "config.json"),
                            model=str(self.path / "kokoro-v1_0.pth"), repo_id=KOKORO.model_id).to(device).eval()
        self.pipelines = {}
        self.pipeline_type = KPipeline

    def synthesize(self, text: str, locale: str) -> bytes:
        import numpy as np
        import torch

        code = language_code(locale)
        language, voice = {"fr": ("f", "ff_siwis"), "en": ("a", "af_heart"), "es": ("e", "ef_dora")}[code]
        if code not in self.pipelines:
            self.pipelines[code] = self.pipeline_type(lang_code=language, model=self.model, repo_id=KOKORO.model_id)
        with torch.inference_mode():
            chunks = [audio.detach().cpu().numpy() for _, _, audio in self.pipelines[code](text, voice=str(self.path / "voices" / (voice + ".pt")))]
        if not chunks:
            raise ValueError("No speech generated")
        audio = np.concatenate(chunks).reshape(-1)
        if not 0 < len(audio) <= 24000 * 40 or not np.isfinite(audio).all():
            raise ValueError("Generated audio outside bounded output contract")
        return (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
