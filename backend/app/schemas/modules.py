"""Public schemas for tenant business module entitlements."""

from uuid import UUID

from pydantic import BaseModel


class ModuleEntitlementResponse(BaseModel):
    key: str
    display_name: str
    description: str
    availability: str
    active: bool
    state: str
    premium: bool
    category: str
    credit_multiplier: float


class CompanyEntitlementsResponse(BaseModel):
    company_id: UUID
    plan_code: str
    active_modules: tuple[str, ...]
    module_limit: int | None
    remaining_module_slots: int | None
    modules: tuple[ModuleEntitlementResponse, ...]
