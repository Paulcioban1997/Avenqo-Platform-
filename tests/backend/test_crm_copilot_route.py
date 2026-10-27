from pathlib import Path
import re

from fastapi.routing import APIRoute

from backend.app.routers.crm import crm_copilot_chat, router as crm_router


def test_crm_copilot_chat_is_published_under_versioned_api() -> None:
    assert crm_router.prefix == "/crm"
    copilot = [
        route
        for route in crm_router.routes
        if isinstance(route, APIRoute)
        and getattr(route.endpoint, "__name__", "") == "crm_copilot_chat"
    ]
    assert len(copilot) == 1
    assert copilot[0].path in {"/copilot/chat", "/crm/copilot/chat"}
    assert copilot[0].path.endswith("/copilot/chat")
    assert "POST" in copilot[0].methods
    assert copilot[0].endpoint is crm_copilot_chat
    assert not any(
        isinstance(route, APIRoute) and route.path.rstrip("/") == "/crm/copilot"
        for route in crm_router.routes
    )

    source = (
        Path(__file__).resolve().parents[2] / "backend" / "app" / "api" / "router.py"
    ).read_text(encoding="utf-8")
    assert re.search(
        r"include_router\(\s*crm_router\s*,\s*prefix=\"/api/v1\"",
        source,
    )
    assert "/api/v1/crm/copilot/chat" == "/api/v1" + (
        copilot[0].path if copilot[0].path.startswith("/crm/") else crm_router.prefix + copilot[0].path
    )
