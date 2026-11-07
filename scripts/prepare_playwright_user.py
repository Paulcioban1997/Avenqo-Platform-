import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4
from dotenv import dotenv_values
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.core.security import hash_password
from backend.app.models.base import CompanyStatus, UserRole
from backend.app.models.billing import BillingAccount
from backend.app.models.company import Company
from backend.app.models.company_membership import CompanyMembership
from backend.app.models.user import User
from backend.app.models.ai_usage import TenantAICreditBalance
from backend.app.models.crm import CRMAppointment, CRMClient, CRMEmployee, CRMService as CRMServiceModel
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from shared.ai_engine.contracts import TenantContext

vals = dotenv_values("backend/.env")
db_url = vals.get("DATABASE_URL") or os.environ.get("DATABASE_URL", "")
if db_url.startswith("postgres://"):
    db_url = "postgresql://" + db_url[len("postgres://"):]

engine = create_engine(db_url, pool_pre_ping=True)
Session = sessionmaker(bind=engine)
db = Session()

email = "alex.physio.sandbox@avenqo.ca"
user = db.scalar(select(User).where(User.email == email))

if user is None:
    company = Company(
        name="Avenqo Physio Clinic Sandbox",
        slug="avenqo-physio-sandbox",
        email="clinic.sandbox@avenqo.ca",
        country="Canada",
        timezone="America/Toronto",
        industry="physiotherapy",
        subscription_plan="professional",
        status=CompanyStatus.ACTIVE,
        business_hours={
            "weekly": {
                "monday": [{"open": "09:00", "close": "12:00"}, {"open": "13:00", "close": "17:00"}],
                "tuesday": [{"open": "09:00", "close": "12:00"}, {"open": "13:00", "close": "17:00"}],
                "wednesday": [{"open": "09:00", "close": "12:00"}, {"open": "13:00", "close": "17:00"}],
                "thursday": [{"open": "09:00", "close": "12:00"}, {"open": "13:00", "close": "17:00"}],
                "friday": [{"open": "09:00", "close": "12:00"}, {"open": "13:00", "close": "17:00"}],
                "saturday": [],
                "sunday": [],
            }
        },
    )
    db.add(company)
    db.flush()

    e2e_pass = os.environ.get("AVENQO_E2E_PASSWORD")
    if not e2e_pass:
        raise ValueError("AVENQO_E2E_PASSWORD environment variable is required")
    user = User(
        company_id=company.id,
        first_name="Dr. Alex",
        last_name="Therapist",
        email=email,
        password_hash=hash_password(e2e_pass),
        role=UserRole.OWNER,
        phone="+15145558989",
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()

    membership = CompanyMembership(
        company_id=company.id,
        user_id=user.id,
        role=user.role,
        is_active=True,
    )
    db.add(membership)

    ba = BillingAccount(
        company_id=company.id,
        plan_code="professional",
        status="active",
        current_period_end=datetime.now(timezone.utc) + timedelta(days=365),
    )
    db.add(ba)

    credit = TenantAICreditBalance(
        company_id=company.id,
        monthly_period=datetime.now(timezone.utc).strftime("%Y-%m"),
        monthly_used=2,
        purchased_balance=0,
    )
    db.add(credit)
    db.commit()
else:
    e2e_pass = os.environ.get("AVENQO_E2E_PASSWORD")
    if not e2e_pass:
        raise ValueError("AVENQO_E2E_PASSWORD environment variable is required")
    company = user.company
    user.password_hash = hash_password(e2e_pass)
    user.email_verified_at = datetime.now(timezone.utc)
    user.is_active = True
    user.phone = "+15145558989"
    db.commit()

# Activate modules
ent = ModuleEntitlementService(db)
tenant = TenantContext(company.id, user.id)
for mod in ["crm", "ocr", "legal", "workflow", "voice"]:
    try:
        ent.activate_module(tenant, mod)
    except Exception as exc:
        print(f"Module {mod}: {exc}")
db.commit()

# Ensure CRM service, employee, client, and appointment exist
srv = db.scalar(select(CRMServiceModel).where(CRMServiceModel.company_id == company.id, CRMServiceModel.name == "Physiothérapie"))
if not srv:
    srv = CRMServiceModel(
        id=uuid4(),
        company_id=company.id,
        name="Physiothérapie",
        duration_minutes=60,
        price=120.0,
        is_active=True,
    )
    db.add(srv)

emp = db.scalar(select(CRMEmployee).where(CRMEmployee.company_id == company.id, CRMEmployee.name == "Test Practitioner"))
if not emp:
    emp = CRMEmployee(
        id=uuid4(),
        company_id=company.id,
        name="Test Practitioner",
        email="practitioner@avenqo.ca",
        role_title="Physiothérapeute en chef",
        is_active=True,
    )
    db.add(emp)

cli = db.scalar(select(CRMClient).where(CRMClient.company_id == company.id, CRMClient.email == "jm.tremblay@example.ca"))
if not cli:
    cli = CRMClient(
        id=uuid4(),
        company_id=company.id,
        first_name="Jean-Marc",
        last_name="Tremblay",
        email="jm.tremblay@example.ca",
        phone="+15145558989",
        status="active",
    )
    db.add(cli)
db.commit()

# Seed Thursday October 22, 2026 at 09:00 appointment
appt_time = datetime(2026, 10, 22, 13, 0, tzinfo=timezone.utc)
existing_appt = db.scalar(select(CRMAppointment).where(CRMAppointment.company_id == company.id, CRMAppointment.start_time == appt_time, CRMAppointment.is_deleted.is_(False)))
if not existing_appt:
    appt = CRMAppointment(
        id=uuid4(),
        company_id=company.id,
        client_id=cli.id,
        service_id=srv.id,
        employee_id=emp.id,
        title="Physiothérapie - Jean-Marc Tremblay",
        start_time=appt_time,
        end_time=appt_time + timedelta(minutes=60),
        status="confirmed",
    )
    db.add(appt)
    db.commit()

print(f"READY: {email} / PhysioSecure123! company_id={company.id}")
db.close()
