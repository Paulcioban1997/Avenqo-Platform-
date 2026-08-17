"""Crée ou met à jour un administrateur tenant sans mot de passe en argument."""

from datetime import datetime, timezone
from dataclasses import dataclass
from getpass import getpass

from sqlalchemy import select

from backend.app.core.security import hash_password
from backend.app.database import SessionLocal, create_database_tables
from backend.app.models import Company, CompanyStatus, User, UserRole


@dataclass(frozen=True, slots=True)
class ProvisionedAdmin:
    email: str
    first_name: str
    last_name: str
    role: str
    company_name: str
    subscription_plan: str


def provision_admin(
    *,
    email: str,
    password: str | None,
    first_name: str,
    last_name: str,
    company_name: str,
) -> ProvisionedAdmin:
    normalized_email = email.strip().lower()
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == normalized_email))
        if user is None:
            company = Company(
                name=company_name,
                slug="pmc-solutions-ai",
                email=normalized_email,
                country="Canada",
                timezone="America/Toronto",
                industry="Technology",
                subscription_plan="enterprise",
                status=CompanyStatus.ACTIVE,
            )
            if not password:
                raise ValueError("Un mot de passe est requis pour un nouveau compte")
            user = User(
                company=company,
                first_name=first_name,
                last_name=last_name,
                email=normalized_email,
                password_hash=hash_password(password),
                role=UserRole.OWNER,
                is_active=True,
                email_verified_at=datetime.now(timezone.utc),
            )
            session.add(user)
        else:
            user.first_name = first_name
            user.last_name = last_name
            user.role = UserRole.OWNER
            user.is_active = True
            user.email_verified_at = user.email_verified_at or datetime.now(timezone.utc)
            user.company.name = company_name
            user.company.subscription_plan = "enterprise"
            user.company.status = CompanyStatus.ACTIVE
            if password:
                user.password_hash = hash_password(password)
                now = datetime.now(timezone.utc)
                for auth_session in user.auth_sessions:
                    if auth_session.revoked_at is None:
                        auth_session.revoked_at = now
        session.commit()
        session.refresh(user)
        return ProvisionedAdmin(
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            role=user.role.value,
            company_name=user.company.name,
            subscription_plan=user.company.subscription_plan,
        )


def main() -> None:
    create_database_tables()
    email = input("Email administrateur: ").strip()
    password = getpass("Nouveau mot de passe (laisser vide pour conserver l'actuel): ")
    user = provision_admin(
        email=email,
        password=password or None,
        first_name="Paul",
        last_name="Cioban",
        company_name="PMC Solutions AI",
    )
    print(f"Compte administrateur prêt: {user.email}")


if __name__ == "__main__":
    main()