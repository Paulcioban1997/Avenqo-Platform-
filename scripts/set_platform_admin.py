"""Promeut un compte Avenqo EXISTANT en `platform_admin` — remédiation V1.

Usage :
    python scripts/set_platform_admin.py --email <email>

Sécurité :
  - Ne crée JAMAIS de compte : refuse si l'email n'existe pas.
  - Ne fixe/n'affiche JAMAIS de mot de passe (aucun `admin123` par défaut).
  - `is_platform_admin` est indépendant du rôle tenant (owner/admin/...) :
    promouvoir un utilisateur ne change ni son entreprise ni son rôle tenant.
  - Écrit une entrée d'audit (`platform_admin_granted`) — jamais silencieux.

Flow attendu (voir docs/platform-admin-setup.md) :
    1. Le propriétaire crée un compte Avenqo normal (signup habituel).
    2. Cette commande est exécutée par un opérateur de confiance pour
       promouvoir CE compte précis en `platform_admin`.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from backend.app.database import SessionLocal
from backend.app.models import User
from backend.app.services.audit_log_service import AuditLogService


def set_platform_admin(email: str) -> User:
    normalized_email = email.strip().lower()
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == normalized_email))
        if user is None:
            raise ValueError(
                f"Aucun compte existant pour {normalized_email}. "
                "Créez d'abord un compte via le signup normal, puis relancez cette commande."
            )
        if user.is_platform_admin:
            raise ValueError(f"{normalized_email} est déjà platform_admin.")

        user.is_platform_admin = True
        AuditLogService(session).record(
            actor_user_id=user.id,
            action="platform_admin_granted",
            target_type="user",
            target_id=str(user.id),
            company_id=user.company_id,
            metadata={"email": normalized_email, "granted_via": "scripts/set_platform_admin.py"},
        )
        session.commit()
        session.refresh(user)
        return user


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="Email du compte Avenqo existant à promouvoir.")
    args = parser.parse_args()

    try:
        user = set_platform_admin(args.email)
    except ValueError as exc:
        print(f"ÉCHEC : {exc}", file=sys.stderr)
        return 1

    print(f"OK : {user.email} est maintenant platform_admin (id={user.id}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
