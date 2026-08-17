"""Catalogue LLM : grands modèles de langage, réutilisés par la famille LLM et par toute
autre famille métier ayant besoin d'un modèle de langage (unique source de vérité).
"""

from shared.ai_engine.architectures.llm.claude import ClaudeModel
from shared.ai_engine.architectures.llm.gemini import GeminiModel
from shared.ai_engine.architectures.llm.llama import LlamaModel
from shared.ai_engine.architectures.llm.mistral import MistralModel
from shared.ai_engine.architectures.llm.openai_gpt import OpenAIGPTModel

__all__ = ["OpenAIGPTModel", "ClaudeModel", "GeminiModel", "LlamaModel", "MistralModel"]
