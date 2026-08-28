import pytest

from payments import (
    AI_CREDIT_PACKS,
    ENTERPRISE_STARTING_PRICE_USD,
    PLANS,
    PlanCode,
    SubscriptionPlan,
    get_credit_pack,
    get_plan,
)


def test_catalogue_contient_les_trois_offres_publiques_avenqo() -> None:
    assert [plan.code for plan in PLANS] == [
        PlanCode.DEMO,
        PlanCode.PROFESSIONAL,
        PlanCode.ENTERPRISE,
    ]
    assert [plan.monthly_price_usd for plan in PLANS] == [28, 49, None]
    assert [plan.included_ai_credits for plan in PLANS] == [5_000, 25_000, None]
    assert ENTERPRISE_STARTING_PRICE_USD == 250


@pytest.mark.parametrize("plan", PLANS)
def test_retail_est_selectionnable_dans_chaque_offre(plan: SubscriptionPlan) -> None:
    assert plan.allows_module("retail") is True


def test_credit_packs_sont_des_achats_uniques_catalogues() -> None:
    assert [(pack.credits, pack.price_usd) for pack in AI_CREDIT_PACKS] == [
        (5_000, 10),
        (20_000, 29),
        (50_000, 59),
        (150_000, 149),
    ]
    assert get_credit_pack("credits_20k").credits == 20_000


def test_custom_enterprise_demande_un_contact_commercial() -> None:
    assert get_plan("custom_enterprise").requires_sales_contact is True


def test_catalogue_public_ne_contient_pas_custom_enterprise() -> None:
    assert [plan.code for plan in PLANS] == [
        PlanCode.DEMO,
        PlanCode.PROFESSIONAL,
        PlanCode.ENTERPRISE,
    ]


def test_offre_inconnue_est_refusee() -> None:
    with pytest.raises(ValueError, match="Offre Avenqo inconnue"):
        get_plan("inconnue")


def test_pack_inconnu_est_refuse() -> None:
    with pytest.raises(ValueError, match="Pack de crédits IA inconnu"):
        get_credit_pack("inconnu")
