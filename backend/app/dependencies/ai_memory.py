from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.ai.memory.service import AvenqoMemoryService
from backend.app.config.settings import Settings, get_settings
from backend.app.database import get_db


def get_memory_service(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AvenqoMemoryService:
    return AvenqoMemoryService(db, settings)
