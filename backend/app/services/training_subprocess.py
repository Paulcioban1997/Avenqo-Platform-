"""Launches automatic training in a process isolated from the API worker."""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from uuid import UUID

from backend.app.config.settings import get_settings
from backend.app.core.logging import configure_logging
from backend.app.database.session import PROJECT_ROOT, get_session_factory
from backend.app.dependencies.ai_engine import get_model_registry_root
from backend.app.services.target_resolution_service import TargetResolutionService
from backend.app.services.training_dispatcher import TrainingDispatcher
from backend.app.services.training_execution_controls import TrainingExecutionControls
from shared.ai_engine.container import AIEngineContainer
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.jobs.models import AIEngineJob, JobState
from shared.ai_engine.model_registry.repository import FileSystemModelRepository
from shared.ai_engine.model_registry.serializer import JoblibArtifactSerializer
from shared.ai_engine.registry.registry import ModelRegistry as AIModelRegistry

logger = logging.getLogger(__name__)


def serialize_job(job: AIEngineJob) -> str:
    return json.dumps(
        {
            "id": str(job.id),
            "state": job.state.value,
            "created_at": job.created_at.astimezone(timezone.utc).isoformat(),
            "tenant_company_id": str(job.tenant.company_id),
            "module_code": job.module_code,
            "task_code": job.task_code,
            "job_type": job.job_type,
            "payload": dict(job.payload),
        }
    )


def deserialize_job(payload: str) -> AIEngineJob:
    data = json.loads(payload)
    created_at = datetime.fromisoformat(str(data["created_at"]))
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return AIEngineJob(
        tenant=TenantContext(UUID(str(data["tenant_company_id"]))),
        module_code=str(data["module_code"]),
        task_code=str(data["task_code"]),
        job_type=str(data["job_type"]),
        payload=dict(data.get("payload") or {}),
        id=UUID(str(data["id"])),
        state=JobState(str(data.get("state") or JobState.PENDING.value)),
        created_at=created_at,
    )


def launch_training_subprocess(job: AIEngineJob) -> None:
    env = os.environ.copy()
    env["AVENQO_TRAINING_SUBPROCESS"] = "1"
    command = [
        sys.executable,
        "-m",
        "backend.app.services.training_subprocess",
        "--payload",
        serialize_job(job),
    ]
    popen_kwargs: dict[str, object] = {
        "cwd": str(PROJECT_ROOT),
        "env": env,
        "stdin": subprocess.DEVNULL,
        "close_fds": os.name != "nt",
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
        )
    else:
        popen_kwargs["start_new_session"] = True
    subprocess.Popen(command, **popen_kwargs)


def _build_dispatcher() -> TrainingDispatcher:
    settings = get_settings()
    model_root = get_model_registry_root()
    training_service = AIEngineContainer(
        models=FileSystemModelRepository(model_root)
    ).training_service()
    registry = AIModelRegistry(root=model_root, serializer=JoblibArtifactSerializer())
    return TrainingDispatcher(
        session_factory=get_session_factory(),
        training_service=training_service,
        ai_model_registry=registry,
        target_resolver=TargetResolutionService(),
        execution_controls=TrainingExecutionControls.from_settings(settings),
    )


def run_serialized_job(payload: str) -> None:
    dispatcher = _build_dispatcher()
    dispatcher.run_job(deserialize_job(payload))


def main(argv: list[str] | None = None) -> int:
    configure_logging(get_settings().log_level)
    parser = argparse.ArgumentParser(description="Run one Avenqo training job")
    parser.add_argument("--payload", required=True)
    args = parser.parse_args(argv)
    run_serialized_job(args.payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
