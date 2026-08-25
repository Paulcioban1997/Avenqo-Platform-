from backend.app.assistants.registry import AssistantRegistry, build_default_assistant_registry

# Registre statique (métadonnées pures, sans état ni session DB) : une seule
# instance suffit pour tout le process, comme le catalogue de plans.
_REGISTRY = build_default_assistant_registry()


def get_assistant_registry() -> AssistantRegistry:
    return _REGISTRY
