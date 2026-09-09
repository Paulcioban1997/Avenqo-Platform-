"""Bootstrap sécurisé du compte platform_admin propriétaire d'Avenqo.

Usage :
    python scripts/bootstrap_platform_admin.py
    python scripts/bootstrap_platform_admin.py --sync-password

Lit PLATFORM_ADMIN_EMAIL / PLATFORM_ADMIN_PASSWORD depuis backend/.env (jamais
committé — voir docs/platform-admin-setup.md). N'imprime jamais le mot de
passe ni son hash.

Comportement par défaut (non destructif, idempotent) :
  - Crée le compte platform_admin s'il n'existe pas.
  - S'il existe déjà, confirme uniquement le rôle `is_platform_admin` — ne
    touche JAMAIS à `password_hash`.

Comportement avec `--sync-password` (opération explicite uniquement) :
  - Si le compte n'existe pas, le crée (identique au comportement par défaut).
  - S'il existe déjà, resynchronise son mot de passe depuis
    PLATFORM_ADMIN_PASSWORD : hache le mot de passe fourni, force
    is_active=True / is_platform_admin=True / email_verified_at renseigné,
    et révoque toutes les sessions d'authentification existantes de ce
    compte (le propriétaire doit se reconnecter avec le nouveau mot de
    passe). N'affecte aucun autre utilisateur.

Sécurité :
  - Le mot de passe est validé avec la même politique que le signup normal.
  - Le mot de passe est haché avec le service de hachage existant
    (`backend.app.core.security.hash_password`) avant tout stockage.
  - Le compte est rattaché à une entreprise technique interne dédiée
    ("Avenqo (Platform)") : il ne devient JAMAIS automatiquement membre
    d'une entreprise cliente existante.
  - Chaque exécution écrit une entrée d'audit (jamais silencieux).
  - Ce script n'agit que sur la base pointée par DATABASE_URL du process en
    cours (celle de l'environnement — sandbox ou production — dans lequel il
    est exécuté) ; il ne copie jamais d'identifiants entre environnements.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from sqlalchemy import select

from backend.app.config.settings import get_settings
from backend.app.core.security import hash_password
from backend.app.database import SessionLocal
from backend.app.models import BillingAccount, Company, CompanyStatus, User, UserRole
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


def _ensure_platform_billing_account(session, company: Company) -> BillingAccount:
    account = session.scalar(
        select(BillingAccount).where(BillingAccount.company_id == company.id)
    )
    if account is None:
        account = BillingAccount(
            company_id=company.id,
            plan_code="enterprise",
            status="active",
        )
        session.add(account)
        return account
    account.plan_code = "enterprise"
    account.status = "active"
    account.cancel_at_period_end = False
    return account


def _read_credentials() -> tuple[str, str]:
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
    return email, password


def _new_platform_admin_user(company: Company, email: str, password: str) -> User:
    return User(
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


def bootstrap_platform_admin() -> tuple[User, bool]:
    """Crée ou confirme le compte platform_admin. Retourne (user, created).

    Ne modifie JAMAIS `password_hash` d'un compte déjà existant.
    """

    email, password = _read_credentials()

    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email))
        created = False
        if user is None:
            company = _get_or_create_platform_company(session)
            user = _new_platform_admin_user(company, email, password)
            session.add(user)
            session.flush()
            created = True
            action = "platform_admin_bootstrapped"
        else:
            if user.company.slug != _PLATFORM_COMPANY_SLUG:
                raise BootstrapError(
                    "Le compte configuré n'appartient pas à l'entreprise Avenqo Platform."
                )
            company = user.company
            if not user.is_platform_admin:
                user.is_platform_admin = True
            action = "platform_admin_confirmed"

        _ensure_platform_billing_account(session, company)

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


def sync_platform_admin_password() -> tuple[User, bool]:
    """Explicit, operator-triggered credential rotation (`--sync-password`).

    Creates the account if it does not exist yet (same as the default
    behaviour). If it already exists, rewrites `password_hash` from
    PLATFORM_ADMIN_PASSWORD, forces the account into a known-good state
    (active, platform_admin, verified), and revokes every existing auth
    session so a stale session cannot outlive the credential rotation.
    Never touches any other user's account.
    """

    email, password = _read_credentials()

    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email))
        created = False
        if user is None:
            company = _get_or_create_platform_company(session)
            user = _new_platform_admin_user(company, email, password)
            session.add(user)
            session.flush()
            created = True
            action = "platform_admin_bootstrapped"
            revoked_sessions = 0
        else:
            if user.company.slug != _PLATFORM_COMPANY_SLUG:
                raise BootstrapError(
                    "Le compte configuré n'appartient pas à l'entreprise Avenqo Platform."
                )
            company = user.company
            user.password_hash = hash_password(password)
            user.is_active = True
            user.is_platform_admin = True
            if user.email_verified_at is None:
                user.email_verified_at = datetime.now(timezone.utc)
            now = datetime.now(timezone.utc)
            revoked_sessions = 0
            for auth_session in user.auth_sessions:
                if auth_session.revoked_at is None:
                    auth_session.revoked_at = now
                    revoked_sessions += 1
            action = "platform_admin_password_synced"

        _ensure_platform_billing_account(session, company)

        AuditLogService(session).record(
            actor_user_id=user.id,
            action=action,
            target_type="user",
            target_id=str(user.id),
            company_id=user.company_id,
            metadata={
                "email": email,
                "synced_via": "scripts/bootstrap_platform_admin.py --sync-password",
                "revoked_sessions": revoked_sessions,
            },
        )
        session.commit()
        session.refresh(user)
        return user, created


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sync-password",
        action="store_true",
        help=(
            "Explicit credential rotation: rewrites password_hash from "
            "PLATFORM_ADMIN_PASSWORD for an existing platform_admin account "
            "and revokes its existing sessions. Omit this flag for the "
            "non-destructive default behaviour."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.sync_password:
            user, created = sync_platform_admin_password()
        else:
            user, created = bootstrap_platform_admin()
    except BootstrapError as exc:
        print(f"ÉCHEC : {exc}", file=sys.stderr)
        return 1

    if args.sync_password:
        status = "créé" if created else "existant, mot de passe resynchronisé, sessions révoquées"
    else:
        status = "créé" if created else "existant, rôle confirmé"
    print(f"OK : compte platform_admin {status} (id={user.id}). Identifiants jamais affichés.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
