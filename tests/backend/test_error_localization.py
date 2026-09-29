from __future__ import annotations

from fastapi import Body, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from backend.app.config.settings import get_settings
from backend.app.core.error_localization import (
    ERROR_MESSAGES,
    catalog_message,
    localized_api_message,
    resolve_api_locale,
)
from backend.app.core.exception_handlers import register_exception_handlers
from backend.app.core.locale_catalog import LOCALES
from backend.main import create_application


class ExamplePayload(BaseModel):
    name: str


def _client() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/missing")
    def missing() -> None:
        raise HTTPException(status_code=404, detail="Client introuvable.")

    @app.post("/validation")
    def validation(payload: ExamplePayload = Body(...)) -> dict[str, bool]:
        return {"ok": True}

    @app.post("/price")
    def price() -> None:
        raise HTTPException(status_code=422, detail="Price analysis requires unit price.")

    @app.get("/missing-source")
    def missing_source() -> None:
        raise HTTPException(
            status_code=422,
            detail=(
                "Le fichier original de ce dataset n'est plus disponible sur le "
                "stockage. Réimportez le fichier pour restaurer les données nettoyées."
            ),
        )

    @app.post("/module")
    def unavailable_module() -> None:
        raise HTTPException(status_code=409, detail="This module is not available for activation.")

    return TestClient(app)


def test_error_catalog_covers_all_canonical_locales_and_keys() -> None:
    assert set(ERROR_MESSAGES) == {locale.locale for locale in LOCALES}
    keys = set(ERROR_MESSAGES["fr"])
    assert all(set(messages) == keys for messages in ERROR_MESSAGES.values())
    assert all(value.strip() for messages in ERROR_MESSAGES.values() for value in messages.values())


def test_accept_language_resolves_region_and_quality_preferences() -> None:
    assert resolve_api_locale("es-MX, fr;q=0.8") == "es"
    assert resolve_api_locale("de-CH, en;q=0.5") == "de"
    assert resolve_api_locale("unsupported;q=1, fr-CA;q=0.6") == "fr-CA"
    assert resolve_api_locale(None) == "fr"


def test_success_catalog_messages_follow_the_requested_locale() -> None:
    assert catalog_message("es-MX", "auth", "registerSuccess", "fallback") == (
        "Cuenta creada. Verifica tu correo electrónico."
    )
    assert localized_api_message("de-CH", "enterprise_quote_received").startswith(
        "Ihre Enterprise-Angebotsanfrage ist eingegangen."
    )


def test_http_error_localizes_message_without_changing_response_contract() -> None:
    response = _client().get("/missing", headers={"Accept-Language": "es-MX,es;q=0.9"})

    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"success", "error", "request_id"}
    assert body["success"] is False
    assert body["error"]["code"] == "HTTP_ERROR"
    assert body["error"]["message"] == ERROR_MESSAGES["es"]["not_found"]
    assert body["error"]["details"] is None


def test_validation_error_preserves_detail_shape_and_localizes_messages() -> None:
    response = _client().post("/validation", json={}, headers={"Accept-Language": "de-CH"})

    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"success", "error", "request_id"}
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["message"] == ERROR_MESSAGES["de"]["validation_failed"]
    assert body["error"]["details"] == [
        {
            "type": "missing",
            "loc": ["body", "name"],
            "msg": ERROR_MESSAGES["de"]["required_field"],
        }
    ]


def test_business_error_keeps_specific_meaning_when_localized() -> None:
    response = _client().post("/price", headers={"Accept-Language": "de-CH"})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "HTTP_ERROR"
    assert body["error"]["message"] == ERROR_MESSAGES["de"]["price_unit_required"]
    assert body["error"]["details"] is None


def test_missing_dataset_source_keeps_reimport_guidance_when_localized() -> None:
    response = _client().get("/missing-source", headers={"Accept-Language": "fr-CA"})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "HTTP_ERROR"
    assert "stockage" in body["error"]["message"]
    assert "réimportez" in body["error"]["message"].casefold()


def test_coming_soon_module_error_keeps_specific_meaning() -> None:
    response = _client().post("/module", headers={"Accept-Language": "fr-CA"})

    assert response.status_code == 409
    assert response.json()["error"]["message"] == "Ce module n’est pas encore disponible."


def test_cors_allows_accept_language_from_frontend() -> None:
    settings = get_settings()
    origin = settings.cors_origins[0] if settings.cors_origins else "http://localhost:8080"
    response = TestClient(create_application()).options(
        "/api/v1/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "accept-language",
        },
    )

    assert response.status_code == 200
    assert "accept-language" in response.headers["access-control-allow-headers"].lower()