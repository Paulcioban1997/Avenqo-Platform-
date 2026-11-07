"""Pinned experimental speech artifacts; speech models never own business tools."""
from dataclasses import dataclass
import io
import wave


@dataclass(frozen=True)
class SpeechArtifact:
    model_id: str
    revision: str
    license_id: str
    locales: frozenset[str]


PARAKEET = SpeechArtifact(
    "nvidia/parakeet-tdt-0.6b-v3",
    "541d1f99c6b0c3cd0b11a95167540bb8edefd82b", "CC-BY-4.0",
    frozenset("en es fr de bg hr cs da nl et fi el hu it lv lt mt pl pt ro sk sl sv ru uk".split()),
)
CHATTERBOX = SpeechArtifact(
    "ResembleAI/chatterbox",
    "5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18", "MIT",
    frozenset("ar da de el en es fi fr he hi it ja ko ms nl no pl pt ru sv sw tr zh".split()),
)
CHATTERBOX_CODE_REVISION = "5de7a54aa4e5e2baadb0182dde554908b48b85c2"
CHATTERBOX_CHECKPOINT = "t3_mtl23ls_v3.safetensors"
CHATTERBOX_FILES = (
    "ve.pt", CHATTERBOX_CHECKPOINT, "s3gen.pt", "conds.pt",
    "grapheme_mtl_merged_expanded_v1.json", "Cangjie5_TC.json",
)
KOKORO = SpeechArtifact(
    "hexgrad/Kokoro-82M", "f3ff3571791e39611d31c381e3a41a3af07b4987",
    "Apache-2.0", frozenset({"fr", "en", "es"}),
)
KOKORO_FILES = ("config.json", "kokoro-v1_0.pth", "voices/ff_siwis.pt", "voices/af_heart.pt", "voices/ef_dora.pt")


def language_code(locale: str) -> str:
    return locale.strip().lower().replace("_", "-").split("-")[0]


def pcm_wav(audio: bytes, sample_rate: int) -> bytes:
    result = io.BytesIO()
    with wave.open(result, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(audio)
    return result.getvalue()
