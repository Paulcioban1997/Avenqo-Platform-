"""Real local neural inference through the isolated worker's HTTP application.

No telephone connection, hosted inference, business mutation or LLM request.
Contract fixtures are deliberately not usable as benchmark engines.
"""
import argparse
import audioop
import base64
import hashlib
import json
import math
import platform
import re
import secrets
import time
import unicodedata
from pathlib import Path


def word_error_rate(reference: str, hypothesis: str) -> float:
    def words(text):
        text = unicodedata.normalize("NFKC", text).casefold()
        return re.sub(r"[^\w\s]", " ", text).split()
    expected, actual = words(reference), words(hypothesis)
    if not expected:
        raise ValueError("Human reference transcript required")
    previous = list(range(len(actual) + 1))
    for index, word in enumerate(expected, 1):
        current = [index]
        for offset, other in enumerate(actual, 1):
            current.append(min(previous[offset] + 1, current[-1] + 1, previous[offset - 1] + (word != other)))
        previous = current
    return previous[-1] / len(expected)


def main():
    import torch
    from fastapi.testclient import TestClient
    from backend.app.voice.open_speech_catalog import pcm_wav
    from backend.app.voice.audio_codec import TelnyxAudioCodec
    from services.voice_speech.app import create_app
    from services.voice_speech.models import ChatterboxEngine, KokoroEngine, ParakeetEngine

    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=["asr", "tts"], required=True)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--asr-manifest")
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument("--tts-backend", choices=["chatterbox", "kokoro"], default="chatterbox")
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    if args.device == "cpu":
        torch.set_num_threads(4)
    engine = (ParakeetEngine if args.role == "asr" else (KokoroEngine if args.tts_backend == "kokoro" else ChatterboxEngine))(cache_dir=args.cache_dir, device=args.device)
    if args.device == "cuda":
        torch.cuda.synchronize()
    report = {"role": args.role, "model": engine.artifact.model_id,
              "revision": engine.artifact.revision, "license": engine.artifact.license_id,
              "device": args.device, "gpu": torch.cuda.get_device_name(0) if args.device == "cuda" else None,
              "torch": torch.__version__, "platform": platform.platform(),
              "model_load_seconds": time.perf_counter() - started,
              "network": "ASGI local HTTP worker; not Telnyx", "samples": [],
              "french_canadian_certified": False, "telephone_tested": False,
              "central_llm_tested": False, "human_mos": None}
    key = secrets.token_urlsafe(32)
    with TestClient(create_app(role=args.role, api_key=key, engine=engine, tts_backend=args.tts_backend)) as client:
        headers = {"Authorization": "Bearer " + key}
        assert client.get("/health", headers=headers).json()["revision"] == engine.artifact.revision
        if args.role == "tts":
            texts = [
                ("fr-CA", "Bonjour, bienvenue chez Avenqo. Le stock de ce produit est inconnu."),
                ("fr-CA", "Les ventes disponibles sont historiques. Elles ne permettent pas de confirmer les ventes actuelles."),
                ("en", "Hello. I cannot confirm current inventory from historical sales."),
                ("es", "Hola. No puedo confirmar las existencias actuales."),
            ]
            for index, (locale, text) in enumerate(texts):
                start = time.perf_counter()
                response = client.post("/v1/audio/speech", headers=headers, json={"input": text, "language": locale})
                if response.status_code != 200:
                    raise RuntimeError("TTS worker failure: " + str(getattr(client.app.state, "last_failure_class", response.status_code)))
                elapsed = time.perf_counter() - start
                wav = pcm_wav(response.content, 24000)
                filename = f"{index}-{locale}.wav"
                (output / filename).write_bytes(wav)
                codec = TelnyxAudioCodec()
                phone = b"".join(codec.outbound_pcm(base64.b64encode(response.content[pos:pos + 9600]).decode("ascii"))
                                 for pos in range(0, len(response.content), 9600))
                (output / f"{index}-{locale}-telephone-8khz.wav").write_bytes(pcm_wav(audioop.ulaw2lin(phone, 2), 8000))
                seconds = len(response.content) / 48000
                row = {"locale": locale, "text": text, "audio_file": filename,
                       "sha256": hashlib.sha256(wav).hexdigest(), "audio_seconds": seconds,
                       "first_audio_seconds": elapsed, "rtf": elapsed / seconds,
                       "native_streaming": False, "status": "PASS_INFERENCE_ONLY"}
                report["samples"].append(row)
                (output / "tts-progress.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            assert client.post("/v1/audio/speech", headers=headers, json={"input": "Bună ziua", "language": "ro"}).status_code == 422
            report["romanian"] = "BLOCKED_UNSUPPORTED_TTS_LANGUAGE"
        else:
            if not args.asr_manifest:
                raise ValueError("An explicit public/human ASR reference manifest is required")
            for sample in json.loads(Path(args.asr_manifest).read_text(encoding="utf-8")):
                start = time.perf_counter()
                response = client.post("/v1/audio/transcriptions", headers=headers, content=Path(sample["path"]).read_bytes())
                if response.status_code != 200:
                    raise RuntimeError("ASR worker failure: " + str(getattr(client.app.state, "last_failure_class", response.status_code)))
                row = response.json()
                report["samples"].append({"locale": sample["locale"], "source": sample["source"],
                    "reference": sample["reference"], "transcript": row["text"],
                    "seconds": time.perf_counter() - start, "audio_seconds": row["audio_seconds"],
                    "wer": word_error_rate(sample["reference"], row["text"]), "human_reference": True})
                (output / "asr-progress.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["status"] = "PASS_LOCAL_NEURAL_INFERENCE"
    if args.device == "cuda":
        report["peak_cuda_allocated_mib"] = torch.cuda.max_memory_allocated() / 2**20
    (output / (args.role + "-benchmark.json")).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"role": args.role, "status": report["status"], "samples": len(report["samples"])}))


if __name__ == "__main__":
    main()
