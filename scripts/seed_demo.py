"""CrÃ©e le tenant de dÃ©monstration Avenqo de faÃ§on idempotente."""

from datetime import datetime, timezone
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.security import hash_password
from backend.app.database import SessionLocal, create_database_tables
from backend.app.models import Company, CompanyStatus, User, UserRole

DEMO_EMAIL = "demo@avenqo.ca"
DEMO_COMPANY_EMAIL = "demo-company@avenqo.ca"


def seed_demo(session: Session, password: str) -> User:
    company = session.scalar(select(Company).where(Company.email == DEMO_COMPANY_EMAIL))
    if company is None:
        company = Company(
            name="Avenqo Demo",
            slug="avenqo-demo",
            email=DEMO_COMPANY_EMAIL,
            country="Canada",
            timezone="America/Toronto",
            industry="Technology",
            subscription_plan="demo",
            status=CompanyStatus.ACTIVE,
        )
        session.add(company)
        session.flush()

    user = session.scalar(select(User).where(User.email == DEMO_EMAIL))
    if user is not None and user.company_id != company.id:
        raise RuntimeError("Le compte dÃ©mo existe dÃ©jÃ  dans un autre tenant")
    now = datetime.now(timezone.utc)
    if user is None:
        user = User(
            company=company,
            first_name="Avenqo",
            last_name="Demo",
            email=DEMO_EMAIL,
            password_hash=hash_password(password),
            role=UserRole.OWNER,
            is_active=True,
            email_verified_at=now,
        )
        session.add(user)
    else:
        user.password_hash = hash_password(password)
        user.role = UserRole.OWNER
        user.is_active = True
        user.email_verified_at = now
        for auth_session in user.auth_sessions:
            if auth_session.revoked_at is None:
                auth_session.revoked_at = now
    session.commit()
    return user


def main() -> None:
    password = os.environ.get("AVENQO_DEMO_PASSWORD")
    if not password:
        raise SystemExit("AVENQO_DEMO_PASSWORD doit Ãªtre dÃ©fini")
    create_database_tables()
    with SessionLocal() as session:
        seed_demo(session, password)
    print(f"Compte dÃ©mo prÃªt : {DEMO_EMAIL}")


if __name__ == "__main__":
    main()
