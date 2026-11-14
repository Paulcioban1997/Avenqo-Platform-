"""Permissions figées par invitation.

Un titre propose un accès limité. Il ne donne jamais l'administration
complète. Les droits enregistrés sur le compte remplacent ceux du rôle.
Un compte sans liste enregistrée conserve les droits de son rôle, pour
que les propriétaires déjà en place ne perdent rien.
"""

from __future__ import annotations

import json

from backend.app.core.permissions import permissions_for
from backend.app.models.base import UserRole

_OWNER_ONLY = frozenset({"company:manage", "billing:manage"})

_BY_TITLE: dict[str, tuple[str, ...]] = {
    "réceptionniste": ("crm:appointments:read", "crm:appointments:write", "tasks:own"),
    "receptionist": ("crm:appointments:read", "crm:appointments:write", "tasks:own"),
    "comptable": ("accounting:read", "accounting:write", "data:read", "tasks:own"),
    "bookkeeper": ("accounting:read", "accounting:write", "data:read", "tasks:own"),
    "chef comptable": ("accounting:read", "accounting:write", "data:read", "tasks:own"),
    "chief accountant": ("accounting:read", "accounting:write", "data:read", "tasks:own"),
    "directeur financier": ("accounting:read", "accounting:write", "data:read", "tasks:own"),
    "chief financial officer": ("accounting:read", "accounting:write", "data:read", "tasks:own"),
    "préposé à la facturation": ("accounting:read", "tasks:own"),
    "billing clerk": ("accounting:read", "tasks:own"),
    "responsable de la paie": ("accounting:read", "data:read", "tasks:own"),
    "payroll lead": ("accounting:read", "data:read", "tasks:own"),
    "contrôleur de gestion": ("accounting:read", "data:read", "tasks:own"),
    "management controller": ("accounting:read", "data:read", "tasks:own"),
    "responsable marketing": ("marketing:read", "marketing:connect", "marketing:admin", "tasks:own"),
    "marketing lead": ("marketing:read", "marketing:connect", "marketing:admin", "tasks:own"),
    "directeur marketing": ("marketing:read", "marketing:connect", "marketing:admin", "tasks:own"),
    "marketing director": ("marketing:read", "marketing:connect", "marketing:admin", "tasks:own"),
    "technicien de service": ("tasks:own",),
    "service technician": ("tasks:own",),
    "technicien": ("tasks:own",),
    "technician": ("tasks:own",),
    "spécialiste au soutien": ("tasks:own",),
    "support specialist": ("tasks:own",),
    "magasinier": ("retail:read", "tasks:own"),
    "warehouse clerk": ("retail:read", "tasks:own"),
    "auditeur interne": ("data:read", "accounting:read", "tasks:own"),
    "internal auditor": ("data:read", "accounting:read", "tasks:own"),
    "membre du conseil, lecture seule": ("data:read", "tasks:own"),
    "board member, read only": ("data:read", "tasks:own"),
}


def grants_for_responsibility(job_title: str, role: UserRole | str) -> tuple[str, ...]:
    """Propose un accès à partir du titre, sinon le rôle sans les droits du propriétaire."""

    preset = _BY_TITLE.get(job_title.strip().casefold())
    if preset is not None:
        return preset
    limited = [item for item in permissions_for(role) if item not in _OWNER_ONLY]
    return tuple(limited)


def cap_grants(requested: tuple[str, ...] | list[str], actor_permissions: tuple[str, ...] | set[str]) -> tuple[str, ...]:
    """Retire tout droit que l'auteur de l'invitation ne possède pas lui-même."""

    allowed = set(actor_permissions)
    return tuple(item for item in requested if item in allowed)


def encode_grants(grants: tuple[str, ...] | list[str]) -> str:
    return json.dumps(list(grants), ensure_ascii=False)


def decode_grants(raw: str | None) -> tuple[str, ...] | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    return tuple(str(item) for item in data if isinstance(item, str))


def effective_permissions(user: object) -> tuple[str, ...]:
    """Droits réellement appliqués. Une liste vide enregistrée n'accorde rien."""

    stored = decode_grants(getattr(user, "permission_grants", None))
    if stored is None:
        return permissions_for(getattr(user, "role", None))
    return stored
