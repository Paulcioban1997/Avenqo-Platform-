from fastapi import APIRouter, Depends

from backend.app.dependencies.subscription import require_active_subscription

from backend.app.routers.ai_chat import router as ai_chat_router
from backend.app.routers.ai_support import router as ai_support_router
from backend.app.routers.admin import router as admin_router
from backend.app.routers.assistants import router as assistants_router
from backend.app.routers.auth import router as auth_router
from backend.app.routers.billing import router as billing_router
from backend.app.routers.dashboard import router as dashboard_router
from backend.app.routers.datasets import router as datasets_router
from backend.app.routers.employees import router as employees_router
from backend.app.routers.health import router as health_router
from backend.app.routers.internal_retraining import router as internal_retraining_router
from backend.app.routers.internal_versioning import router as internal_versioning_router
from backend.app.routers.onboarding import router as onboarding_router
from backend.app.routers.retail import router as retail_router
from backend.app.routers.training import router as training_router
from backend.app.routers.tenant_business import customers_router, sales_router
from backend.app.routers.tenant_products_recommendations import (
	products_router,
	recommendations_router,
)

api_router = APIRouter()
api_router.include_router(health_router, prefix="/api/v1")
api_router.include_router(
	ai_chat_router,
	prefix="/api/v1",
	dependencies=[Depends(require_active_subscription)],
)
api_router.include_router(ai_support_router, prefix="/api/v1")
api_router.include_router(admin_router, prefix="/api/v1")
api_router.include_router(
	assistants_router,
	prefix="/api/v1",
	dependencies=[Depends(require_active_subscription)],
)
api_router.include_router(auth_router, prefix="/api/v1")
api_router.include_router(billing_router, prefix="/api/v1")
api_router.include_router(
	dashboard_router,
	prefix="/api/v1",
	dependencies=[Depends(require_active_subscription)],
)
api_router.include_router(
	sales_router,
	prefix="/api/v1",
	dependencies=[Depends(require_active_subscription)],
)
api_router.include_router(
	customers_router,
	prefix="/api/v1",
	dependencies=[Depends(require_active_subscription)],
)
api_router.include_router(
	products_router,
	prefix="/api/v1",
	dependencies=[Depends(require_active_subscription)],
)
api_router.include_router(
	recommendations_router,
	prefix="/api/v1",
	dependencies=[Depends(require_active_subscription)],
)
api_router.include_router(
	datasets_router,
	prefix="/api/v1",
	dependencies=[Depends(require_active_subscription)],
)
api_router.include_router(onboarding_router, prefix="/api/v1")
api_router.include_router(
	retail_router,
	prefix="/api/v1",
	dependencies=[Depends(require_active_subscription)],
)
api_router.include_router(
	employees_router,
	prefix="/api/v1",
	dependencies=[Depends(require_active_subscription)],
)
api_router.include_router(
	training_router,
	prefix="/api/v1",
	dependencies=[Depends(require_active_subscription)],
)

# Routeur interne (Auto Retraining Enterprise, Phase 8) : jamais sous
# `/api/v1`, jamais consommé par le frontend utilisateur.
api_router.include_router(internal_retraining_router, prefix="/internal")

# Routeur interne (Model Versioning Enterprise, Phase 9) : idem, jamais
# consommé par le frontend utilisateur.
api_router.include_router(internal_versioning_router, prefix="/internal")
