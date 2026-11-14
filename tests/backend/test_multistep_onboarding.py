"""Tests unitaires et de non-régression du parcours d'onboarding multi-pages (8 étapes),
personnalisation visuelle (15 thèmes), contrats et validation multi-tenant.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.database import get_db
from backend.app.dependencies.auth import get_account_notifier
from backend.app.models import Base, Company, User, CompanyOnboarding
from backend.main import create_application

from shared.themes.theme_catalog import ALL_30_THEMES
from tests.backend.test_auth import NON_SENSITIVE_TEST_PASSWORD, RecordingNotifier, registration_payload, verify_and_login


@pytest.fixture
def multistep_env(
    tmp_path: Path,
) -> Generator[tuple[TestClient, RecordingNotifier, sessionmaker[Session]], None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'multistep.db'}",
        connect_args={"check_same_thread": False},
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    notifier = RecordingNotifier()
    app = create_application()

    def override_db() -> Generator[Session, None, None]:
        session = testing_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_account_notifier] = lambda: notifier
    with TestClient(app) as client:
        yield client, notifier, testing_session


def register_user(client: TestClient, notifier: RecordingNotifier, email: str, company_name: str) -> str:
    res = client.post(
        "/api/v1/auth/register",
        json=registration_payload(email=email, company_name=company_name),
    )
    assert res.status_code == 201, res.text
    session_data = verify_and_login(client, notifier, email)
    token = session_data["access_token"]
    assert isinstance(token, str)
    return token


def test_multistep_onboarding_lifecycle(multistep_env):
    client, notifier, _ = multistep_env
    token = register_user(client, notifier, "owner@entreprise-alpha.ca", "Entreprise Alpha")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Obtenir l'état initial
    state_res = client.get("/api/v1/onboarding/state", headers=headers)
    assert state_res.status_code == 200, state_res.text
    state = state_res.json()
    assert state["status"] == "pending"
    assert len(state["candidate_themes"]) == 30
    active_presets = [t for t in state["candidate_themes"] if t["is_active_preset"]]
    assert len(active_presets) == 5

    # 2. Mettre à jour l'étape 1 : Entreprise
    step1_res = client.put(
        "/api/v1/onboarding/step/company",
        headers=headers,
        json={
            "commercial_name": "Alpha Solutions Inc.",
            "legal_name": "9488-1234 Québec Inc.",
            "country": "Canada",
            "region": "Québec",
            "timezone": "America/Montreal",
            "industry": "Technologies",
            "team_size": "11-50",
            "website": "https://alpha.ca",
            "description": "Leader québécois des solutions de commerce intelligent.",
            "authorized_rep_first_name": "Jean",
            "authorized_rep_last_name": "Dupont",
            "authorized_rep_title": "Président & Fondateur",
        },
    )
    assert step1_res.status_code == 200, step1_res.text
    assert "company" in step1_res.json()["completed_steps"]

    # 3. Mettre à jour l'étape 2 : Modules
    step2_res = client.put(
        "/api/v1/onboarding/step/modules",
        headers=headers,
        json={"selected_modules": ["retail", "crm"], "industry_category": "Technologies"},
    )
    assert step2_res.status_code == 200
    assert "modules" in step2_res.json()["completed_steps"]

    # 4. Mettre à jour l'étape 3 : Design / Personnalisation
    step3_res = client.put(
        "/api/v1/onboarding/step/design",
        headers=headers,
        json={
            "theme_id": "emerald_enterprise",
            "primary_color": "#059669",
            "secondary_color": "#064E3B",
            "accent_color": "#F59E0B",
            "mode": "dark",
            "background_style": "gradient_dark",
            "company_logo_url": "https://alpha.ca/logo.png",
            "display_name": "Alpha Solutions",
        },
    )
    assert step3_res.status_code == 200
    assert step3_res.json()["design"]["theme_id"] == "emerald_enterprise"
    assert "design" in step3_res.json()["completed_steps"]

    # 5. Mettre à jour l'étape 5 : Contrats
    step5_res = client.put(
        "/api/v1/onboarding/step/contracts",
        headers=headers,
        json={
            "accepted_contract_types": ["terms_of_service", "saas_subscription", "privacy_policy"],
            "accepted_by_name": "Jean Dupont",
            "accepted_by_title": "Président",
            "marketing_consent": True,
        },
    )
    assert step5_res.status_code == 200
    assert "contracts" in step5_res.json()["completed_steps"]

    # 6. Mettre à jour l'étape 6 : Abonnement
    step6_res = client.put(
        "/api/v1/onboarding/step/subscription",
        headers=headers,
        json={"plan_code": "professional", "billing_cycle": "monthly", "currency": "CAD"},
    )
    assert step6_res.status_code == 200

    # 7. Finaliser l'onboarding
    finalize_res = client.post("/api/v1/onboarding/finalize", headers=headers)
    assert finalize_res.status_code == 200, finalize_res.text
    final_data = finalize_res.json()
    assert final_data["success"] is True
    assert final_data["status"] == "completed"
    assert "retail" in final_data["activated_modules"]
    assert "crm" in final_data["activated_modules"]

    # 8. Vérifier la modification post-activation (Section 10)
    branding_get = client.get("/api/v1/onboarding/branding", headers=headers)
    assert branding_get.status_code == 200
    assert branding_get.json()["theme_id"] == "emerald_enterprise"

    # Modification de marque par l'administrateur
    branding_update = client.put(
        "/api/v1/onboarding/branding",
        headers=headers,
        json={"primary_color": "#10B981", "display_name": "Alpha AI"},
    )
    assert branding_update.status_code == 200
    assert branding_update.json()["primary_color"] == "#10B981"
    assert branding_update.json()["display_name"] == "Alpha AI"

    # Réinitialisation du style
    branding_reset = client.put(
        "/api/v1/onboarding/branding",
        headers=headers,
        json={"reset": True},
    )
    assert branding_reset.status_code == 200
    assert branding_reset.json()["theme_id"] == "avenqo_obsidian"


def test_asset_upload_security(multistep_env):
    client, notifier, _ = multistep_env
    token = register_user(client, notifier, "owner2@entreprise-beta.ca", "Entreprise Beta")
    headers = {"Authorization": f"Bearer {token}"}

    # Upload valide PNG
    png_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    res_valid = client.post(
        "/api/v1/onboarding/upload-asset",
        headers=headers,
        files={"file": ("logo.png", png_data, "image/png")},
    )
    assert res_valid.status_code == 200, res_valid.text
    assert res_valid.json()["asset_url"].startswith("data:image/png;base64,")

    # Rejet fichier non image
    res_invalid = client.post(
        "/api/v1/onboarding/upload-asset",
        headers=headers,
        files={"file": ("script.sh", b"#!/bin/bash\necho hack", "application/x-sh")},
    )
    assert res_invalid.status_code == 400


def test_tenant_isolation_on_onboarding(multistep_env):
    client, notifier, _ = multistep_env
    token_a = register_user(client, notifier, "owner-a@corp.ca", "Corp A")
    token_b = register_user(client, notifier, "owner-b@corp.ca", "Corp B")

    client.put(
        "/api/v1/onboarding/step/design",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"theme_id": "amethyst_nebula", "primary_color": "#7C3AED", "display_name": "Corp A Space"},
    )

    state_b = client.get("/api/v1/onboarding/state", headers={"Authorization": f"Bearer {token_b}"}).json()
    assert state_b["design"]["display_name"] == "Onboarding Test Co" or "Corp B" in state_b["design"]["display_name"]
    assert state_b["design"]["theme_id"] == "avenqo_obsidian"


def test_full_8_step_transactional_journey(multistep_env):
    """Valide l'intégralité du parcours transactionnel en 8 étapes indépendantes :
    Entreprise -> Modules -> 30 thèmes -> Personnalisation -> Aperçu -> Contrats -> Base/Professional -> Stripe -> Activation.
    """
    client, notifier, _ = multistep_env
    token = register_user(client, notifier, "directeur@innovations-quebec.ca", "Innovations Québec Inc.")
    headers = {"Authorization": f"Bearer {token}"}

    # Étape 0 : État initial et présence des 30 univers
    init_state = client.get("/api/v1/onboarding/state", headers=headers).json()
    assert init_state["status"] == "pending"
    assert len(init_state["candidate_themes"]) == 30
    theme_ids = {t["id"] for t in init_state["candidate_themes"]}
    assert "galaxy_orbit" in theme_ids
    assert "midnight_gold" in theme_ids
    assert "titanium_minimal" in theme_ids

    # Étape 1 : Entreprise (/step/company)
    s1 = client.put(
        "/api/v1/onboarding/step/company",
        headers=headers,
        json={
            "commercial_name": "Innovations Québec",
            "legal_name": "9488-5678 Québec Inc.",
            "country": "Canada",
            "region": "Québec",
            "timezone": "America/Montreal",
            "industry": "Intelligence Artificielle & Commerce",
            "team_size": "20-99",
            "website": "https://innovations-quebec.ca",
            "description": "Plateforme d'automatisation des opérations retail et relation client.",
            "authorized_rep_first_name": "Sophie",
            "authorized_rep_last_name": "Tremblay",
            "authorized_rep_title": "Directrice Générale",
        },
    ).json()
    assert "company" in s1["completed_steps"]

    # Étape 2 : Modules (/step/modules)
    s2 = client.put(
        "/api/v1/onboarding/step/modules",
        headers=headers,
        json={
            "selected_modules": ["retail", "crm", "voice"],
            "industry_category": "Technologies",
        },
    ).json()
    assert "modules" in s2["completed_steps"]

    # Étape 3 : 30 Thèmes & Personnalisation (/step/design)
    s3 = client.put(
        "/api/v1/onboarding/step/design",
        headers=headers,
        json={
            "theme_id": "galaxy_orbit",
            "primary_color": "#3B82F6",
            "secondary_color": "#8B5CF6",
            "accent_color": "#06B6D4",
            "mode": "dark",
            "background_style": "neon_grid",
            "display_name": "Espace IA Innovations",
            "company_logo_url": "https://innovations-quebec.ca/logo.png",
            "company_emblem_url": "https://innovations-quebec.ca/emblem.png",
        },
    ).json()
    assert "design" in s3["completed_steps"]
    assert s3["design"]["theme_id"] == "galaxy_orbit"

    # Étape 4 : Aperçu interactif (/step/preview)
    s4 = client.put(
        "/api/v1/onboarding/step/preview",
        headers=headers,
        json={"confirmed_preview": True},
    ).json()
    assert "preview" in s4["completed_steps"]

    # Étape 5 : Contrats et conformité légale (/step/contracts)
    s5 = client.put(
        "/api/v1/onboarding/step/contracts",
        headers=headers,
        json={
            "accepted_contract_types": ["terms_of_service", "saas_subscription", "privacy_policy", "data_processing"],
            "accepted_by_name": "Sophie Tremblay",
            "accepted_by_title": "Directrice Générale",
            "marketing_consent": False,
        },
    ).json()
    assert "contracts" in s5["completed_steps"]

    # Étape 6 : Abonnement Base / Professional (/step/subscription)
    s6 = client.put(
        "/api/v1/onboarding/step/subscription",
        headers=headers,
        json={
            "plan_code": "professional",
            "billing_cycle": "monthly",
            "currency": "CAD",
        },
    ).json()
    assert "subscription" in s6["completed_steps"]

    # Étape 7 : Checkout Stripe sécurisé (/step/checkout)
    s7 = client.put(
        "/api/v1/onboarding/step/checkout",
        headers=headers,
        json={
            "checkout_status": "verified_test",
            "plan_code": "professional",
            "currency": "CAD",
        },
    ).json()
    assert "checkout" in s7["completed_steps"]

    # Étape 8 : Finalisation et activation de l'espace (/finalize)
    fin_res = client.post("/api/v1/onboarding/finalize", headers=headers)
    assert fin_res.status_code == 200, fin_res.text
    fin_data = fin_res.json()
    assert fin_data["success"] is True
    assert fin_data["status"] == "completed"
    assert "retail" in fin_data["activated_modules"]
    assert "crm" in fin_data["activated_modules"]

    # Vérification post-activation dans Settings
    post_state = client.get("/api/v1/onboarding/state", headers=headers).json()
    assert post_state["status"] == "completed"
    assert post_state["design"]["theme_id"] == "galaxy_orbit"

    # Modification de thème post-activation vers #9 Midnight Gold
    updated_branding = client.put(
        "/api/v1/onboarding/branding",
        headers=headers,
        json={"theme_id": "midnight_gold", "primary_color": "#F59E0B"},
    ).json()
    assert updated_branding["theme_id"] == "midnight_gold"


def test_branding_save_accepts_plain_json_and_stays_on_the_tenant(multistep_env):
    client, notifier, _ = multistep_env
    owner_email = "owner-brand@entreprise-alpha.ca"
    owner = register_user(client, notifier, owner_email, "Entreprise Alpha")
    other = register_user(client, notifier, "owner-brand@entreprise-beta.ca", "Entreprise Beta")
    owner_headers = {"Authorization": f"Bearer {owner}"}
    other_headers = {"Authorization": f"Bearer {other}"}
    client.cookies.clear()

    for theme in ALL_30_THEMES:
        body = {
            "theme_id": theme.id,
            "primary_color": theme.primary_color,
            "secondary_color": theme.secondary_color,
            "accent_color": theme.accent_color,
            "mode": theme.mode,
            "background_style": theme.background_style,
            "company_logo_url": "",
            "company_emblem_url": "",
            "logo_placement": "both",
            "display_name": "Entreprise Alpha",
        }
        saved = client.put(
            "/api/v1/onboarding/branding",
            headers={**owner_headers, "Content-Type": "text/plain;charset=UTF-8"},
            content=json.dumps(body),
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["theme_id"] == theme.id
        assert saved.json()["primary_color"] == theme.primary_color

    refreshed = client.get("/api/v1/onboarding/branding", headers=owner_headers)
    assert refreshed.status_code == 200
    assert refreshed.json()["theme_id"] == ALL_30_THEMES[-1].id

    relogin = client.post(
        "/api/v1/auth/login",
        json={"email": owner_email, "password": NON_SENSITIVE_TEST_PASSWORD},
    )
    assert relogin.status_code == 200, relogin.text
    client.cookies.clear()
    persisted = client.get(
        "/api/v1/onboarding/branding",
        headers={"Authorization": f"Bearer {relogin.json()['access_token']}"},
    )
    assert persisted.json()["theme_id"] == ALL_30_THEMES[-1].id
    client.cookies.clear()
    assert client.get("/api/v1/onboarding/branding", headers=other_headers).json()["theme_id"] == "avenqo_obsidian"

    rejected = client.put(
        "/api/v1/onboarding/branding",
        headers={**owner_headers, "Content-Type": "text/plain"},
        content="not-json",
    )
    assert rejected.status_code == 422
    unknown = client.put(
        "/api/v1/onboarding/branding",
        headers=owner_headers,
        json={"theme_id": "not_a_theme", "primary_color": "gold"},
    )
    assert unknown.status_code == 422
