"""One-shot entry point for the connector AI evaluation cron service."""

from __future__ import annotations

import logging

from backend.app.config.settings import get_settings
from backend.app.core.logging import configure_logging
from backend.app.database.session import get_session_factory
from backend.app.services.connector_ai_evaluation_service import (
    ConnectorAIEvaluationService,
)
from backend.app.services.training_subprocess import (
    _build_dispatcher,
    launch_training_subprocess,
)
from shared.ai_engine.jobs.models import AIEngineJob

logger = logging.getLogger(__name__)


class _SubprocessScheduler:
    def enqueue(self, job: AIEngineJob) -> str:
        launch_training_subprocess(job)
        return str(job.id)

    def schedule(self, job: AIEngineJob, run_at) -> str:
        return self.enqueue(job)


def run_once() -> int:
    settings = get_settings()
    dispatcher = _build_dispatcher()
    dispatcher.attach_scheduler(_SubprocessScheduler())
    service = ConnectorAIEvaluationService(
        get_session_factory(),
        dispatcher,
        lease_seconds=settings.connector_ai_evaluation_lease_seconds,
        batch_size=settings.connector_ai_evaluation_batch_size,
    )
    processed = service.run_due()
    logger.info("Connector AI evaluation cycle completed claimed=%s", processed)
    return processed


def main() -> int:
    configure_logging(get_settings().log_level)
    run_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())