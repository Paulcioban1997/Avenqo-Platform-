"""Permissions simples dérivées du rôle de l'employé."""

from backend.app.models.base import UserRole

ROLE_PERMISSIONS: dict[UserRole, tuple[str, ...]] = {
    UserRole.OWNER: (
        "company:manage",
        "users:manage",
        "modules:manage",
        "billing:manage",
        "data:manage",
        "data:read",
        "crm:appointments:write",
        "crm:appointments:read",
        "marketing:read",
        "marketing:connect",
        "marketing:disconnect",
        "marketing:admin",
        "ai:use",
    ),
    UserRole.ADMIN: (
        "users:manage",
        "modules:manage",
        "data:manage",
        "data:read",
        "crm:appointments:write",
        "crm:appointments:read",
        "marketing:read",
        "marketing:connect",
        "marketing:disconnect",
        "marketing:admin",
        "ai:use",
    ),
    UserRole.MANAGER: (
        "data:manage",
        "data:read",
        "crm:appointments:write",
        "crm:appointments:read",
        "marketing:read",
        "marketing:connect",
        "ai:use",
    ),
    UserRole.ANALYST: ("data:read", "marketing:read", "ai:use"),
    UserRole.USER: ("ai:use",),
    UserRole.VIEWER: ("data:read", "marketing:read"),
}


def permissions_for(role: UserRole | str) -> tuple[str, ...]:
    """Retourne les permissions stables d'un rôle."""

    if isinstance(role, UserRole):
        resolved = role
    else:
        try:
            resolved = UserRole(str(role).strip().lower())
        except (ValueError, KeyError):
            return ()
    return ROLE_PERMISSIONS.get(resolved, ())
