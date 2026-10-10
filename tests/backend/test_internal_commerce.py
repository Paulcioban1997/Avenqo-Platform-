from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.dependencies import internal
from backend.app.routers import internal_commerce


class _Runner:
    async def reconcile_active(self) -> int:
        return 2


def test_reconciliation_trigger_requires_configured_token(monkeypatch) -> None:
    monkeypatch.setattr(
        internal,
        "get_settings",
        lambda: SimpleNamespace(connector_ai_scheduler_token=""),
    )
    with pytest.raises(HTTPException) as error:
        internal.require_internal_service_token("")
    assert error.value.status_code == 503


def test_reconciliation_trigger_rejects_invalid_token(monkeypatch) -> None:
    monkeypatch.setattr(
        internal,
        "get_settings",
        lambda: SimpleNamespace(connector_ai_scheduler_token="expected"),
    )
    with pytest.raises(HTTPException) as error:
        internal.require_internal_service_token("wrong")
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_reconciliation_trigger_runs_active_connections(monkeypatch) -> None:
    monkeypatch.setattr(
        internal,
        "get_settings",
        lambda: SimpleNamespace(connector_ai_scheduler_token="expected"),
    )
    internal.require_internal_service_token("expected")
    assert await internal_commerce.reconcile_commerce_connections(_Runner()) == {"claimed": 2}
