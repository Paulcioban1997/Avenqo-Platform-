"""Durable connector-generation evaluation with database leases."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models import ConnectorDatasetEvaluation, DatasetEvaluationStatus
from backend.app.services.training_dispatcher import TrainingDispatcher
from shared.ai_engine.contracts import TenantContext

logger = logging.getLogger(__name__)


class ConnectorAIEvaluationService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        dispatcher: TrainingDispatcher,
        *,
        lease_seconds: int = 900,
        batch_size: int = 20,
    ) -> None:
        self._session_factory = session_factory
        self._dispatcher = dispatcher
        self._lease_seconds = lease_seconds
        self._batch_size = batch_size

    def run_due(self) -> int:
        claims = self._claim_due()
        for evaluation_id, lease_token in claims:
            self._process(evaluation_id, lease_token)
        return len(claims)

    def _claim_due(self) -> list[tuple[UUID, UUID]]:
        now = datetime.now(timezone.utc)
        session = self._session_factory()
        try:
            candidates = session.scalars(
                select(ConnectorDatasetEvaluation)
                .where(
                    ConnectorDatasetEvaluation.due_at <= now,
                    or_(
                        ConnectorDatasetEvaluation.status.in_(
                            (
                                DatasetEvaluationStatus.PENDING,
                                DatasetEvaluationStatus.FAILED,
                            )
                        ),
                        (
                            (ConnectorDatasetEvaluation.status == DatasetEvaluationStatus.CLAIMED)
                            & (ConnectorDatasetEvaluation.lease_expires_at < now)
                        ),
                    ),
                )
                .order_by(
                    ConnectorDatasetEvaluation.company_id,
                    ConnectorDatasetEvaluation.connection_id,
                    ConnectorDatasetEvaluation.dataset_id,
                    ConnectorDatasetEvaluation.dataset_generation.desc(),
                )
                .with_for_update(skip_locked=True)
            ).all()
            claims: list[tuple[UUID, UUID]] = []
            seen: set[tuple[UUID, UUID, UUID]] = set()
            for evaluation in candidates:
                key = (
                    evaluation.company_id,
                    evaluation.connection_id,
                    evaluation.dataset_id,
                )
                if key in seen:
                    evaluation.status = DatasetEvaluationStatus.COALESCED
                    evaluation.evaluated_at = now
                    evaluation.decision = "coalesced"
                    evaluation.reason = "newer_generation_pending"
                    continue
                if len(claims) >= self._batch_size:
                    continue
                seen.add(key)
                token = uuid4()
                evaluation.status = DatasetEvaluationStatus.CLAIMED
                evaluation.lease_token = token
                evaluation.lease_expires_at = now + timedelta(seconds=self._lease_seconds)
                evaluation.attempt_count += 1
                claims.append((evaluation.id, token))
            session.commit()
            return claims
        finally:
            session.close()

    def _process(self, evaluation_id: UUID, lease_token: UUID) -> None:
        session = self._session_factory()
        try:
            evaluation = session.scalar(
                select(ConnectorDatasetEvaluation).where(
                    ConnectorDatasetEvaluation.id == evaluation_id,
                    ConnectorDatasetEvaluation.status == DatasetEvaluationStatus.CLAIMED,
                    ConnectorDatasetEvaluation.lease_token == lease_token,
                )
            )
            if evaluation is None:
                return
            company_id = evaluation.company_id
            connection_id = evaluation.connection_id
            dataset_id = evaluation.dataset_id
            generation = evaluation.dataset_generation
        finally:
            session.close()

        try:
            result = self._dispatcher.evaluate_connector_dataset(
                TenantContext(company_id=company_id),
                dataset_id,
                generation,
                connection_id,
            )
        except Exception:
            logger.exception(
                "Connector AI evaluation failed company=%s connection=%s dataset=%s generation=%s",
                company_id,
                connection_id,
                dataset_id,
                generation,
            )
            self._finish(
                evaluation_id,
                lease_token,
                status=DatasetEvaluationStatus.FAILED,
                decision="retry",
                reason="evaluation_failed",
                retry=True,
            )
            return

        self._finish(
            evaluation_id,
            lease_token,
            status=DatasetEvaluationStatus.COMPLETED,
            decision=str(result["decision"]),
            reason=str(result["reason"]),
            drift_metrics=dict(result["drift"]),
            ai_job_ids=list(result["ai_job_ids"]),
        )

    def _finish(
        self,
        evaluation_id: UUID,
        lease_token: UUID,
        *,
        status: DatasetEvaluationStatus,
        decision: str,
        reason: str,
        drift_metrics: dict | None = None,
        ai_job_ids: list | None = None,
        retry: bool = False,
    ) -> None:
        now = datetime.now(timezone.utc)
        session = self._session_factory()
        try:
            session.execute(
                update(ConnectorDatasetEvaluation)
                .where(
                    ConnectorDatasetEvaluation.id == evaluation_id,
                    ConnectorDatasetEvaluation.lease_token == lease_token,
                )
                .values(
                    status=status,
                    evaluated_at=now,
                    decision=decision,
                    reason=reason,
                    drift_metrics=drift_metrics,
                    ai_job_ids=ai_job_ids,
                    lease_token=None,
                    lease_expires_at=None,
                    due_at=now + timedelta(minutes=5) if retry else now,
                )
            )
            session.commit()
        finally:
            session.close()