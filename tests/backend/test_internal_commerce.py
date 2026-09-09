from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.routers import internal_commerce


class _Runner:
    async def reconcile_active(self) -> int:
        return 2


@pytest.mark.asyncio
async def test_reconciliation_trigger_requires_configured_token(monkeypatch) -> None:
    monkeypatch.setattr(
        internal_commerce,
        "get_settings",
        lambda: SimpleNamespace(connector_ai_scheduler_token=""),
    )
    with pytest.raises(HTTPException) as error:
        await internal_commerce.reconcile_commerce_connections("", _Runner())
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_reconciliation_trigger_rejects_invalid_token(monkeypatch) -> None:
    monkeypatch.setattr(
        internal_commerce,
        "get_settings",
        lambda: SimpleNamespace(connector_ai_scheduler_token="expected"),
    )
    with pytest.raises(HTTPException) as error:
        await internal_commerce.reconcile_commerce_connections("wrong", _Runner())
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_reconciliation_trigger_runs_active_connections(monkeypatch) -> None:
    monkeypatch.setattr(
        internal_commerce,
        "get_settings",
        lambda: SimpleNamespace(connector_ai_scheduler_token="expected"),
    )
    assert await internal_commerce.reconcile_commerce_connections(
        "expected", _Runner()
    ) == {"claimed": 2}