"""Sandbox voice answers stay audible and the free frontend stays off production."""
from pathlib import Path
from types import SimpleNamespace

from backend.app.voice.direct_answers import (
    is_module_access_question,
    is_open_catalog_question,
    spoken_catalog_answer,
    spoken_module_answer,
)
from backend.app.voice.messages import voice_ivr_greeting

EMPLOYEE_QUESTION = "Quels modules Avenqo sont accessibles pour mon entreprise ?"
CUSTOMER_QUESTION = "Quels produits avez-vous en vente et à quels prix ?"


def test_exact_brand_menu_offers_employee_and_customer_paths():
    cfg = SimpleNamespace(
        business_name="Produits Ero",
        voice_display_name="Produits Ero",
        custom_pronunciation=None,
        preferred_language="fr",
        call_policy={},
    )
    greeting = voice_ivr_greeting(cfg)
    assert "Bienvenue chez Produits, Ero." in greeting
    assert "composez le 1" in greeting
    assert "composez le 2" in greeting
    assert "Produits Ero" not in greeting
    assert cfg.business_name == "Produits Ero"
    assert cfg.voice_display_name == "Produits Ero"


def test_legacy_underscore_name_uses_the_generic_pause():
    cfg = SimpleNamespace(
        business_name="Produits_Ero",
        voice_display_name=None,
        custom_pronunciation="{}",
        preferred_language="fr",
        call_policy={
            "ivr_greeting": (
                "Bienvenue chez {company}. Pour les employés, composez le 1. "
                "Pour le service clientèle, composez le 2."
            )
        },
    )
    greeting = voice_ivr_greeting(cfg)
    assert "Produits, Ero" in greeting
    assert "Produits_Ero" not in greeting
    assert "Zéro" not in greeting
    assert "composez le 1" in greeting and "composez le 2" in greeting


def test_employee_and_customer_questions_produce_spoken_answers():
    assert is_module_access_question(EMPLOYEE_QUESTION)
    assert is_open_catalog_question(CUSTOMER_QUESTION)
    modules = spoken_module_answer(["Retail", "CRM"], plan_code="professional", locale="fr")
    assert "Retail" in modules and "CRM" in modules
    assert modules.strip()
    none = spoken_module_answer([], plan_code=None, locale="fr")
    assert "aucun module actif" in none
    catalog = spoken_catalog_answer(
        [{"name": "Savon", "price": 12.5, "currency": "CAD", "in_stock": True, "inventory_count": 3}],
        retail_enabled=True,
        locale="fr",
    )
    assert catalog.startswith("Nous avons en vente")
    assert "Savon" in catalog and "12.5" in catalog and "CAD" in catalog
    blocked = spoken_catalog_answer(
        [{"name": "Savon", "price": 12.5, "currency": "CAD"}],
        retail_enabled=False,
        locale="fr",
    )
    assert "Savon" not in blocked
    assert "n'est pas disponible" in blocked


def test_render_blueprint_stays_on_the_sandbox_branch_and_api():
    text = Path("render.yaml").read_text(encoding="utf-8")
    assert "plan: free" in text
    assert "branch: fix/sandbox-crm-accounting-labels-20261112" in text
    assert "branch: main" not in text
    assert "rootDir: web" in text
    assert "value: sandbox" in text
    assert "https://avenqo-platform-sandbox.up.railway.app" in text
    assert "value: https://api.avenqo.ca" not in text
    assert "value: https://avenqo.ca" not in text
