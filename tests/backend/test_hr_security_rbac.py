"""Tests complets de sécurité, RBAC, isolation multi-tenant et intégrité des données pour le module HR AI."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity
from backend.app.models.base import Base, CompanyStatus, UserRole
from backend.app.models.billing import BillingAccount
from backend.app.models.company import Company
from backend.app.models.company_module import CompanyModule, CompanyModuleStatus
from backend.app.models.user import User
from backend.app.models.voice import VoiceCallerCredential
from backend.app.models.workspace import EmployeeLeave, EmployeePerformanceReview, EmployeeSkill, EmployeeTask
from backend.app.routers.hr import router as hr_router
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from shared.ai_engine.contracts import TenantContext


@pytest.fixture
def rbac_env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'hr_security_rbac.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Entreprise Principale (Tenant A)
    company_a = Company(
        id=uuid4(),
        name="Entreprise Alpha",
        slug=f"alpha-{uuid4().hex[:6]}",
        email="contact@alpha.com",
        country="Canada",
        timezone="America/Toronto",
        subscription_plan="professional",
        industry="Automobile / Atelier",
        status=CompanyStatus.ACTIVE,
    )
    session.add(company_a)

    # Billing actif pour Tenant A
    billing_a = BillingAccount(
        company_id=company_a.id,
        plan_code="professional",
        status="active",
    )
    session.add(billing_a)

    # Activation du module HR pour Tenant A
    ModuleEntitlementService(session).activate_module(TenantContext(company_a.id), "hr")

    # Utilisateurs Tenant A
    owner_a = User(
        id=uuid4(),
        company_id=company_a.id,
        email="owner@alpha.com",
        first_name="Alice",
        last_name="Owner",
        job_title="CEO",
        department="Direction",
        role=UserRole.OWNER,
        password_hash="hash1",
        is_active=True,
    )
    manager_atelier = User(
        id=uuid4(),
        company_id=company_a.id,
        email="manager@alpha.com",
        first_name="Bob",
        last_name="Manager",
        job_title="Chef d'Atelier",
        department="Atelier",
        role=UserRole.MANAGER,
        password_hash="hash2",
        is_active=True,
    )
    manager_vente = User(
        id=uuid4(),
        company_id=company_a.id,
        email="vente_mgr@alpha.com",
        first_name="Vincent",
        last_name="Vente",
        job_title="Responsable Commercial",
        department="Ventes",
        role=UserRole.MANAGER,
        password_hash="hash3",
        is_active=True,
    )
    emp_a1 = User(
        id=uuid4(),
        company_id=company_a.id,
        email="emp1@alpha.com",
        first_name="Charlie",
        last_name="Mécano",
        job_title="Technicien Mécanique",
        department="Atelier",
        role=UserRole.USER,
        phone="+15145550101",
        password_hash="hash4",
        is_active=True,
    )
    emp_a2 = User(
        id=uuid4(),
        company_id=company_a.id,
        email="emp2@alpha.com",
        first_name="David",
        last_name="Vendeur",
        job_title="Conseiller Commercial",
        department="Ventes",
        role=UserRole.USER,
        phone="+15145550102",
        password_hash="hash5",
        is_active=True,
    )
    session.add_all([owner_a, manager_atelier, manager_vente, emp_a1, emp_a2])

    # Voice credential pour emp_a1
    cred_a1 = VoiceCallerCredential(
        company_id=company_a.id,
        principal_type="USER",
        principal_id=emp_a1.id,
        phone_number="+15145550101",
        pin_hash="pin_hash_1",
    )
    session.add(cred_a1)

    # Entreprise Secondaire (Tenant B) pour tests d'isolation inter-entreprises
    company_b = Company(
        id=uuid4(),
        name="Entreprise Beta",
        slug=f"beta-{uuid4().hex[:6]}",
        email="contact@beta.com",
        country="Canada",
        timezone="America/Toronto",
        subscription_plan="professional",
        industry="Construction",
        status=CompanyStatus.ACTIVE,
    )
    session.add(company_b)

    billing_b = BillingAccount(
        company_id=company_b.id,
        plan_code="professional",
        status="active",
    )
    session.add(billing_b)

    # Activation du module HR pour Tenant B
    ModuleEntitlementService(session).activate_module(TenantContext(company_b.id), "hr")

    owner_b = User(
        id=uuid4(),
        company_id=company_b.id,
        email="owner@beta.com",
        first_name="Bernard",
        last_name="OwnerB",
        job_title="Directeur Général",
        department="Direction",
        role=UserRole.OWNER,
        password_hash="hashb",
        is_active=True,
    )
    session.add(owner_b)

    # Plateforme Admin externe
    platform_admin = User(
        id=uuid4(),
        company_id=uuid4(),  # Entreprise tierce / système
        email="superadmin@avenqo.internal",
        first_name="Admin",
        last_name="Platform",
        job_title="Platform Engineer",
        role=UserRole.ADMIN,
        is_platform_admin=True,
        password_hash="hash_plat",
        is_active=True,
    )
    session.add(platform_admin)

    session.commit()

    # Application FastAPI de test
    app = FastAPI()
    app.include_router(hr_router)

    current_test_user = [owner_a]

    def override_get_db():
        try:
            yield session
        finally:
            pass

    def override_get_current_identity():
        u = current_test_user[0]
        return CurrentIdentity(auth_session=None, user=u, raw_token="fake_token")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_identity] = override_get_current_identity

    client = TestClient(app)

    yield {
        "session": session,
        "client": client,
        "current_test_user": current_test_user,
        "company_a": company_a,
        "company_b": company_b,
        "owner_a": owner_a,
        "manager_atelier": manager_atelier,
        "manager_vente": manager_vente,
        "emp_a1": emp_a1,
        "emp_a2": emp_a2,
        "owner_b": owner_b,
        "platform_admin": platform_admin,
    }

    session.close()
    engine.dispose()


def test_hr_entitlement_inactive_returns_403(rbac_env):
    """Un abonnement sans module HR AI activé reçoit 403 Forbidden."""
    env = rbac_env
    session = env["session"]
    client = env["client"]
    tenant_a = TenantContext(env["company_a"].id)

    # Désactiver le module HR pour Tenant A
    ModuleEntitlementService(session).deactivate_module(tenant_a, "hr")

    resp = client.get("/hr/overview")
    assert resp.status_code == 403
    data = resp.json()
    assert "module_inactive" in str(data)

    resp_leaves = client.get("/hr/leaves")
    assert resp_leaves.status_code == 403

    # Réactiver pour les autres tests
    ModuleEntitlementService(session).activate_module(tenant_a, "hr")


def test_hr_platform_admin_no_automatic_access(rbac_env):
    """Platform Admin: Aucun accès automatique aux dossiers RH privés sans appartenance au tenant."""
    env = rbac_env
    client = env["client"]
    env["current_test_user"][0] = env["platform_admin"]

    resp = client.get("/hr/leaves")
    assert resp.status_code == 403
    assert "dossiers RH privés" in resp.json()["detail"]


def test_hr_leaves_employee_peer_isolation_and_anti_idor(rbac_env):
    """Employee A ne peut voir les congés confidentiels d'Employee B."""
    env = rbac_env
    client = env["client"]
    session = env["session"]

    # Création d'un congé privé pour emp_a1
    now = datetime.now(timezone.utc)
    leave_a1 = EmployeeLeave(
        id=uuid4(),
        company_id=env["company_a"].id,
        user_id=env["emp_a1"].id,
        leave_type="sickness",
        start_date=now,
        end_date=now + timedelta(days=2),
        days_count=2.0,
        reason="Arrêt maladie confidentiel",
        status="pending",
    )
    # Création d'un congé privé pour emp_a2
    leave_a2 = EmployeeLeave(
        id=uuid4(),
        company_id=env["company_a"].id,
        user_id=env["emp_a2"].id,
        leave_type="vacation",
        start_date=now + timedelta(days=10),
        end_date=now + timedelta(days=15),
        days_count=5.0,
        reason="Vacances personnelles",
        status="pending",
    )
    session.add_all([leave_a1, leave_a2])
    session.commit()

    # 1. Connecté en tant que emp_a1 (Employé standard)
    env["current_test_user"][0] = env["emp_a1"]
    resp_a1 = client.get("/hr/leaves")
    assert resp_a1.status_code == 200
    leaves_a1 = resp_a1.json()
    assert len(leaves_a1) == 1
    assert leaves_a1[0]["id"] == str(leave_a1.id)
    assert leaves_a1[0]["reason"] == "Arrêt maladie confidentiel"
    # Aucune donnée de emp_a2 visible !
    assert not any(l["id"] == str(leave_a2.id) for l in leaves_a1)

    # 2. Connecté en tant que emp_a2 (Employé standard)
    env["current_test_user"][0] = env["emp_a2"]
    resp_a2 = client.get("/hr/leaves")
    assert resp_a2.status_code == 200
    leaves_a2 = resp_a2.json()
    assert len(leaves_a2) == 1
    assert leaves_a2[0]["id"] == str(leave_a2.id)
    # Ne voit pas le congé maladie de emp_a1
    assert not any(l["id"] == str(leave_a1.id) for l in leaves_a2)

    # 3. Anti-IDOR : soumettre une demande attribue TOUJOURS la demande au demandeur connecté
    req_body = {
        "leave_type": "vacation",
        "start_date": (now + timedelta(days=20)).isoformat(),
        "end_date": (now + timedelta(days=22)).isoformat(),
        "days_count": 2.0,
        "reason": "Test anti-usurpation",
    }
    resp_create = client.post("/hr/leaves", json=req_body)
    assert resp_create.status_code == 201
    created_item = resp_create.json()
    assert created_item["user_id"] == str(env["emp_a2"].id)


