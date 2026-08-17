"""Contrats des droits d'accÃ¨s partagÃ©s par tous les modules Avenqo."""

from typing import Protocol

from shared.ai_engine.contracts import TenantContext


class ModuleAccessDenied(PermissionError):
    """Signale qu'une entreprise tente d'utiliser un module non activÃ©."""


class ModuleEntitlementReader(Protocol):
    """Lit les droits d'accÃ¨s sans exposer leur technologie de stockage."""

    def is_active(self, tenant: TenantContext, module_code: str) -> bool: ...


class ModuleAccessService:
    """Applique un refus par dÃ©faut Ã  chaque opÃ©ration d'un module."""

    def __init__(self, entitlements: ModuleEntitlementReader) -> None:
        self._entitlements = entitlements

    def require_active(self, tenant: TenantContext, module_code: str) -> None:
        if not self._entitlements.is_active(tenant, module_code):
            raise ModuleAccessDenied(
                f"Module '{module_code}' is not active for this company"
            )


class InMemoryModuleEntitlements:
    """Stocke les droits d'accÃ¨s pour les tests et le dÃ©veloppement local."""

    def __init__(self) -> None:
        self._active: set[tuple[object, str]] = set()

    def activate(self, tenant: TenantContext, module_code: str) -> None:
        self._active.add((tenant.company_id, module_code))

    def deactivate(self, tenant: TenantContext, module_code: str) -> None:
        self._active.discard((tenant.company_id, module_code))

    def is_active(self, tenant: TenantContext, module_code: str) -> bool:
        return (tenant.company_id, module_code) in self._active
