"""Company display conversions. Original amounts are never written."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.app.dependencies.auth import CurrentIdentity, get_current_identity
from backend.app.services.fx_rates import quote_items

router = APIRouter(prefix="/fx", tags=["fx"])


class FxItem(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    amount: float
    currency: str = Field(min_length=3, max_length=8)
    on_date: str | None = Field(default=None, max_length=10)


class FxRequest(BaseModel):
    items: list[FxItem] = Field(max_length=40)


@router.post("/display")
def display_conversion(
    payload: FxRequest,
    identity: CurrentIdentity = Depends(get_current_identity),
) -> dict:
    target = getattr(identity.user.company, "display_currency", None)
    return {
        "display_currency": (target or "").upper() or None,
        "items": quote_items(target, [item.model_dump() for item in payload.items]),
    }
