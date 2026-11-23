"""Permissions simples dérivées du rôle de l'employé."""

from __future__ import annotations

from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.base import UserRole

EXECUTIVE_ROLE_NAMES: frozenset[str] = frozenset({
    "owner",
    "admin",
    "super_admin",
    "director",
    "executive",
    "manager",
})

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
        "trading:read",
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


def normalize_role(role: UserRole | str | None) -> str:
    """Normalise un rôle utilisateur ou enum Python 3.11+ en chaîne canonique minuscule.

    Gère notamment :
    - `UserRole.OWNER` -> `"owner"`
    - `"UserRole.OWNER"` (sérialisation `str(Enum)` en Python 3.11+) -> `"owner"`
    - `"OWNER"` / `" admin "` -> `"owner"` / `"admin"`
    - `None` -> `""`
    """
    if role is None:
        return ""
    if isinstance(role, UserRole):
        return str(role.value).strip().lower()
    if hasattr(role, "value"):
        raw = str(getattr(role, "value")).strip().lower()
    else:
        raw = str(role).strip().lower()
    if "." in raw:
        prefix, suffix = raw.rsplit(".", 1)
        if prefix.endswith("userrole") or prefix.endswith("role"):
            raw = suffix.strip().lower()
    return raw


def is_executive_role(role: UserRole | str | None) -> bool:
    """True si le rôle canonique vérifié autorise l'accès direction (marges, exécutif)."""
    return normalize_role(role) in EXECUTIVE_ROLE_NAMES


def resolve_verified_staff_role(
    db: Session | None,
    company_id: UUID | None,
    user_id: UUID | None,
    *,
    fallback_role: UserRole | str | None = None,
) -> str:
    """Résout le rôle canonique serveur vérifié depuis CompanyMembership + User.

    Ne se fie jamais aux affirmations verbales de l'appelant.
    """
    if db is not None and company_id is not None and user_id is not None:
        from backend.app.models.company_membership import CompanyMembership
        from backend.app.models.user import User

        membership = db.scalar(
            select(CompanyMembership).where(
                CompanyMembership.company_id == company_id,
                CompanyMembership.user_id == user_id,
                CompanyMembership.is_active.is_(True),
            )
        )
        if membership is not None and getattr(membership, "role", None) is not None:
            resolved = normalize_role(membership.role)
            if resolved:
                return resolved
        user = db.get(User, user_id)
        if user is not None and user.company_id == company_id and getattr(user, "is_active", True):
            resolved = normalize_role(getattr(user, "role", None))
            if resolved:
                return resolved
    return normalize_role(fallback_role)


def permissions_for(role: UserRole | str) -> tuple[str, ...]:
    """Retourne les permissions stables d'un rôle."""

    if isinstance(role, UserRole):
        resolved = role
    else:
        canonical = normalize_role(role)
        try:
            resolved = UserRole(canonical)
        except (ValueError, KeyError):
            return ()
    return ROLE_PERMISSIONS.get(resolved, ())
