from fastapi import FastAPI
from fastapi.routing import APIRoute

from backend.app.api.router import api_router
from backend.app.routers.crm import crm_copilot_chat, router as crm_router


def test_crm_copilot_chat_is_published_under_versioned_api() -> None:
    assert crm_router.prefix == "/crm"
    assert any(
        isinstance(route, APIRoute) and route.endpoint is crm_copilot_chat
        for route in crm_router.routes
    )

    app = FastAPI()
    app.include_router(api_router)
    matching = [
        route
        for route in app.routes
        if isinstance(route, APIRoute) and route.endpoint is crm_copilot_chat
    ]
    assert {route.path for route in matching} == {"/api/v1/crm/copilot/chat"}
    assert all("POST" in route.methods for route in matching)
    assert not any(
        isinstance(route, APIRoute) and route.path == "/crm/copilot"
        for route in app.routes
    )
