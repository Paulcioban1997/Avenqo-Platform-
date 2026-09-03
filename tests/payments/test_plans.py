import pytest

from payments import PLANS, PlanCode, SubscriptionPlan, get_plan


def test_catalogue_contient_les_trois_offres_publiques_avenqo() -> None:
    assert [plan.code for plan in PLANS] == [
        PlanCode.DEMO,
        PlanCode.PROFESSIONAL,
        PlanCode.ENTERPRISE,
    ]


@pytest.mark.parametrize("plan", PLANS)
def test_retail_est_selectionnable_dans_chaque_offre(
    plan: SubscriptionPlan,
) -> None:
    assert plan.allows_module("retail") is True


def test_custom_enterprise_demande_un_contact_commercial() -> None:
    assert get_plan("custom_enterprise").requires_sales_contact is True


def test_catalogue_public_ne_contient_pas_custom_enterprise() -> None:
    assert [plan.code for plan in PLANS] == [
        PlanCode.DEMO,
        PlanCode.PROFESSIONAL,
        PlanCode.ENTERPRISE,
    ]


def test_allocations_mensuelles_de_credits_sont_centralisees_par_offre() -> None:
    assert get_plan("demo").monthly_ai_credits == 6_500
    assert get_plan("professional").monthly_ai_credits == 25_000
    assert get_plan("enterprise").monthly_ai_credits is None


def test_offre_inconnue_est_refusee() -> None:
    with pytest.raises(ValueError, match="Offre Avenqo inconnue"):
        get_plan("inconnue")
