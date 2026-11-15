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

_OFFICE = ("tasks:own",)
_AGENDA = ("crm:appointments:read", "crm:appointments:write", "tasks:own")
_FRONT_DESK = ("crm:appointments:read", "crm:appointments:write", "tasks:own")
_SALES = ("crm:clients:read", "crm:appointments:read", "tasks:own")
_BOOKS = ("accounting:read", "accounting:write", "tasks:own")
_BOOKS_READ = ("accounting:read", "tasks:own")
_MARKETING = ("marketing:read", "marketing:connect", "tasks:own")
_STOCK = ("retail:read", "tasks:own")

_BY_TITLE: dict[str, tuple[str, ...]] = {
    "adjoint administratif": _AGENDA,
    "administrative assistant": _AGENDA,
    "adjoint de direction": _AGENDA,
    "adjoint à la direction": _AGENDA,
    "executive assistant": _AGENDA,
    "deputy director": _AGENDA,
    "réceptionniste": _FRONT_DESK,
    "receptionist": ("crm:appointments:read", "crm:appointments:write", "tasks:own"),
    "comptable": _BOOKS,
    "bookkeeper": _BOOKS,
    "chef comptable": _BOOKS,
    "chief accountant": _BOOKS,
    "directeur financier": _BOOKS,
    "chief financial officer": _BOOKS,
    "préposé à la facturation": _BOOKS_READ,
    "billing clerk": _BOOKS_READ,
    "responsable de la paie": _BOOKS_READ,
    "payroll lead": _BOOKS_READ,
    "contrôleur de gestion": _BOOKS_READ,
    "management controller": _BOOKS_READ,
    "auditeur interne": _BOOKS_READ,
    "internal auditor": _BOOKS_READ,
    "responsable marketing": _MARKETING,
    "marketing lead": _MARKETING,
    "directeur marketing": _MARKETING,
    "marketing director": _MARKETING,
    "conseiller aux ventes": _SALES,
    "sales advisor": _SALES,
    "responsable des ventes": _SALES,
    "sales lead": _SALES,
    "représentant commercial": _SALES,
    "sales representative": _SALES,
    "chargé de grands comptes": _SALES,
    "key account manager": _SALES,
    "technicien de service": _OFFICE,
    "service technician": _OFFICE,
    "technicien": _OFFICE,
    "technician": _OFFICE,
    "spécialiste au soutien": _OFFICE,
    "support specialist": _OFFICE,
    "magasinier": _STOCK,
    "warehouse clerk": _STOCK,
    "vice-président": ("tasks:own", "data:read"),
    "vice president": ("tasks:own", "data:read"),
    "membre du conseil, lecture seule": ("data:read", "tasks:own"),
    "board member, read only": ("data:read", "tasks:own"),
}

_JOB_TASKS: dict[str, tuple[str, ...]] = {
    "adjoint administratif": (
        "Tenir l'agenda et les suivis du bureau",
        "Préparer les documents demandés par la direction",
        "Classer les dossiers du service",
    ),
    "administrative assistant": (
        "Keep the office agenda and follow-ups",
        "Prepare the documents requested by management",
    ),
    "réceptionniste": (
        "Accueillir les rendez-vous du jour",
        "Confirmer les horaires autorisés",
    ),
    "receptionist": (
        "Welcome today's appointments",
        "Confirm the authorized schedule",
    ),
    "comptable": (
        "Vérifier les factures ouvertes",
        "Saisir les écritures du jour",
    ),
    "bookkeeper": (
        "Review the open invoices",
        "Record today's entries",
    ),
    "technicien de service": (
        "Traiter les tâches qui vous sont assignées",
    ),
    "service technician": (
        "Work on the tasks assigned to you",
    ),
}


def grants_for_responsibility(job_title: str, role: UserRole | str) -> tuple[str, ...]:
    """Le poste ouvre ses tâches, jamais tout l'espace de l'entreprise."""

    key = job_title.strip().casefold()
    preset = _BY_TITLE.get(key)
    if preset is not None:
        return preset
    if any(word in key for word in ("comptable", "finance", "paie", "facturation")):
        return _BOOKS_READ
    if "marketing" in key:
        return ("marketing:read", "tasks:own")
    if "réception" in key or "reception" in key:
        return _FRONT_DESK
    if any(word in key for word in ("vente", "commercial", "sales")):
        return _SALES
    if any(word in key for word in ("magasin", "entrepôt", "warehouse")):
        return _STOCK
    return _OFFICE


def tasks_for_responsibility(job_title: str) -> tuple[str, ...]:
    """Tâches concrètes du poste. Un titre inconnu n'en invente pas."""

    return _JOB_TASKS.get(job_title.strip().casefold(), ())


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
