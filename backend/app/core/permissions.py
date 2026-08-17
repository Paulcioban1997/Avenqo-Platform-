"""Permissions simples dérivées du rôle de l'employé."""

from backend.app.models.base import UserRole

ROLE_PERMISSIONS: dict[UserRole, tuple[str, ...]] = {
    UserRole.OWNER: ("company:manage", "users:manage", "modules:manage", "billing:manage", "data:manage", "ai:use"),
    UserRole.ADMIN: ("users:manage", "modules:manage", "data:manage", "ai:use"),
    UserRole.MANAGER: ("data:manage", "ai:use"),
    UserRole.ANALYST: ("data:read", "ai:use"),
    UserRole.USER: ("ai:use",),
    UserRole.VIEWER: ("data:read",),
}


def permissions_for(role: UserRole) -> tuple[str, ...]:
    """Retourne les permissions stables d'un rôle."""

    return ROLE_PERMISSIONS[role]