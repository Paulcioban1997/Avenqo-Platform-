"""Bootstrap sécurisé du compte platform_admin propriétaire d'Avenqo.

Usage :
    python scripts/bootstrap_platform_admin.py

Lit PLATFORM_ADMIN_EMAIL / PLATFORM_ADMIN_PASSWORD depuis backend/.env (jamais
committé — voir docs/platform-admin-setup.md). Idempotent : relancer la
commande ne crée jamais de doublon, confirme simplement le rôle. N'imprime
jamais le mot de passe ni son hash.

Sécurité :
  - Le mot de passe est validé avec la même politique que le signup normal.
  - Le mot de passe est haché avec le service de hachage existant
    (`backend.app.core.security.hash_password`) avant tout stockage.
  - Le compte est rattaché à une entreprise technique interne dédiée
    ("Avenqo (Platform)") : il ne devient JAMAIS automatiquement membre
    d'une entreprise cliente existante.
  - Chaque exécution écrit une entrée d'audit (jamais silencieux).
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from sqlalchemy import select

from backend.app.config.settings import get_settings
from backend.app.core.security import hash_password
from backend.app.database import SessionLocal
from backend.app.models import Company, CompanyStatus, User, UserRole
from backend.app.schemas.auth import RegisterRequest
from backend.app.services.audit_log_service import AuditLogService

_PLATFORM_COMPANY_SLUG = "avenqo-platform"
_PLATFORM_COMPANY_EMAIL = "platform-admin@avenqo.internal"


class BootstrapError(ValueError):
    """Erreur volontairement générique — ne révèle jamais les identifiants."""


def _get_or_create_platform_company(session) -> Company:
    company = session.scalar(select(Company).where(Company.slug == _PLATFORM_COMPANY_SLUG))
    if company is not None:
        return company
    company = Company(
        name="Avenqo (Platform)",
        slug=_PLATFORM_COMPANY_SLUG,
        email=_PLATFORM_COMPANY_EMAIL,
        country="Canada",
        timezone="America/Toronto",
        industry="Avenqo Platform Operations",
        subscription_plan="enterprise",
        status=CompanyStatus.ACTIVE,
    )
    session.add(company)
    session.flush()
    return company


def bootstrap_platform_admin() -> tuple[User, bool]:
    """Crée ou confirme le compte platform_admin. Retourne (user, created)."""

    settings = get_settings()
    email = (settings.platform_admin_email or "").strip().lower()
    password = settings.platform_admin_password or ""
    if not email:
        raise BootstrapError("PLATFORM_ADMIN_EMAIL n'est pas configuré (backend/.env).")
    if not password:
        raise BootstrapError("PLATFORM_ADMIN_PASSWORD n'est pas configuré (backend/.env).")
    try:
        RegisterRequest.validate_password(password)
    except ValueError as exc:
        raise BootstrapError(str(exc)) from exc

    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email))
        created = False
        if user is None:
            company = _get_or_create_platform_company(session)
            user = User(
                company=company,
                first_name="Avenqo",
                last_name="Owner",
                email=email,
                password_hash=hash_password(password),
                role=UserRole.OWNER,
                is_active=True,
                is_platform_admin=True,
                email_verified_at=datetime.now(timezone.utc),
            )
            session.add(user)
            session.flush()
            created = True
            action = "platform_admin_bootstrapped"
        else:
            if not user.is_platform_admin:
                user.is_platform_admin = True
            action = "platform_admin_confirmed"

        AuditLogService(session).record(
            actor_user_id=user.id,
            action=action,
            target_type="user",
            target_id=str(user.id),
            company_id=user.company_id,
            metadata={"email": email, "granted_via": "scripts/bootstrap_platform_admin.py"},
        )
        session.commit()
        session.refresh(user)
        return user, created


def main() -> int:
    try:
        user, created = bootstrap_platform_admin()
    except BootstrapError as exc:
        print(f"ÉCHEC : {exc}", file=sys.stderr)
        return 1

    status = "créé" if created else "existant, rôle confirmé"
    print(f"OK : compte platform_admin {status} (id={user.id}). Identifiants jamais affichés.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
