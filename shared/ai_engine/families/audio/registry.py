"""Catalogue des modèles Audio : entièrement réutilisé depuis `architectures/audio`,
unique source de vérité (aucun modèle propre à cette famille).
"""

from shared.ai_engine.architectures.audio.wav2vec2 import Wav2Vec2Model
from shared.ai_engine.architectures.audio.whisper_asr import WhisperASRModel
from shared.ai_engine.core.model_candidate_registry import ModelCandidateRegistry


def build_audio_registry() -> ModelCandidateRegistry:
    registry = ModelCandidateRegistry()
    registry.register("whisper_asr", WhisperASRModel)
    registry.register("wav2vec2", Wav2Vec2Model)
    return registry