def test_hr_leaves_approval_rbac_and_self_approval_blocked(rbac_env):
    """Contrôle d'approbation des congés, séparation des devoirs et périmètre managérial."""
    env = rbac_env
    client = env["client"]
    session = env["session"]

    now = datetime.now(timezone.utc)
    leave_mécano = EmployeeLeave(
        id=uuid4(),
        company_id=env["company_a"].id,
        user_id=env["emp_a1"].id,
        leave_type="vacation",
        start_date=now + timedelta(days=5),
        end_date=now + timedelta(days=7),
        days_count=2.0,
        status="pending",
    )
    session.add(leave_mécano)
    session.commit()

    # 1. Un employé ne peut JAMAIS approuver son propre congé (403)
    env["current_test_user"][0] = env["emp_a1"]
    resp_self = client.put(f"/hr/leaves/{leave_mécano.id}/status", json={"status": "approved"})
    assert resp_self.status_code == 403
    assert "propre demande de congé" in resp_self.json()["detail"]

    # 2. Un employé standard B ne peut pas approuver le congé de A (403)
    env["current_test_user"][0] = env["emp_a2"]
    resp_colleague = client.put(f"/hr/leaves/{leave_mécano.id}/status", json={"status": "approved"})
    assert resp_colleague.status_code == 403

    # 3. Le Manager Vente ne peut pas approuver un employé de l'Atelier (403)
    env["current_test_user"][0] = env["manager_vente"]
    resp_other_dept = client.put(f"/hr/leaves/{leave_mécano.id}/status", json={"status": "approved"})
    assert resp_other_dept.status_code == 403
    assert "collaborateurs de votre département" in resp_other_dept.json()["detail"]

    # 4. Le Manager de l'Atelier peut approuver (200)
    env["current_test_user"][0] = env["manager_atelier"]
    resp_ok = client.put(f"/hr/leaves/{leave_mécano.id}/status", json={"status": "approved"})
    assert resp_ok.status_code == 200
    assert resp_ok.json()["status"] == "approved"
    assert resp_ok.json()["approved_by"] == "Bob Manager"

    # 5. Tentative inter-entreprises (Tenant B tente d'approuver le congé de Tenant A -> 404)
    env["current_test_user"][0] = env["owner_b"]
    resp_cross_tenant = client.put(f"/hr/leaves/{leave_mécano.id}/status", json={"status": "rejected"})
    assert resp_cross_tenant.status_code == 404


