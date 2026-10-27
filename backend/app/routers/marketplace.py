from fastapi import APIRouter, Depends

from backend.app.dependencies.auth import get_current_identity
from backend.app.services.marketplace_service import marketplace_catalog

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


@router.get("")
def catalog(_: object = Depends(get_current_identity)) -> dict:
    return marketplace_catalog()
