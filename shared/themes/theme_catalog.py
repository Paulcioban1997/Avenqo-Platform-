"""Catalogue officiel des 30 thèmes visuels Avenqo et Top 5 Recommandés.

Définit les 30 thèmes complets avec identifiants stables, palettes primaires/secondaires/accent,
surfaces, gradients de prévisualisation, mode clair/sombre et catégorisation de style.
Les 5 thèmes recommandés (#1, #2, #3, #9, #21) sont présentés en priorité pour le lancement.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ThemeDefinition:
    id: str
    number: int
    name: str
    description: str
    mode: str  # "dark" | "light"
    category: str  # "corporate" | "luxury" | "tech" | "creative" | "nature"
    primary_color: str
    secondary_color: str
    accent_color: str
    background_style: str
    preview_gradient: str
    is_recommended: bool = False
    is_active_preset: bool = False
    card_border: str = "border-slate-800"
    font_family: str = "Inter, sans-serif"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Catalogue officiel des 30 thèmes Avenqo
ALL_30_THEMES: tuple[ThemeDefinition, ...] = (
    # 1. Avenqo Obsidian (Top 5 #1)
    ThemeDefinition(
        id="avenqo_obsidian",
        number=1,
        name="Avenqo Obsidian",
        description="Bleu électrique, cyan, indigo — L'élégance technique et la puissance analytique signature d'Avenqo",
        mode="dark",
        category="tech",
        primary_color="#0076FF",
        secondary_color="#0B132B",
        accent_color="#00D4FF",
        background_style="mesh_dark",
        preview_gradient="linear-gradient(135deg, #0B132B 0%, #111D3D 50%, #0076FF 100%)",
        is_recommended=True,
        is_active_preset=True,
    ),
    # 2. Titanium Minimal (Top 5 #2)
    ThemeDefinition(
        id="titanium_minimal",
        number=2,
        name="Titanium Minimal",
        description="Blanc, acier, bleu — Clarté architecturale scandinave et lisibilité maximale",
        mode="light",
        category="corporate",
        primary_color="#2563EB",
        secondary_color="#F8FAFC",
        accent_color="#38BDF8",
        background_style="subtle_grid",
        preview_gradient="linear-gradient(135deg, #FFFFFF 0%, #F1F5F9 50%, #2563EB 100%)",
        is_recommended=True,
        is_active_preset=True,
    ),
    # 3. Emerald Enterprise (Top 5 #3)
    ThemeDefinition(
        id="emerald_enterprise",
        number=3,
        name="Emerald Enterprise",
        description="Vert émeraude, menthe — Prestige institutionnel, stabilité financière et croissance durable",
        mode="dark",
        category="corporate",
        primary_color="#059669",
        secondary_color="#064E3B",
        accent_color="#34D399",
        background_style="gradient_dark",
        preview_gradient="linear-gradient(135deg, #064E3B 0%, #0F382C 50%, #059669 100%)",
        is_recommended=True,
        is_active_preset=True,
    ),
    # 4. Royal Sapphire
    ThemeDefinition(
        id="royal_sapphire",
        number=4,
        name="Royal Sapphire",
        description="Bleu saphir, cyan — Confiance bancaire, fintech et rigueur transactionnelle",
        mode="dark",
        category="corporate",
        primary_color="#1D4ED8",
        secondary_color="#0F172A",
        accent_color="#60A5FA",
        background_style="radial_dark",
        preview_gradient="linear-gradient(135deg, #0F172A 0%, #1E293B 50%, #1D4ED8 100%)",
        is_recommended=False,
        is_active_preset=False,
    ),
    # 5. Amethyst Nebula
    ThemeDefinition(
        id="amethyst_nebula",
        number=5,
        name="Amethyst Nebula",
        description="Violet améthyste, lilas — Innovation créative et intelligence artificielle générative",
        mode="dark",
        category="creative",
        primary_color="#7C3AED",
        secondary_color="#1E1B4B",
        accent_color="#C084FC",
        background_style="mesh_purple",
        preview_gradient="linear-gradient(135deg, #1E1B4B 0%, #31104B 50%, #7C3AED 100%)",
        is_recommended=False,
        is_active_preset=False,
    ),
    # 6. Cyberpunk Neon
    ThemeDefinition(
        id="cyberpunk_neon",
        number=6,
        name="Cyberpunk Neon",
        description="Magenta, turquoise, rose — Haute technologie nocturne et avant-garde numérique",
        mode="dark",
        category="tech",
        primary_color="#EC4899",
        secondary_color="#0F172A",
        accent_color="#06B6D4",
        background_style="neon_grid",
        preview_gradient="linear-gradient(135deg, #0F172A 0%, #1E112A 50%, #EC4899 100%)",
        is_recommended=False,
        is_active_preset=False,
    ),
    # 7. Nordic Frost
    ThemeDefinition(
        id="nordic_frost",
        number=7,
        name="Nordic Frost",
        description="Blanc glacier, bleu — Fraîcheur boréale épurée et respiration visuelle",
        mode="light",
        category="nature",
        primary_color="#0284C7",
        secondary_color="#F0F9FF",
        accent_color="#38BDF8",
        background_style="frost_clean",
        preview_gradient="linear-gradient(135deg, #FFFFFF 0%, #E0F2FE 50%, #0284C7 100%)",
        is_recommended=False,
        is_active_preset=False,
    ),
    # 8. Solar Flare
    ThemeDefinition(
        id="solar_flare",
        number=8,
        name="Solar Flare",
        description="Orange, ambre — Énergie commerciale vibrante, dynamisme et vente active",
        mode="dark",
        category="creative",
        primary_color="#EA580C",
        secondary_color="#431407",
        accent_color="#F59E0B",
        background_style="sunset_mesh",
        preview_gradient="linear-gradient(135deg, #431407 0%, #7C2D12 50%, #EA580C 100%)",
        is_recommended=False,
        is_active_preset=False,
    ),
    # 9. Midnight Gold (Top 5 #4)
    ThemeDefinition(
        id="midnight_gold",
        number=9,
        name="Midnight Gold",
        description="Noir, or — Luxe souverain, haute joaillerie et prestance de direction générale",
        mode="dark",
        category="luxury",
        primary_color="#D97706",
        secondary_color="#09090B",
        accent_color="#FBBF24",
        background_style="deep_black",
        preview_gradient="linear-gradient(135deg, #09090B 0%, #1C1917 50%, #D97706 100%)",
        is_recommended=True,
        is_active_preset=True,
    ),
    # 10. Alpine Meadow
    ThemeDefinition(
        id="alpine_meadow",
        number=10,
        name="Alpine Meadow",
        description="Vert prairie, sauge — Écologie, santé naturelle et clarté biologique",
        mode="light",
        category="nature",
        primary_color="#16A34A",
        secondary_color="#F0FDF4",
        accent_color="#4ADE80",
        background_style="meadow_clean",
        preview_gradient="linear-gradient(135deg, #FFFFFF 0%, #DCFCE7 50%, #16A34A 100%)",
        is_recommended=False,
        is_active_preset=False,
    ),
    # 11. Monochrome Slate
    ThemeDefinition(
        id="monochrome_slate",
        number=11,
        name="Monochrome Slate",
        description="Ardoise, argent — Sobriété professionnelle absolue, rigueur comptable et juridique",
        mode="dark",
        category="corporate",
        primary_color="#64748B",
        secondary_color="#0F172A",
        accent_color="#CBD5E1",
        background_style="carbon_mesh",
        preview_gradient="linear-gradient(135deg, #020617 0%, #0F172A 50%, #64748B 100%)",
        is_recommended=False,
        is_active_preset=False,
    ),
    # 12. Rose Quartz
    ThemeDefinition(
        id="rose_quartz",
        number=12,
        name="Rose Quartz",
        description="Rose pastel, quartz — Cosmétique, bien-être et douceur visuelle haut de gamme",
        mode="light",
        category="creative",
        primary_color="#E11D48",
        secondary_color="#FFF1F2",
        accent_color="#FB7185",
        background_style="warm_cream",
        preview_gradient="linear-gradient(135deg, #FFFFFF 0%, #FFE4E6 50%, #E11D48 100%)",
        is_recommended=False,
        is_active_preset=False,
    ),
    # 13. Deep Ocean
    ThemeDefinition(
        id="deep_ocean",
        number=13,
        name="Deep Ocean",
        description="Bleu abyssal, aigue-marine — Stabilité profonde des fonds marins et clarté technologique",
        mode="dark",
        category="nature",
        primary_color="#0369A1",
        secondary_color="#082F49",
        accent_color="#38BDF8",
        background_style="ocean_abyss",
        preview_gradient="linear-gradient(135deg, #082F49 0%, #0C4A6E 50%, #0369A1 100%)",
        is_recommended=False,
        is_active_preset=False,
    ),
    # 14. Crimson Executive
    ThemeDefinition(
        id="crimson_executive",
        number=14,
        name="Crimson Executive",
        description="Rouge rubis, bordeaux — Puissance décisionnelle, leadership et intensité commerciale",
        mode="dark",
        category="luxury",
        primary_color="#DC2626",
        secondary_color="#450A0A",
        accent_color="#EF4444",
        background_style="crimson_pulse",
        preview_gradient="linear-gradient(135deg, #450A0A 0%, #7F1D1D 50%, #DC2626 100%)",
        is_recommended=False,
        is_active_preset=False,
    ),
    # 15. Clean Daylight
    ThemeDefinition(
        id="clean_daylight",
        number=15,
        name="Clean Daylight",
        description="Blanc, bleu ciel — SaaS haute luminosité, modernité sans artifice et travail diurne",
        mode="light",
        category="corporate",
        primary_color="#2563EB",
        secondary_color="#FFFFFF",
        accent_color="#60A5FA",
        background_style="daylight_pure",
        preview_gradient="linear-gradient(135deg, #FFFFFF 0%, #EFF6FF 50%, #2563EB 100%)",
        is_recommended=False,
        is_active_preset=False,
    ),
    # 16. Arctic White
    ThemeDefinition(
        id="arctic_white",
        number=16,
        name="Arctic White",
        description="Blanc pur, bleu glacier — Pureté immaculée et précision clinique",
        mode="light",
        category="nature",
        primary_color="#0EA5E9",
        secondary_color="#F8FAFC",
        accent_color="#7DD3FC",
        background_style="arctic_pure",
        preview_gradient="linear-gradient(135deg, #FFFFFF 0%, #F0F9FF 50%, #0EA5E9 100%)",
        is_recommended=False,
        is_active_preset=False,
    ),
    # 17. Forest Elite
    ThemeDefinition(
        id="forest_elite",
        number=17,
        name="Forest Elite",
        description="Vert forêt, émeraude — Sérénité forestière profonde et croissance organique",
        mode="dark",
        category="nature",
        primary_color="#047857",
        secondary_color="#022C22",
        accent_color="#10B981",
        background_style="forest_deep",
        preview_gradient="linear-gradient(135deg, #022C22 0%, #064E3B 50%, #047857 100%)",
        is_recommended=False,
        is_active_preset=False,
    ),
    # 18. Coral Breeze
    ThemeDefinition(
        id="coral_breeze",
        number=18,
        name="Coral Breeze",
        description="Corail, sable — Chaleur méditerranéenne, restauration et e-commerce convivial",
        mode="light",
        category="creative",
        primary_color="#F97316",
        secondary_color="#FFF7ED",
        accent_color="#FB923C",
        background_style="coral_soft",
        preview_gradient="linear-gradient(135deg, #FFFFFF 0%, #FFEDD5 50%, #F97316 100%)",
        is_recommended=False,
        is_active_preset=False,
    ),
    # 19. Indigo Corporate
    ThemeDefinition(
        id="indigo_corporate",
        number=19,
        name="Indigo Corporate",
        description="Indigo, lavande — Envergure multinationale, cabinet d'audit et autorité institutionnelle",
        mode="dark",
        category="corporate",
        primary_color="#4338CA",
        secondary_color="#1E1B4B",
        accent_color="#818CF8",
        background_style="indigo_deep",
        preview_gradient="linear-gradient(135deg, #1E1B4B 0%, #2E1065 50%, #4338CA 100%)",
        is_recommended=False,
        is_active_preset=False,
    ),
    # 20. Teal Horizon
    ThemeDefinition(
        id="teal_horizon",
        number=20,
        name="Teal Horizon",
        description="Sarcelle, turquoise — Biomédical, pharmacie et technologies de pointe",
        mode="dark",
        category="tech",
        primary_color="#0F766E",
        secondary_color="#042F2E",
        accent_color="#2DD4BF",
        background_style="teal_horizon",
        preview_gradient="linear-gradient(135deg, #042F2E 0%, #115E59 50%, #0F766E 100%)",
        is_recommended=False,
        is_active_preset=False,
    ),
    # 21. Galaxy Orbit (Top 5 #5)
    ThemeDefinition(
        id="galaxy_orbit",
        number=21,
        name="Galaxy Orbit",
        description="Bleu spatial, violet néon — Immersion futuriste, intelligence artificielle et exploration",
        mode="dark",
        category="tech",
        primary_color="#4F46E5",
        secondary_color="#0B0F19",
        accent_color="#8B5CF6",
        background_style="galaxy_stars",
        preview_gradient="linear-gradient(135deg, #0B0F19 0%, #1E1B4B 50%, #4F46E5 100%)",
        is_recommended=True,
        is_active_preset=True,
    ),
    # 22. Sandstone
    ThemeDefinition(
        id="sandstone",
        number=22,
        name="Sandstone",
        description="Sable, bronze — Immobilier, architecture et minéralité noble",
        mode="light",
        category="luxury",
        primary_color="#B45309",
        secondary_color="#FEFCE8",
        accent_color="#D97706",
        background_style="sandstone_warm",
        preview_gradient="linear-gradient(135deg, #FFFFFF 0%, #FEF9C3 50%, #B45309 100%)",
        is_recommended=False,
        is_active_preset=False,
    ),
    # 23. Graphite Pro
    ThemeDefinition(
        id="graphite_pro",
        number=23,
        name="Graphite Pro",
        description="Graphite, acier — Précision industrielle, ingénierie et manufacture avancée",
        mode="dark",
        category="corporate",
        primary_color="#334155",
        secondary_color="#020617",
        accent_color="#94A3B8",
        background_style="graphite_dark",
        preview_gradient="linear-gradient(135deg, #020617 0%, #0F172A 50%, #334155 100%)",
        is_recommended=False,
        is_active_preset=False,
    ),
    # 24. Lavender Dream
    ThemeDefinition(
        id="lavender_dream",
        number=24,
        name="Lavender Dream",
        description="Lavande, perle — Sérénité poétique, mode et créativité stylistique",
        mode="light",
        category="creative",
        primary_color="#8B5CF6",
        secondary_color="#FAF5FF",
        accent_color="#C4B5FD",
        background_style="lavender_light",
        preview_gradient="linear-gradient(135deg, #FFFFFF 0%, #F3E8FF 50%, #8B5CF6 100%)",
        is_recommended=False,
        is_active_preset=False,
    ),
    # 25. Iceberg
    ThemeDefinition(
        id="iceberg",
        number=25,
        name="Iceberg",
        description="Blanc glacier, bleu arctique — Clarté cristalline et fraîcheur boréale",
        mode="light",
        category="nature",
        primary_color="#0284C7",
        secondary_color="#F0F9FF",
        accent_color="#7DD3FC",
        background_style="iceberg_glow",
        preview_gradient="linear-gradient(135deg, #FFFFFF 0%, #E0F2FE 50%, #0284C7 100%)",
        is_recommended=False,
        is_active_preset=False,
    ),
    # 26. Sunset Horizon
    ThemeDefinition(
        id="sunset_horizon",
        number=26,
        name="Sunset Horizon",
        description="Orange, rose, violet — Coucher de soleil crépusculaire et énergie festive",
        mode="dark",
        category="creative",
        primary_color="#F43F5E",
        secondary_color="#3B0764",
        accent_color="#FB7185",
        background_style="sunset_dusk",
        preview_gradient="linear-gradient(135deg, #3B0764 0%, #701A75 50%, #F43F5E 100%)",
        is_recommended=False,
        is_active_preset=False,
    ),
    # 27. Midnight Purple
    ThemeDefinition(
        id="midnight_purple",
        number=27,
        name="Midnight Purple",
        description="Pourpre, magenta — Mystère nocturne, haute gastronomie et club privé",
        mode="dark",
        category="luxury",
        primary_color="#6B21A8",
        secondary_color="#180529",
        accent_color="#C084FC",
        background_style="purple_velvet",
        preview_gradient="linear-gradient(135deg, #180529 0%, #3B0764 50%, #6B21A8 100%)",
        is_recommended=False,
        is_active_preset=False,
    ),
    # 28. Oceanic Mint
    ThemeDefinition(
        id="oceanic_mint",
        number=28,
        name="Oceanic Mint",
        description="Menthe, turquoise — Pureté océanique, biotechnologie et air marin",
        mode="light",
        category="nature",
        primary_color="#0D9488",
        secondary_color="#F0FDFA",
        accent_color="#5EEAD4",
        background_style="mint_fresh",
        preview_gradient="linear-gradient(135deg, #FFFFFF 0%, #CCFBF1 50%, #0D9488 100%)",
        is_recommended=False,
        is_active_preset=False,
    ),
    # 29. Copper Industry
    ThemeDefinition(
        id="copper_industry",
        number=29,
        name="Copper Industry",
        description="Cuivre, anthracite — Force métallurgique, artisanat d'art et solidité industrielle",
        mode="dark",
        category="luxury",
        primary_color="#C2410C",
        secondary_color="#18181B",
        accent_color="#FB923C",
        background_style="copper_forge",
        preview_gradient="linear-gradient(135deg, #18181B 0%, #27272A 50%, #C2410C 100%)",
        is_recommended=False,
        is_active_preset=False,
    ),
    # 30. Aurora Light
    ThemeDefinition(
        id="aurora_light",
        number=30,
        name="Aurora Light",
        description="Bleu ciel, violet, blanc — Lumières d'aurore céleste et clarté optimiste",
        mode="light",
        category="creative",
        primary_color="#3B82F6",
        secondary_color="#F8FAFC",
        accent_color="#8B5CF6",
        background_style="aurora_sky",
        preview_gradient="linear-gradient(135deg, #FFFFFF 0%, #EDE9FE 50%, #3B82F6 100%)",
        is_recommended=False,
        is_active_preset=False,
    ),
)

THEMES_BY_ID: dict[str, ThemeDefinition] = {t.id: t for t in ALL_30_THEMES}
THEMES_BY_NUMBER: dict[int, ThemeDefinition] = {t.number: t for t in ALL_30_THEMES}

DEFAULT_THEME_ID = "avenqo_obsidian"

# Top 5 recommandé officiel désigné par le fondateur : #1, #2, #3, #9, #21
RECOMMENDED_THEME_IDS: tuple[str, ...] = (
    "avenqo_obsidian",
    "titanium_minimal",
    "emerald_enterprise",
    "midnight_gold",
    "galaxy_orbit",
)


def get_all_candidate_themes() -> list[dict[str, Any]]:
    """Retourne la totalité des 30 thèmes officiels."""
    return [t.to_dict() for t in ALL_30_THEMES]


def get_active_preset_themes() -> list[dict[str, Any]]:
    """Retourne les 5 thèmes recommandés prioritaires."""
    return [t.to_dict() for t in ALL_30_THEMES if t.is_recommended]


def get_theme(theme_id: str | None) -> ThemeDefinition:
    if theme_id and theme_id in THEMES_BY_ID:
        return THEMES_BY_ID[theme_id]
    return THEMES_BY_ID[DEFAULT_THEME_ID]
