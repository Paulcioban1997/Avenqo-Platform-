"""Catalogue des modèles LLM : entièrement réutilisé depuis `architectures/llm`,
unique source de vérité (aucun modèle propre à cette famille).
"""

from shared.ai_engine.architectures.llm.claude import ClaudeModel
from shared.ai_engine.architectures.llm.gemini import GeminiModel
from shared.ai_engine.architectures.llm.llama import LlamaModel
from shared.ai_engine.architectures.llm.mistral import MistralModel
from shared.ai_engine.architectures.llm.openai_gpt import OpenAIGPTModel
from shared.ai_engine.core.model_candidate_registry import ModelCandidateRegistry


def build_llm_registry() -> ModelCandidateRegistry:
    registry = ModelCandidateRegistry()
    registry.register("openai_gpt", OpenAIGPTModel)
    registry.register("claude", ClaudeModel)
    registry.register("gemini", GeminiModel)
    registry.register("llama", LlamaModel)
    registry.register("mistral", MistralModel)
    return registry