def test_hr_reviews_peer_isolation_and_manager_scope(rbac_env):
    """Employee A ne peut lire les évaluations privées d'Employee B. Manager limité à son équipe."""
    env = rbac_env
    client = env["client"]
    session = env["session"]

    # Revue pour emp_a1 (Atelier)
    rev_a1 = EmployeePerformanceReview(
        id=uuid4(),
        company_id=env["company_a"].id,
        user_id=env["emp_a1"].id,
        reviewer_user_id=env["manager_atelier"].id,
        review_period="Q4 2026",
        rating=4.5,
        strengths="Excellente technique",
        growth_areas="Communication client",
        goals="Formation électrique",
        ai_coach_notes="Évaluation confidentielle Atelier",
        is_demo=False,
    )
    # Revue pour emp_a2 (Ventes)
    rev_a2 = EmployeePerformanceReview(
        id=uuid4(),
        company_id=env["company_a"].id,
        user_id=env["emp_a2"].id,
        reviewer_user_id=env["manager_vente"].id,
        review_period="Q4 2026",
        rating=4.7,
        strengths="Très bons chiffres de vente",
        growth_areas="CRM logging",
        goals="Dépasser 100k$",
        ai_coach_notes="Évaluation confidentielle Ventes",
        is_demo=False,
    )
    session.add_all([rev_a1, rev_a2])
    session.commit()

    # 1. emp_a1 ne voit QUE sa propre revue
    env["current_test_user"][0] = env["emp_a1"]
    resp_emp1 = client.get("/hr/reviews")
    assert resp_emp1.status_code == 200
    revs_emp1 = resp_emp1.json()
    assert len(revs_emp1) == 1
    assert revs_emp1[0]["id"] == str(rev_a1.id)
    assert not any(r["id"] == str(rev_a2.id) for r in revs_emp1)

    # 2. Le collaborateur ne peut pas s'auto-évaluer (403)
    resp_self_rev = client.post(
        "/hr/reviews",
        json={
            "employee_id": str(env["emp_a1"].id),
            "review_period": "Q4 2026",
            "rating": 5.0,
            "strengths": "Je suis parfait",
            "growth_areas": "Rien",
            "goals": "Augmentation",
        },
    )
    assert resp_self_rev.status_code == 403
    assert "propre évaluation" in resp_self_rev.json()["detail"]

    # 3. Manager Vente ne peut pas évaluer emp_a1 de l'Atelier (403)
    env["current_test_user"][0] = env["manager_vente"]
    resp_wrong_dept = client.post(
        "/hr/reviews",
        json={
            "employee_id": str(env["emp_a1"].id),
            "review_period": "Q4 2026",
            "rating": 3.0,
            "strengths": "Moyen",
            "growth_areas": "Beaucoup",
            "goals": "Travailler plus",
        },
    )
    assert resp_wrong_dept.status_code == 403

    # 4. Manager Atelier évalue emp_a1 (200 avec message données insuffisantes si pas de tâches)
    env["current_test_user"][0] = env["manager_atelier"]
    resp_ok = client.post(
        "/hr/reviews",
        json={
            "employee_id": str(env["emp_a1"].id),
            "review_period": "Q4 2026",
            "rating": 4.6,
            "strengths": "Rapidité",
            "growth_areas": "Rangement",
            "goals": "Zéro retours",
        },
    )
    assert resp_ok.status_code == 201
    assert resp_ok.json()["ai_coach_notes"] == "Données insuffisantes pour produire une évaluation personnalisée fiable."


