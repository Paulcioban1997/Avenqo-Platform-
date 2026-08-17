"""Catalogue Audio : architectures de traitement audio, réutilisées par la famille Audio
(unique source de vérité).
"""

from shared.ai_engine.architectures.audio.wav2vec2 import Wav2Vec2Model
from shared.ai_engine.architectures.audio.whisper_asr import WhisperASRModel

__all__ = ["WhisperASRModel", "Wav2Vec2Model"]
