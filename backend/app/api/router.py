from fastapi import APIRouter

from backend.app.routers.ai_chat import router as ai_chat_router
from backend.app.routers.auth import router as auth_router
from backend.app.routers.billing import router as billing_router
from backend.app.routers.datasets import router as datasets_router
from backend.app.routers.employees import router as employees_router
from backend.app.routers.health import router as health_router
from backend.app.routers.internal_retraining import router as internal_retraining_router
from backend.app.routers.internal_versioning import router as internal_versioning_router
from backend.app.routers.retail import router as retail_router
from backend.app.routers.training import router as training_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/api/v1")
api_router.include_router(ai_chat_router, prefix="/api/v1")
api_router.include_router(auth_router, prefix="/api/v1")
api_router.include_router(billing_router, prefix="/api/v1")
api_router.include_router(datasets_router, prefix="/api/v1")
api_router.include_router(retail_router, prefix="/api/v1")
api_router.include_router(employees_router, prefix="/api/v1")
api_router.include_router(training_router, prefix="/api/v1")

# Routeur interne (Auto Retraining Enterprise, Phase 8) : jamais sous
# `/api/v1`, jamais consommé par le frontend utilisateur.
api_router.include_router(internal_retraining_router, prefix="/internal")

# Routeur interne (Model Versioning Enterprise, Phase 9) : idem, jamais
# consommé par le frontend utilisateur.
api_router.include_router(internal_versioning_router, prefix="/internal")
