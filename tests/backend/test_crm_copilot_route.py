from backend.app.api.router import api_router


def test_crm_copilot_chat_is_published_under_versioned_api() -> None:
    paths = {getattr(route, "path", "") for route in api_router.routes}
    assert "/api/v1/crm/copilot/chat" in paths
    assert "/crm/copilot" not in paths
