"""Production E2E Validation Script for CRM AI.
Executes real HTTP requests against running FastAPI backend (http://127.0.0.1:8000)
and validates database persistence directly in the live PostgreSQL database.
"""

import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import asyncio
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import httpx
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from backend.app.config.settings import get_settings
from backend.app.core.security import create_access_token, generate_token, hash_token
from backend.app.models.company import Company
from backend.app.models.user import User, UserRole
from backend.app.models.auth_session import AuthSession
from backend.app.models.billing import BillingAccount
from backend.app.models.crm import (
    CRMClient,
    CRMAppointment,
    CRMService,
    CRMEmployee,
    CRMCalendarConnection,
)
from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.ai.tools.business.crm_tools import (
    SearchClientsTool,
    SearchClientsArgs,
    GetClientTool,
    GetClientArgs,
    CheckAvailabilityTool,
    CheckAvailabilityArgs,
    ListAvailableSlotsTool,
    ListAvailableSlotsArgs,
    CreateAppointmentTool,
    CreateAppointmentArgs,
    UpdateAppointmentTool,
    UpdateAppointmentArgs,
    CancelAppointmentTool,
    CancelAppointmentArgs,
    GetClientHistoryTool,
    GetCRMOverviewTool,
    CRMGenericArgs,
)
from shared.ai_engine.contracts import TenantContext

BASE_URL = "http://127.0.0.1:8000/api/v1"

def create_real_auth_token(session, user: User) -> str:
    now = datetime.now(timezone.utc)
    refresh_token = generate_token()
    refresh_expires_at = now + timedelta(days=30)
    auth_session = AuthSession(
        id=uuid4(),
        user_id=user.id,
        token_hash=hash_token(refresh_token),
        created_at=now,
        expires_at=refresh_expires_at,
    )
    session.add(auth_session)
    session.commit()
    token, _ = create_access_token(user.id, user.company_id, auth_session.id)
    return token

