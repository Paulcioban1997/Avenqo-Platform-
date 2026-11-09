"""Theme and visual style catalog for Avenqo multi-tenant white-label personalization.

Maintains all 15 candidate visual themes and flags the 5 approved preset styles.
Allows dynamic customization: primary, secondary, accent colors, mode (dark/light),
background style, company logo and emblem.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ThemeDefinition:
    id: str
    name: str
    description: str
    mode: str  # "dark" | "light"
    primary_color: str
    secondary_color: str
    accent_color: str
    background_style: str  # "mesh_dark" | "subtle_grid" | "gradient_dark" | etc.
    preview_gradient: str
    is_active_preset: bool = False
    card_border: str = "border-slate-800"
    font_family: str = "Inter, sans-serif"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# 15 candidate visual themes from founder concepts; 5 currently flagged as approved flagship presets.
CANDIDATE_THEMES: tuple[ThemeDefinition, ...] = (
    ThemeDefinition(
        id="avenqo_obsidian",
        name="Avenqo Obsidian",
        description="Signature Cyber & Deep Navy — L'élégance technique et la puissance analytique de référence",
        mode="dark",
        primary_color="#0076FF",
        secondary_color="#0B132B",
        accent_color="#00D4FF",
        background_style="mesh_dark",
        preview_gradient="linear-gradient(135deg, #0B132B 0%, #111D3D 50%, #0076FF 100%)",
        is_active_preset=True,
    ),
    ThemeDefinition(
        id="titanium_minimal",
        name="Titanium Minimalist",
        description="Slate pur & Silver — Clarté architecturale scandinave et lisibilité maximale",
        mode="light",
        primary_color="#2563EB",
        secondary_color="#F8FAFC",
        accent_color="#38BDF8",
        background_style="subtle_grid",
        preview_gradient="linear-gradient(135deg, #FFFFFF 0%, #F1F5F9 50%, #2563EB 100%)",
        is_active_preset=True,
    ),
    ThemeDefinition(
        id="emerald_enterprise",
        name="Emerald Enterprise",
        description="Vert Forêt & Or Subtil — Prestige institutionnel, stabilité financière et croissance",
        mode="dark",
        primary_color="#059669",
        secondary_color="#064E3B",
        accent_color="#F59E0B",
        background_style="gradient_dark",
        preview_gradient="linear-gradient(135deg, #064E3B 0%, #0F382C 50%, #059669 100%)",
        is_active_preset=True,
    ),
    ThemeDefinition(
        id="royal_sapphire",
        name="Royal Sapphire",
        description="Bleu Impérial & Platine — Confiance bancaire, fintech et rigueur transactionnelle",
        mode="dark",
        primary_color="#1D4ED8",
        secondary_color="#0F172A",
        accent_color="#60A5FA",
        background_style="radial_dark",
        preview_gradient="linear-gradient(135deg, #0F172A 0%, #1E293B 50%, #1D4ED8 100%)",
        is_active_preset=True,
    ),
    ThemeDefinition(
        id="amethyst_nebula",
        name="Amethyst Nebula",
        description="Violet Profond & Cyan Électrique — Innovation technologique et intelligence artificielle",
        mode="dark",
        primary_color="#7C3AED",
        secondary_color="#1E1B4B",
        accent_color="#06B6D4",
        background_style="mesh_purple",
        preview_gradient="linear-gradient(135deg, #1E1B4B 0%, #31104B 50%, #7C3AED 100%)",
        is_active_preset=True,
    ),
    ThemeDefinition(
        id="carbon_stealth",
        name="Carbon Stealth",
        description="Monochrome Carbone & Titane Brossé — Discrétion absolue pour direction générale",
        mode="dark",
        primary_color="#64748B",
        secondary_color="#0F172A",
        accent_color="#94A3B8",
        background_style="carbon_mesh",
        preview_gradient="linear-gradient(135deg, #020617 0%, #0F172A 50%, #475569 100%)",
        is_active_preset=False,
    ),
    ThemeDefinition(
        id="nordic_frost",
        name="Nordic Frost",
        description="Blanc Arctique & Bleu Glace — Énergie lumineuse et respiration visuelle",
        mode="light",
        primary_color="#0284C7",
        secondary_color="#F0F9FF",
        accent_color="#0EA5E9",
        background_style="frost_clean",
        preview_gradient="linear-gradient(135deg, #FFFFFF 0%, #E0F2FE 50%, #0284C7 100%)",
        is_active_preset=False,
    ),
    ThemeDefinition(
        id="champagne_luxury",
        name="Champagne Luxury",
        description="Ivoire Chaud & Bronze — Luxe discret, bijouterie et hospitalité premium",
        mode="light",
        primary_color="#B45309",
        secondary_color="#FFFBEB",
        accent_color="#D97706",
        background_style="warm_cream",
        preview_gradient="linear-gradient(135deg, #FFFBEB 0%, #FEF3C7 50%, #B45309 100%)",
        is_active_preset=False,
    ),
    ThemeDefinition(
        id="cobalt_dynamic",
        name="Cobalt Dynamic",
        description="Bleu Électrique & Cyan Vif — Énergie technologique moderne et SaaS hyper-croissance",
        mode="dark",
        primary_color="#2563EB",
        secondary_color="#172554",
        accent_color="#22D3EE",
        background_style="cobalt_glow",
        preview_gradient="linear-gradient(135deg, #172554 0%, #1E3A8A 50%, #2563EB 100%)",
        is_active_preset=False,
    ),
    ThemeDefinition(
        id="vanguard_onyx",
        name="Vanguard Onyx",
        description="Noir Absolu & Argent Fin — Contraste maximal et immersion trading",
        mode="dark",
        primary_color="#E2E8F0",
        secondary_color="#000000",
        accent_color="#38BDF8",
        background_style="deep_black",
        preview_gradient="linear-gradient(135deg, #000000 0%, #111111 50%, #38BDF8 100%)",
        is_active_preset=False,
    ),
    ThemeDefinition(
        id="meridian_teal",
        name="Meridian Teal",
        description="Sarcelle Profonde & Menthe — Santé, biomédical et précision scientifique",
        mode="dark",
        primary_color="#0D9488",
        secondary_color="#042F2E",
        accent_color="#2DD4BF",
        background_style="teal_deep",
        preview_gradient="linear-gradient(135deg, #042F2E 0%, #134E4A 50%, #0D9488 100%)",
        is_active_preset=False,
    ),
    ThemeDefinition(
        id="apex_crimson",
        name="Apex Crimson",
        description="Rubis Impérial & Braise — Énergie commerciale intense et dépassement d'objectifs",
        mode="dark",
        primary_color="#E11D48",
        secondary_color="#4C0519",
        accent_color="#FB7185",
        background_style="crimson_pulse",
        preview_gradient="linear-gradient(135deg, #4C0519 0%, #881337 50%, #E11D48 100%)",
        is_active_preset=False,
    ),
    ThemeDefinition(
        id="horizon_sunset",
        name="Horizon Sunset",
        description="Ambre Chaud & Coucher de Soleil — Créativité, design studio et commerce de détail",
        mode="dark",
        primary_color="#EA580C",
        secondary_color="#431407",
        accent_color="#FBBF24",
        background_style="sunset_mesh",
        preview_gradient="linear-gradient(135deg, #431407 0%, #7C2D12 50%, #EA580C 100%)",
        is_active_preset=False,
    ),
    ThemeDefinition(
        id="zenith_pearl",
        name="Zenith Pearl",
        description="Perle Irisée & Indigo Doux — Clarté consultative et prestance de cabinet de conseil",
        mode="light",
        primary_color="#4F46E5",
        secondary_color="#FAF5FF",
        accent_color="#818CF8",
        background_style="pearl_clean",
        preview_gradient="linear-gradient(135deg, #FAF5FF 0%, #EDE9FE 50%, #4F46E5 100%)",
        is_active_preset=False,
    ),
    ThemeDefinition(
        id="quantum_midnight",
        name="Quantum Midnight",
        description="Nuit Quantique & Aurore Boréale — Espace cosmique et intelligence de nouvelle génération",
        mode="dark",
        primary_color="#9333EA",
        secondary_color="#030712",
        accent_color="#10B981",
        background_style="quantum_aurora",
        preview_gradient="linear-gradient(135deg, #030712 0%, #1F103A 50%, #10B981 100%)",
        is_active_preset=False,
    ),
)

THEMES_BY_ID: dict[str, ThemeDefinition] = {t.id: t for t in CANDIDATE_THEMES}
DEFAULT_THEME_ID = "avenqo_obsidian"


def get_all_candidate_themes() -> list[dict[str, Any]]:
    return [t.to_dict() for t in CANDIDATE_THEMES]


def get_active_preset_themes() -> list[dict[str, Any]]:
    return [t.to_dict() for t in CANDIDATE_THEMES if t.is_active_preset]


def get_theme(theme_id: str | None) -> ThemeDefinition:
    if theme_id and theme_id in THEMES_BY_ID:
        return THEMES_BY_ID[theme_id]
    return THEMES_BY_ID[DEFAULT_THEME_ID]
