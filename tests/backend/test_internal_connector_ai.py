from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.routers import internal_connector_ai


class _EvaluationService:
    def __init__(self, *args, **kwargs):
        pass

    def run_due(self):
        return 3


def test_scheduler_trigger_requires_configured_token(monkeypatch) -> None:
    monkeypatch.setattr(
        internal_connector_ai,
        "get_settings",
        lambda: SimpleNamespace(connector_ai_scheduler_token=""),
    )
    with pytest.raises(HTTPException) as error:
        internal_connector_ai.evaluate_connector_changes("", object(), object())
    assert error.value.status_code == 503


def test_scheduler_trigger_rejects_invalid_token(monkeypatch) -> None:
    monkeypatch.setattr(
        internal_connector_ai,
        "get_settings",
        lambda: SimpleNamespace(connector_ai_scheduler_token="expected"),
    )
    with pytest.raises(HTTPException) as error:
        internal_connector_ai.evaluate_connector_changes("wrong", object(), object())
    assert error.value.status_code == 401


def test_scheduler_trigger_runs_due_evaluations(monkeypatch) -> None:
    monkeypatch.setattr(
        internal_connector_ai,
        "get_settings",
        lambda: SimpleNamespace(
            connector_ai_scheduler_token="expected",
            connector_ai_evaluation_lease_seconds=60,
            connector_ai_evaluation_batch_size=5,
        ),
    )
    monkeypatch.setattr(
        internal_connector_ai,
        "ConnectorAIEvaluationService",
        _EvaluationService,
    )
    assert internal_connector_ai.evaluate_connector_changes(
        "expected", object(), object()
    ) == {"claimed": 3}