def run_validation():
    print("=" * 80)
    print("STARTING REAL PRODUCTION E2E VALIDATION FOR CRM AI")
    print(f"Backend Target: {BASE_URL}")
    settings = get_settings()
    print(f"Database URL configured: {settings.database_url.split('@')[-1] if '@' in settings.database_url else 'configured'}")
    print("=" * 80)

    # 1. Connect to PostgreSQL and verify Alembic migration & 17 tables
    engine = create_engine(settings.database_url)
    inspector = inspect(engine)
    db_tables = inspector.get_table_names()
    
    expected_tables = [
        "crm_activities",
        "crm_activity_log",
        "crm_addresses",
        "crm_appointments",
        "crm_automations",
        "crm_calendar_connections",
        "crm_clients",
        "crm_communications",
        "crm_contacts",
        "crm_employees",
        "crm_leads",
        "crm_notes",
        "crm_opportunities",
        "crm_pipeline_stages",
        "crm_pipelines",
        "crm_reminders",
        "crm_services",
    ]
    
    missing_tables = [t for t in expected_tables if t not in db_tables]
    print(f"\n[STEP 1 - DB SCHEMA & ALEMBIC MIGRATION]")
    print(f"Found {len(db_tables)} total tables in database.")
    if missing_tables:
        print(f"FAILED: Missing CRM tables: {missing_tables}")
        sys.exit(1)
    else:
        print(f"PASSED: All 17 CRM tables exist in PostgreSQL:")
        for t in expected_tables:
            print(f"  - {t}: OK")

    # Check alembic_version
    with engine.connect() as conn:
        res = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
        current_rev = res[0] if res else None
        print(f"Alembic current revision: {current_rev}")
        assert current_rev == "0018_crm_ai_full_suite", f"Expected revision 0018_crm_ai_full_suite, got {current_rev}"
        print("PASSED: Alembic migration 0018_crm_ai_full_suite is active and verified.")

    Session = sessionmaker(bind=engine)
    session = Session()

    # 2. Setup / Retrieve Tenant A and Tenant B
    print(f"\n[STEP 2 - TENANT SETUP]")
    # Find or create Tenant A
    tenant_a = session.query(Company).filter(Company.name == "E2E Tenant Alpha").first()
    if not tenant_a:
        tenant_a = Company(
            id=uuid4(),
            name="E2E Tenant Alpha",
            slug=f"tenant-alpha-{uuid4().hex[:6]}",
            email=f"tenant_a_{uuid4().hex[:4]}@avenqo-e2e.ca",
            country="CA",
            timezone="America/Toronto",
            industry="Healthcare",
            subscription_plan="enterprise",
        )
        session.add(tenant_a)
        session.flush()

    # Find or create Tenant B
    tenant_b = session.query(Company).filter(Company.name == "E2E Tenant Beta").first()
    if not tenant_b:
        tenant_b = Company(
            id=uuid4(),
            name="E2E Tenant Beta",
            slug=f"tenant-beta-{uuid4().hex[:6]}",
            email=f"tenant_b_{uuid4().hex[:4]}@avenqo-e2e.ca",
            country="CA",
            timezone="America/Toronto",
            industry="Retail",
            subscription_plan="enterprise",
        )
        session.add(tenant_b)
        session.flush()

    now = datetime.now(timezone.utc)
    # Create test users if needed
    user_a = session.query(User).filter(User.company_id == tenant_a.id).first()
    if not user_a:
        user_a = User(
            id=uuid4(),
            company_id=tenant_a.id,
            email=f"user_a_{uuid4().hex[:4]}@avenqo-e2e.ca",
            password_hash="fakehashedpassword",
            first_name="User",
            last_name="Alpha",
            role=UserRole.ADMIN,
            is_active=True,
            email_verified_at=now,
        )
        session.add(user_a)
        session.flush()
    else:
        user_a.is_active = True
        user_a.email_verified_at = now

    user_b = session.query(User).filter(User.company_id == tenant_b.id).first()
    if not user_b:
        user_b = User(
            id=uuid4(),
            company_id=tenant_b.id,
            email=f"user_b_{uuid4().hex[:4]}@avenqo-e2e.ca",
            password_hash="fakehashedpassword",
            first_name="User",
            last_name="Beta",
            role=UserRole.ADMIN,
            is_active=True,
            email_verified_at=now,
        )
        session.add(user_b)
        session.flush()
    else:
        user_b.is_active = True
        user_b.email_verified_at = now

    billing_a = session.query(BillingAccount).filter(BillingAccount.company_id == tenant_a.id).first()
    if not billing_a:
        billing_a = BillingAccount(
            id=uuid4(),
            company_id=tenant_a.id,
            plan_code="enterprise",
            status="active",
            current_period_end=now + timedelta(days=365),
        )
        session.add(billing_a)
    else:
        billing_a.status = "active"

    billing_b = session.query(BillingAccount).filter(BillingAccount.company_id == tenant_b.id).first()
    if not billing_b:
        billing_b = BillingAccount(
            id=uuid4(),
            company_id=tenant_b.id,
            plan_code="enterprise",
            status="active",
            current_period_end=now + timedelta(days=365),
        )
        session.add(billing_b)
    else:
        billing_b.status = "active"

    session.commit()

    token_a = create_real_auth_token(session, user_a)
    token_b = create_real_auth_token(session, user_b)

    headers_a = {"Authorization": f"Bearer {token_a}", "Content-Type": "application/json"}
    headers_b = {"Authorization": f"Bearer {token_b}", "Content-Type": "application/json"}

    print(f"Tenant A ID: {tenant_a.id} ({tenant_a.name})")
    print(f"Tenant B ID: {tenant_b.id} ({tenant_b.name})")

    # Clean existing test records for Tenant A and Tenant B to ensure clean run
    session.query(CRMAppointment).filter(CRMAppointment.company_id.in_([tenant_a.id, tenant_b.id])).delete(synchronize_session=False)
    session.query(CRMClient).filter(CRMClient.company_id.in_([tenant_a.id, tenant_b.id])).delete(synchronize_session=False)
    session.query(CRMEmployee).filter(CRMEmployee.company_id.in_([tenant_a.id, tenant_b.id])).delete(synchronize_session=False)
    session.query(CRMService).filter(CRMService.company_id.in_([tenant_a.id, tenant_b.id])).delete(synchronize_session=False)
    session.commit()
    print("Cleaned existing test records for Tenant A and Tenant B.")

    client_http = httpx.Client(base_url=BASE_URL, timeout=15.0)

    # 3. Verify Zero Fake KPI Values for clean tenant
    print(f"\n[STEP 3 - ZERO FAKE KPI VALUES]")
    res = client_http.get("/crm/kpis", headers=headers_a)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    kpis = res.json()
    print(f"Real KPIs for empty Tenant A: {kpis}")
    assert kpis.get("active_clients") == 0, f"Expected active_clients=0, got {kpis.get('active_clients')}"
    assert kpis.get("appointments_this_month") == 0, f"Expected appointments_this_month=0, got {kpis.get('appointments_this_month')}"
    assert kpis.get("total_revenue_generated") == 0 or kpis.get("total_revenue_generated") == 0.0, f"Expected total_revenue_generated=0, got {kpis.get('total_revenue_generated')}"
    print("PASSED: Empty tenant displays strictly 0 for active_clients, appointments_this_month, and revenue. Zero fake values.")

    # 4. Create Client "TEST TENANT A"
    print(f"\n[STEP 4 - CREATE REAL CLIENT TEST TENANT A]")
    client_payload = {
        "first_name": "TEST",
        "last_name": "TENANT A",
        "email": "test.tenant.a@production-test.ca",
        "phone": "514-555-7890",
        "company_name": "Alpha Corp",
        "notes": "Client créé pour validation E2E stricte de production",
    }
    res = client_http.post("/crm/clients", headers=headers_a, json=client_payload)
    assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.text}"
    client_a_data = res.json()
    client_a_id = client_a_data["id"]
    print(f"Created client A ID: {client_a_id} ({client_a_data.get('full_name', '')})")

    # Verify directly in PostgreSQL
    db_client = session.query(CRMClient).filter(CRMClient.id == client_a_id).first()
    assert db_client is not None, "Client not persisted in PostgreSQL!"
    assert str(db_client.company_id) == str(tenant_a.id), "Company ID mismatch in PostgreSQL!"
    print(f"PASSED: Client persisted in PostgreSQL (ID: {db_client.id}, Company: {db_client.company_id})")

    # 5. Test Global Search
    print(f"\n[STEP 5 - TEST GLOBAL SEARCH & PARTIAL MATCH]")
    # 5a. Search by full name
    res = client_http.get("/crm/search?q=TEST+TENANT+A", headers=headers_a)
    print(f"Search response status: {res.status_code}, text: {res.text}")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    search_res = res.json()
    clients_found = search_res.get("results", {}).get("clients", [])
    assert len(clients_found) >= 1, f"Expected client found by full name, got: {search_res}"
    assert clients_found[0]["id"] == client_a_id
    print("  - Search by full name 'TEST TENANT A': OK")

    # 5b. Search by partial name
    res = client_http.get("/crm/search?q=TENANT", headers=headers_a)
    assert res.status_code == 200
    search_res = res.json()
    clients_found = search_res.get("results", {}).get("clients", [])
    assert any(c["id"] == client_a_id for c in clients_found), "Expected client found by partial name 'TENANT'"
    print("  - Search by partial name 'TENANT': OK")

    # 5c. Search by email
    res = client_http.get("/crm/search?q=production-test.ca", headers=headers_a)
    assert res.status_code == 200
    search_res = res.json()
    clients_found = search_res.get("results", {}).get("clients", [])
    assert any(c["id"] == client_a_id for c in clients_found), "Expected client found by email"
    print("  - Search by email 'production-test.ca': OK")

    # 6. Multi-Tenant Security Isolation
    print(f"\n[STEP 6 - MULTI-TENANT SECURITY ISOLATION]")
    # 6a. Tenant B searches for "TEST TENANT A"
    res_b = client_http.get("/crm/search?q=TEST+TENANT+A", headers=headers_b)
    assert res_b.status_code == 200
    clients_b = res_b.json().get("results", {}).get("clients", [])
    assert len(clients_b) == 0, "SECURITY BREACH: Tenant B retrieved Tenant A's client via /crm/search!"
    print("  - Tenant B global search for 'TEST TENANT A': 0 results (PASSED)")

    # 6b. Tenant B searches by email
    res_b = client_http.get("/crm/search?q=test.tenant.a@production-test.ca", headers=headers_b)
    assert res_b.status_code == 200
    clients_b = res_b.json().get("results", {}).get("clients", [])
    assert len(clients_b) == 0, "SECURITY BREACH: Tenant B retrieved Tenant A's client via email search!"
    print("  - Tenant B search by email: 0 results (PASSED)")

    # 6c. Tenant B lists all clients
    res_b = client_http.get("/crm/clients", headers=headers_b)
    assert res_b.status_code == 200
    assert not any(c["id"] == client_a_id for c in res_b.json()), "SECURITY BREACH: Tenant B retrieved Tenant A's client in /crm/clients!"
    print("  - Tenant B /crm/clients listing: 0 items from Tenant A (PASSED)")

    # 6d. Tenant B accesses direct client ID
    res_b = client_http.get(f"/crm/clients/{client_a_id}", headers=headers_b)
    assert res_b.status_code == 404, f"SECURITY BREACH: Expected 404, got {res_b.status_code}"
    print(f"  - Tenant B direct GET /crm/clients/{client_a_id}: returned HTTP 404 Not Found without leaking existence (PASSED)")

    # 6e. Tenant B invokes Copilot tools
    ctx_b = ToolExecutionContext(
        tenant=TenantContext(company_id=tenant_b.id),
        user_id=user_b.id,
        permissions=frozenset(["ai:use"]),
        request_id="sec-b-copilot",
    )
    search_tool = SearchClientsTool(session)
    tool_res = asyncio.run(search_tool.run(ctx_b, SearchClientsArgs(query="TEST TENANT A")))
    assert tool_res.data["count"] == 0, "SECURITY BREACH: Copilot search_clients returned Tenant A data to Tenant B!"
    print("  - Tenant B Copilot search_clients(): returned 0 results (PASSED)")

    get_tool = GetClientTool(session)
    tool_get_res = asyncio.run(get_tool.run(ctx_b, GetClientArgs(client_id=client_a_id)))
    assert tool_get_res.success is False, "SECURITY BREACH: Copilot get_client allowed Tenant B to fetch Tenant A data!"
    print("  - Tenant B Copilot get_client(): rejected with success=False (PASSED)")

    # 7. Create Employee and Service for Tenant A
    print(f"\n[STEP 7 - CREATE REAL EMPLOYEE & SERVICE FOR TENANT A]")
    emp_res = client_http.post(
        "/crm/employees",
        headers=headers_a,
        json={
            "name": "Dr. Sarah Physiothérapeute",
            "email": "sarah.physio@avenqo-e2e.ca",
            "role_title": "Physiothérapeute",
            "working_hours": {
                "monday": {"start": "08:00", "end": "17:00"},
                "tuesday": {"start": "08:00", "end": "17:00"},
                "wednesday": {"start": "08:00", "end": "17:00"},
                "thursday": {"start": "08:00", "end": "17:00"},
                "friday": {"start": "08:00", "end": "17:00"},
                "saturday": {"start": "08:00", "end": "17:00"},
                "sunday": {"start": "08:00", "end": "17:00"},
            },
        },
    )
    assert emp_res.status_code == 201, f"Failed to create employee: {emp_res.text}"
    employee_a = emp_res.json()
    emp_id = employee_a["id"]
    print(f"Created Employee: {employee_a['name']} (ID: {emp_id})")

    svc_res = client_http.post(
        "/crm/services",
        headers=headers_a,
        json={
            "name": "Physiothérapie",
            "duration_minutes": 30,
            "price": 95.0,
            "color_hex": "#0ea5e9",
        },
    )
    assert svc_res.status_code == 201, f"Failed to create service: {svc_res.text}"
    service_a = svc_res.json()
    svc_id = service_a["id"]
    print(f"Created Service: {service_a['name']} (ID: {svc_id}, Duration: 30m, Price: 95.0)")

    # 8. Create Appointment & Conflict Detection Test
    print(f"\n[STEP 8 - APPOINTMENT CREATION & STRICT CONFLICT DETECTION]")
    today = datetime.now(timezone.utc).replace(hour=14, minute=30, second=0, microsecond=0)
    slot_end = today + timedelta(minutes=30) # 14:30 -> 15:00

    app_payload = {
        "client_id": client_a_id,
        "employee_id": emp_id,
        "service_id": svc_id,
        "title": "Physiothérapie",
        "start_time": today.isoformat(),
        "end_time": slot_end.isoformat(),
        "duration_minutes": 30,
        "price": 95.0,
    }

    # 8a. Create First Appointment (14:30 -> 15:00)
    res = client_http.post("/crm/appointments", headers=headers_a, json=app_payload)
    assert res.status_code == 201, f"Failed to create appointment: {res.text}"
    app1_data = res.json()
    app1_id = app1_data["id"]
    print(f"Created Appointment 1: {app1_data['title']} (ID: {app1_id}, 14:30 -> 15:00)")

    # Verify directly in PostgreSQL
    db_app = session.query(CRMAppointment).filter(CRMAppointment.id == app1_id).first()
    assert db_app is not None, "Appointment 1 not found in PostgreSQL!"
    assert str(db_app.company_id) == str(tenant_a.id)
    print(f"PASSED: Appointment 1 persisted in PostgreSQL (ID: {db_app.id}, Status: {db_app.status})")

    # 8b. Attempt Overlapping Appointment for SAME EMPLOYEE (14:45 -> 15:15)
    conflict_start = today + timedelta(minutes=15) # 14:45
    conflict_end = conflict_start + timedelta(minutes=30) # 15:15
    conflict_payload = {
        "client_id": client_a_id,
        "employee_id": emp_id,
        "service_id": svc_id,
        "title": "Physiothérapie Conflit",
        "start_time": conflict_start.isoformat(),
        "end_time": conflict_end.isoformat(),
        "duration_minutes": 30,
        "price": 95.0,
    }

    conflict_res = client_http.post("/crm/appointments", headers=headers_a, json=conflict_payload)
    print(f"Conflict response code: {conflict_res.status_code}")
    print(f"Conflict response body: {conflict_res.text}")
    assert conflict_res.status_code in (400, 409), f"Expected HTTP 400 or 409 Conflict, got {conflict_res.status_code}"
    conflict_json = conflict_res.json()
    err_msg = conflict_json.get("error", {}).get("message") or conflict_json.get("detail", "")
    assert "Conflit" in err_msg, f"Expected 'Conflit' in error message, got: {conflict_json}"
    print(f"PASSED: Overlapping appointment rejected with conflict message: '{err_msg}'")

    # Confirm NO duplicate record persisted in PostgreSQL
    conflicting_db_apps = session.query(CRMAppointment).filter(
        CRMAppointment.company_id == tenant_a.id,
        CRMAppointment.title == "Physiothérapie Conflit"
    ).all()
    assert len(conflicting_db_apps) == 0, "FAILURE: Conflicting appointment was wrongly persisted in PostgreSQL!"
    print("PASSED: Zero conflicting duplicate records persisted in PostgreSQL.")

    # 9. Availability Engine Test
    print(f"\n[STEP 9 - AVAILABILITY ENGINE TEST]")
    avail_res = client_http.get(
        f"/crm/availability/slots?target_date={today.date().isoformat()}&duration_minutes=30&employee_id={emp_id}",
        headers=headers_a,
    )
    assert avail_res.status_code == 200, f"Availability query failed: {avail_res.text}"
    avail_data = avail_res.json()
    slots = avail_data.get("slots", [])
    # Check that 14:30 is NOT available
    slot_1430_available = any("14:30" in s["start_time"] for s in slots)
    assert not slot_1430_available, f"Availability engine returned 14:30 as free while Dr. Sarah is booked!"
    print(f"PASSED: Availability engine correctly marks 14:30 as occupied. Available slots count: {len(slots)}")

    # 10. Bidirectional Modification Test
    print(f"\n[STEP 10 - APPOINTMENT MODIFICATION (14:30 -> 15:30)]")
    new_start = today + timedelta(hours=1) # 15:30
    new_end = new_start + timedelta(minutes=30) # 16:00
    put_res = client_http.put(
        f"/crm/appointments/{app1_id}",
        headers=headers_a,
        json={"start_time": new_start.isoformat(), "end_time": new_end.isoformat()},
    )
    assert put_res.status_code == 200, f"Failed to modify appointment: {put_res.text}"
    updated_app = put_res.json()
    print(f"Modified appointment start: {updated_app['start_time']}")

    # Verify update in DB
    session.expire_all()
    db_updated = session.query(CRMAppointment).filter(CRMAppointment.id == app1_id).first()
    assert db_updated.start_time.hour == 15 and db_updated.start_time.minute == 30
    print(f"PASSED: Database updated start_time to {db_updated.start_time} (15:30 -> 16:00).")

    # 11. Real Copilot AI Tools Validation
    print(f"\n[STEP 11 - COPILOT AI TOOLS EXECUTION]")
    ctx_a = ToolExecutionContext(
        tenant=TenantContext(company_id=tenant_a.id),
        user_id=user_a.id,
        permissions=frozenset(["ai:use"]),
        request_id="copilot-a-test",
    )

    # 11a. Check availability tool (for specific time)
    check_tool = CheckAvailabilityTool(session)
    chk_res = asyncio.run(check_tool.run(ctx_a, CheckAvailabilityArgs(
        start_time=today.isoformat(),
        duration_minutes=30,
        employee_id=str(emp_id),
    )))
    assert chk_res.success is True
    print(f"  - CheckAvailabilityTool executed successfully: available={chk_res.data.get('available')}")

    # 11b. List available slots tool: 'Trouve-moi mes créneaux libres demain'
    tomorrow = (today + timedelta(days=1)).date()
    slots_tool = ListAvailableSlotsTool(session)
    slots_res = asyncio.run(slots_tool.run(ctx_a, ListAvailableSlotsArgs(
        target_date=tomorrow.isoformat(),
        employee_id=str(emp_id),
    )))
    assert slots_res.success is True
    print(f"  - ListAvailableSlotsTool ('Trouve-moi mes créneaux libres demain'): found {slots_res.data['count']} slots")

    # 11c. Client history tool: 'Historique et fiche 360'
    history_tool = GetClientHistoryTool(session)
    history_res = asyncio.run(history_tool.run(ctx_a, GetClientArgs(client_id=str(client_a_id))))
    assert history_res.success is True
    print(f"  - GetClientHistoryTool ('Client 360'): retrieved client {history_res.data.get('full_name')}")

    # 11d. Create appointment via Copilot tool: 'Crée un rendez-vous...'
    create_tool = CreateAppointmentTool(session)
    copilot_time = today + timedelta(days=2)
    cop_create_res = asyncio.run(create_tool.run(ctx_a, CreateAppointmentArgs(
        client_name_or_id="TEST TENANT A",
        title="Physiothérapie Séance IA",
        start_time=copilot_time.isoformat(),
        duration_minutes=30,
    )))
    assert cop_create_res.success is True
    cop_app_id = cop_create_res.data["id"]
    print(f"  - CreateAppointmentTool executed successfully: created app ID {cop_app_id}")

    # Confirm in DB
    db_cop_app = session.query(CRMAppointment).filter(CRMAppointment.id == cop_app_id).first()
    assert db_cop_app is not None
    print(f"  - Verified AI-created appointment persisted in PostgreSQL: {db_cop_app.title}")

    # 11e. Update appointment tool: 'Déplace le rendez-vous de physiothérapie'
    update_tool = UpdateAppointmentTool(session)
    moved_time = copilot_time + timedelta(hours=2)
    upd_res = asyncio.run(update_tool.run(ctx_a, UpdateAppointmentArgs(
        appointment_id=str(cop_app_id),
        new_start_time=moved_time.isoformat(),
        new_duration_minutes=45,
    )))
    assert upd_res.success is True
    print(f"  - UpdateAppointmentTool ('Déplace le rendez-vous'): successfully moved to {moved_time}")

    # 11f. Cancel appointment tool: 'Annule le rendez-vous de physiothérapie'
    cancel_tool = CancelAppointmentTool(session)
    canc_res = asyncio.run(cancel_tool.run(ctx_a, CancelAppointmentArgs(
        appointment_id=str(cop_app_id),
        reason="Annulation demandée par le client",
    )))
    assert canc_res.success is True
    print(f"  - CancelAppointmentTool ('Annule le rendez-vous'): status={canc_res.data.get('status')}")

    # 11g. Get CRM Overview Tool
    overview_tool = GetCRMOverviewTool(session)
    over_res = asyncio.run(overview_tool.run(ctx_a, CRMGenericArgs()))
    assert over_res.success is True
    print(f"  - GetCRMOverviewTool executed successfully: total_leads={over_res.data.get('total_leads')}, pipeline_value={over_res.data.get('total_pipeline_value')}")

    # 12. Google Calendar OAuth Failure / Missing Credentials State
    print(f"\n[STEP 12 - GOOGLE CALENDAR CONNECTION & FAILURE / MISSING CREDENTIALS TEST]")
    # 12a. Check calendar connection endpoint for unconfigured tenant
    cal_res = client_http.get("/crm/calendar/connection", headers=headers_a)
    assert cal_res.status_code == 200, f"Expected 200, got {cal_res.status_code}: {cal_res.text}"
    cal_conn = cal_res.json()
    print(f"Real calendar connection for clean Tenant A: {cal_conn}")
    assert cal_conn.get("connected") is False, "Expected connected=False for unconfigured tenant"
    assert cal_conn.get("sync_status") != "connected", "Must NOT display 'connected'/'Synchronisé' when unconfigured"
    print("PASSED: Calendar connection endpoint returns real disconnected state (no fake 'Synchronisé').")

    # 12b. Attempt to retrieve Google OAuth URL
    oauth_res = client_http.get("/crm/calendar/google/auth-url", headers=headers_a)
    assert oauth_res.status_code == 200
    auth_url = oauth_res.json().get("auth_url", "")
    print(f"Generated Google OAuth URL: {auth_url[:70]}...")

    # 12c. Test invalid/revoked token behavior: save a revoked connection in DB
    revoked_conn = session.query(CRMCalendarConnection).filter(CRMCalendarConnection.company_id == tenant_a.id).first()
    if not revoked_conn:
        revoked_conn = CRMCalendarConnection(
            id=uuid4(),
            company_id=tenant_a.id,
            provider="google",
            account_email="expired-user@avenqo.ca",
            calendar_id="primary",
            encrypted_credentials="revoked_fake_payload",
            sync_status="error",
            last_synced_at=datetime.now(timezone.utc) - timedelta(days=7),
        )
        session.add(revoked_conn)
    else:
        revoked_conn.sync_status = "error"
    session.commit()

    err_cal_res = client_http.get("/crm/calendar/connection", headers=headers_a)
    assert err_cal_res.status_code == 200
    err_conn_data = err_cal_res.json()
    print(f"Revoked/Error connection state: {err_conn_data}")
    assert err_conn_data.get("connected") is False, "Must NOT show connected when sync_status is error"
    assert err_conn_data.get("sync_status") == "error", "Must show 'error' state for revoked connection"
    print("PASSED: Revoked/error connection correctly shows error state requiring reconnection (no fake 'Synchronisé').")

    # 12d. Disconnect calendar
    disc_res = client_http.post("/crm/calendar/disconnect", headers=headers_a)
    assert disc_res.status_code == 200
    print(f"Disconnected response: {disc_res.json()}")
    disc_status_res = client_http.get("/crm/calendar/connection", headers=headers_a)
    assert disc_status_res.json().get("sync_status") == "disconnected"
    print("PASSED: Disconnect action transitions connection to 'disconnected' status.")

    print("\n" + "=" * 80)
    print("ALL REAL PRODUCTION E2E VALIDATION TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 80)

if __name__ == "__main__":
    run_validation()
