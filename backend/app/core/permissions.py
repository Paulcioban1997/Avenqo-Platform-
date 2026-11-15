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
        "accounting:read",
        "accounting:write",
        "retail:read",
        "crm:clients:read",
        "crm:clients:write",
        "tasks:own",
        "ai:use",
        "trading:read",
    ),
    UserRole.ADMIN: (
        "users:manage",
        "modules:manage",
        "data:manage",
        "data:read",
        "crm:appointments:write",
        "crm:appointments:read",
        "crm:clients:read",
        "crm:clients:write",
        "marketing:read",
        "marketing:connect",
        "marketing:disconnect",
        "marketing:admin",
        "accounting:read",
        "retail:read",
        "tasks:own",
        "ai:use",
    ),
    UserRole.MANAGER: (
        "data:manage",
        "data:read",
        "crm:appointments:write",
        "crm:appointments:read",
        "crm:clients:read",
        "crm:clients:write",
        "marketing:read",
        "marketing:connect",
        "retail:read",
        "tasks:own",
        "ai:use",
    ),
    UserRole.ANALYST: ("data:read", "marketing:read", "accounting:read", "tasks:own", "ai:use"),
    UserRole.USER: ("tasks:own", "ai:use"),
    UserRole.VIEWER: ("data:read", "marketing:read", "tasks:own"),
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