def test_hr_employees_directory_sanitization(rbac_env):
    """Un employé standard reçoit un annuaire épuré sans téléphone privé ni statut de NIP vocal."""
    env = rbac_env
    client = env["client"]

    # Connecté en tant qu'employé standard
    env["current_test_user"][0] = env["emp_a2"]
    resp_emp = client.get("/hr/employees")
    assert resp_emp.status_code == 200
    employees = resp_emp.json()
    assert len(employees) >= 4
    # Vérifier que le numéro de téléphone et le NIP de son collègue emp_a1 sont masqués
    item_emp1 = next(e for e in employees if e["id"] == str(env["emp_a1"].id))
    assert item_emp1["phone"] is None
    assert item_emp1["has_voice_pin"] is False

    # Connecté en tant que Direction / Owner
    env["current_test_user"][0] = env["owner_a"]
    resp_owner = client.get("/hr/employees")
    assert resp_owner.status_code == 200
    owner_employees = resp_owner.json()
    item_emp1_full = next(e for e in owner_employees if e["id"] == str(env["emp_a1"].id))
    assert item_emp1_full["phone"] == "+15145550101"
    assert item_emp1_full["has_voice_pin"] is True


def test_hr_skills_matrix_integrity_and_verification_flow(rbac_env):
    """Les compétences non vérifiées ne sont jamais présentées comme officielles."""
    env = rbac_env
    client = env["client"]

    # 1. Matrice brute sans vérification : toutes les compétences suggérées sont not_assessed et certified=False
    resp_matrix = client.get("/hr/skills")
    assert resp_matrix.status_code == 200
    skills = resp_matrix.json()
    assert len(skills) >= 3
    for s in skills:
        assert s["certified"] is False
        assert s["status"] == "not_assessed"

    # 2. Auto-déclaration par un employé
    env["current_test_user"][0] = env["emp_a1"]
    declare_resp = client.post(
        "/hr/skills/declare",
        json={
            "name": "Diagnostic Hybride Toyota",
            "category": "Technique",
            "level": 3,
            "evidence_url_or_note": "Formation interne suivie en octobre 2026",
        },
    )
    assert declare_resp.status_code == 201
    decl_skill = declare_resp.json()
    assert decl_skill["certified"] is False
    assert decl_skill["status"] == "self_declared"
    skill_id = decl_skill["id"]

    # 3. Un autre employé ne peut pas valider la compétence (403)
    env["current_test_user"][0] = env["emp_a2"]
    resp_forbidden_verify = client.post(
        f"/hr/skills/{skill_id}/verify",
        json={"certified": True, "level": 4},
    )
    assert resp_forbidden_verify.status_code == 403

    # 4. Le Manager certifie officiellement avec preuve
    env["current_test_user"][0] = env["manager_atelier"]
    resp_verified = client.post(
        f"/hr/skills/{skill_id}/verify",
        json={
            "certified": True,
            "level": 4,
            "evidence_url_or_note": "Certificat officiel n° TH-2026-99 validé par Chef d'Atelier",
        },
    )
    assert resp_verified.status_code == 200
    verified_data = resp_verified.json()
    assert verified_data["certified"] is True
    assert verified_data["status"] == "verified"
    assert verified_data["verified_by"] == "Bob Manager"
    assert verified_data["verified_at"] is not None


