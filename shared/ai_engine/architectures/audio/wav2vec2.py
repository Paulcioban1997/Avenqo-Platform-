"""Candidat Wav2Vec2 (sera implémenté avec transformers.Wav2Vec2ForCTC)."""

from shared.ai_engine.core.model_stub import UntrainedModel


class Wav2Vec2Model(UntrainedModel):
    candidate_id = "wav2vec2"