def test_hr_skills_matrix_peer_isolation_and_departmental_scope(rbac_env):
    """GET /hr/skills respecte strictement le cloisonnement par employé et par département."""
    env = rbac_env
    client = env["client"]

    # 1. Employé standard emp_a1 (Atelier) ne voit QUE ses propres compétences
    env["current_test_user"][0] = env["emp_a1"]
    resp_emp1 = client.get("/hr/skills")
    assert resp_emp1.status_code == 200
    skills_emp1 = resp_emp1.json()
    assert len(skills_emp1) > 0
    for s in skills_emp1:
        assert s["employee_id"] == str(env["emp_a1"].id)

    # 2. Employé standard emp_a2 (Ventes) ne voit QUE ses propres compétences
    env["current_test_user"][0] = env["emp_a2"]
    resp_emp2 = client.get("/hr/skills")
    assert resp_emp2.status_code == 200
    skills_emp2 = resp_emp2.json()
    assert len(skills_emp2) > 0
    for s in skills_emp2:
        assert s["employee_id"] == str(env["emp_a2"].id)

    # 3. Manager Atelier ne voit QUE les membres du département Atelier (Bob Manager & Charlie Mécano)
    env["current_test_user"][0] = env["manager_atelier"]
    resp_mgr_atelier = client.get("/hr/skills")
    assert resp_mgr_atelier.status_code == 200
    skills_atelier = resp_mgr_atelier.json()
    allowed_atelier_ids = {str(env["manager_atelier"].id), str(env["emp_a1"].id)}
    for s in skills_atelier:
        assert s["employee_id"] in allowed_atelier_ids
    # Doit contenir les compétences d'Atelier et aucune de Ventes
    assert any(s["employee_id"] == str(env["emp_a1"].id) for s in skills_atelier)
    assert not any(s["employee_id"] == str(env["emp_a2"].id) for s in skills_atelier)

    # 4. Le Directeur / Owner voit l'ensemble des compétences de l'entreprise
    env["current_test_user"][0] = env["owner_a"]
    resp_owner = client.get("/hr/skills")
    assert resp_owner.status_code == 200
    skills_owner = resp_owner.json()
    all_emp_ids = {s["employee_id"] for s in skills_owner}
    assert str(env["emp_a1"].id) in all_emp_ids
    assert str(env["emp_a2"].id) in all_emp_ids


def test_hr_skills_verification_rbac_and_boundaries(rbac_env):
    """POST /hr/skills/{skill_id}/verify bloque l'auto-certification et le débordement inter-départemental."""
    env = rbac_env
    client = env["client"]

    # Charlie Mécano (emp_a1, Atelier) déclare une compétence
    env["current_test_user"][0] = env["emp_a1"]
    resp_decl = client.post(
        "/hr/skills/declare",
        json={"name": "Soudure MIG / TIG", "category": "Technique", "level": 2},
    )
    assert resp_decl.status_code == 201
    skill_charlie_id = resp_decl.json()["id"]

    # 1. Charlie ne peut pas valider sa propre compétence (403 car non-manager)
    resp_self = client.post(f"/hr/skills/{skill_charlie_id}/verify", json={"level": 5})
    assert resp_self.status_code == 403

    # 2. David Vendeur (emp_a2, non-manager) ne peut pas valider (403)
    env["current_test_user"][0] = env["emp_a2"]
    resp_peer = client.post(f"/hr/skills/{skill_charlie_id}/verify", json={"level": 5})
    assert resp_peer.status_code == 403

    # 3. Manager Vente (Alice Vente, département Ventes) essaie de valider la compétence de Charlie (Atelier) -> 403
    env["current_test_user"][0] = env["manager_vente"]
    resp_wrong_dept = client.post(f"/hr/skills/{skill_charlie_id}/verify", json={"level": 4})
    assert resp_wrong_dept.status_code == 403
    assert "département" in resp_wrong_dept.json()["detail"]

    # 4. Bob Manager (Atelier) auto-déclare une compétence pour lui-même
    env["current_test_user"][0] = env["manager_atelier"]
    resp_decl_mgr = client.post(
        "/hr/skills/declare",
        json={"name": "Gestion Atelier Lean", "category": "Gestion", "level": 3},
    )
    assert resp_decl_mgr.status_code == 201
    skill_bob_id = resp_decl_mgr.json()["id"]

    # Bob Manager tente d'auto-certifier sa propre compétence -> 403
    resp_mgr_self_verify = client.post(f"/hr/skills/{skill_bob_id}/verify", json={"level": 5})
    assert resp_mgr_self_verify.status_code == 403
    assert "propres compétences" in resp_mgr_self_verify.json()["detail"]

    # 5. Tentative de vérification d'un UUID inexistant -> 404
    resp_not_found = client.post(f"/hr/skills/{uuid4()}/verify", json={"level": 4})
    assert resp_not_found.status_code == 404

    # 6. Bob Manager valide la compétence de Charlie (même département Atelier) -> 200 OK
    resp_valid = client.post(
        f"/hr/skills/{skill_charlie_id}/verify",
        json={"level": 4, "evidence_url_or_note": "Formation soudure réussie avec mention"},
    )
    assert resp_valid.status_code == 200
    assert resp_valid.json()["certified"] is True
    assert resp_valid.json()["status"] == "verified"
    assert resp_valid.json()["verified_by"] == "Bob Manager"

    # 7. La Direction / Owner peut valider la compétence de Bob Manager (cross-department) -> 200 OK
    env["current_test_user"][0] = env["owner_a"]
    resp_owner_valid = client.post(
        f"/hr/skills/{skill_bob_id}/verify",
        json={"level": 5, "evidence_url_or_note": "Validation par la Direction Générale"},
    )
    assert resp_owner_valid.status_code == 200
    assert resp_owner_valid.json()["certified"] is True
    assert resp_owner_valid.json()["verified_by"] == "Alice Owner"

