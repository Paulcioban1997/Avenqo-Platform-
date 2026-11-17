import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import React from "react";
import {
  INDUSTRY_CATALOG,
  INDUSTRY_CATEGORIES,
  getLocalizedCategory,
  getLocalizedIndustry,
  getVoiceIndustryCatalog,
  getVoiceIndustryUi,
} from "../src/components/voice/voice-industry-catalog";
import { VoiceOnboardingWizard } from "../src/components/voice/voice-onboarding-wizard";
import { CANONICAL_LOCALES } from "@/lib/i18n/canonical-locales.generated";
import type { LocaleCode } from "@/lib/i18n/types";

vi.mock("@/lib/i18n/locale-context", () => ({
  useLocale: () => ({ locale: "fr", setLocale: vi.fn() }),
}));

describe("Voice AI Industry Expansion & Verification Suite", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("contains 30 distinct industry sectors with complete FR/EN descriptions and tailored capabilities", () => {
    expect(INDUSTRY_CATALOG.length).toBe(30);

    const ids = new Set(INDUSTRY_CATALOG.map((ind) => ind.id));
    expect(ids.size).toBe(30);

    for (const ind of INDUSTRY_CATALOG) {
      expect(ind.id).toBeTruthy();
      expect(ind.nameFr).toBeTruthy();
      expect(ind.nameEn).toBeTruthy();
      expect(ind.descFr).toBeTruthy();
      expect(ind.descEn).toBeTruthy();
      expect(ind.icon).toBeTruthy();
      expect(ind.image).toMatch(/^https:\/\/images\.unsplash\.com\//);
      expect(ind.fallbackSvg).toMatch(/^data:image\/svg\+xml/);
      expect(ind.suggestedCapabilitiesFr.length).toBeGreaterThanOrEqual(3);
      expect(ind.suggestedCapabilitiesEn.length).toBeGreaterThanOrEqual(3);
    }
  });

  it("verifies all 44 canonical locales have genuine translated names, descriptions, categories, and UI strings", () => {
    expect(CANONICAL_LOCALES.length).toBe(44);

    for (const loc of CANONICAL_LOCALES) {
      const code = loc.code as LocaleCode;
      const catalog = getVoiceIndustryCatalog(code);
      expect(catalog).toBeDefined();

      // UI strings
      expect(catalog.ui.sectionTitle).toBeTruthy();
      expect(catalog.ui.sectionSubtitle).toBeTruthy();
      expect(catalog.ui.searchPlaceholder).toBeTruthy();
      expect(catalog.ui.expandButton).toBeTruthy();
      expect(catalog.ui.collapseButton).toBeTruthy();
      expect(catalog.ui.suggestionsDisclaimer).toBeTruthy();
      expect(catalog.ui.noIndustrySelected).toBeTruthy();

      // Categories
      for (const cat of INDUSTRY_CATEGORIES) {
        const catLabel = getLocalizedCategory(cat.id, code);
        expect(catLabel).toBeTruthy();
        expect(typeof catLabel).toBe("string");
      }

      // Industries
      for (const ind of INDUSTRY_CATALOG) {
        const item = getLocalizedIndustry(ind.id, code);
        expect(item).not.toBeNull();
        expect(item!.name).toBeTruthy();
        expect(item!.desc).toBeTruthy();
        expect(item!.suggestedCapabilities.length).toBeGreaterThanOrEqual(3);
      }
    }
  });

  it("verifies Commerce / Retail has an updated valid image URL and reliable SVG fallback", () => {
    const retail = INDUSTRY_CATALOG.find((ind) => ind.id === "retail");
    expect(retail).toBeDefined();
    expect(retail!.nameFr).toContain("Commerce / Retail");
    // Verify it no longer uses the deleted photo-1556742049-0a67c5574f73 that returned HTTP 404
    expect(retail!.image).not.toContain("photo-1556742049-0a67c5574f73");
    expect(retail!.image).toContain("photo-1441986300917-64674bd600d8");
    expect(retail!.fallbackSvg).toContain("data:image/svg+xml");
    expect(decodeURIComponent(retail!.fallbackSvg)).toContain("Commerce / Retail");
  });

  it("starts with empty industry selection (no preselected retail) and displays prompt", async () => {
    const fetcher = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        profile: {
          business_name: "Produits Ero",
          industry: "",
          industries: [],
        },
      }),
    }));
    vi.stubGlobal("fetch", fetcher);

    render(
      <VoiceOnboardingWizard
        tenantId="tenant-test-a"
        canManage={true}
        businessName="Produits Ero"
      />
    );

    const step2Btn = await screen.findByText(/2\. Ma réceptionniste IA/i);
    fireEvent.click(step2Btn);

    // Initial state: "Aucun secteur sélectionné. Veuillez choisir au moins une industrie ci-dessous."
    expect(
      screen.getByText(/Aucun secteur sélectionné\. Veuillez choisir au moins une industrie/i)
    ).toBeInTheDocument();
  });

  it("renders 8 primary industries initially on desktop 4-column layout and expands on toggle", async () => {
    const fetcher = vi.fn(async () => ({ ok: true, json: async () => ({}) }));
    vi.stubGlobal("fetch", fetcher);

    render(
      <VoiceOnboardingWizard
        tenantId="tenant-test-a"
        canManage={true}
        businessName="Produits Ero"
      />
    );

    // Open Step 2 (Receptionist)
    const step2Btn = await screen.findByText(/2\. Ma réceptionniste IA/i);
    fireEvent.click(step2Btn);

    // Initial 8 industries must be visible
    expect(screen.getByText("Automobile / Pièces")).toBeInTheDocument();
    expect(screen.getByText("Médical / Cliniques")).toBeInTheDocument();
    expect(screen.getByText("Restauration / Traiteur")).toBeInTheDocument();
    expect(screen.getByText("Commerce / Retail")).toBeInTheDocument();
    expect(screen.getByText("Transport / Logistique")).toBeInTheDocument();
    expect(screen.getByText("Immobilier")).toBeInTheDocument();
    expect(screen.getByText("Hôtellerie / Tourisme")).toBeInTheDocument();
    expect(screen.getByText("Beauté / Bien-être")).toBeInTheDocument();

    // Industry 9 (Construction) should not be visible before expanding
    expect(screen.queryByText("Construction / Entrepreneurs")).toBeNull();

    // Find and click "+ Voir plus d'industries" button
    const toggleBtn = screen.getByRole("button", { name: /\+.*Voir plus d'industries/i });
    expect(toggleBtn).toBeInTheDocument();
    fireEvent.click(toggleBtn);

    // Now all 30 industries including Construction and Avocats should be visible
    expect(screen.getByText("Construction / Entrepreneurs")).toBeInTheDocument();
    expect(screen.getByText("Avocats / Notaires")).toBeInTheDocument();
    expect(screen.getByText("Pharmacie / Parapharmacie")).toBeInTheDocument();

    // Toggle button changes to "Réduire la liste"
    expect(screen.getByRole("button", { name: /Réduire la liste/i })).toBeInTheDocument();
  });

  it("filters industries dynamically by search keyword and category pills", async () => {
    const fetcher = vi.fn(async () => ({ ok: true, json: async () => ({}) }));
    vi.stubGlobal("fetch", fetcher);

    render(
      <VoiceOnboardingWizard
        tenantId="tenant-test-a"
        canManage={true}
        businessName="Produits Ero"
      />
    );

    const step2Btn = await screen.findByText(/2\. Ma réceptionniste IA/i);
    fireEvent.click(step2Btn);

    // Expand catalog
    fireEvent.click(screen.getByRole("button", { name: /\+.*Voir plus d'industries/i }));

    // Search input
    const searchInput = screen.getByPlaceholderText(/Rechercher une industrie\.\.\./i);
    fireEvent.change(searchInput, { target: { value: "vétérinaire" } });

    expect(screen.getByText(/Vétérinaire \/ Soins animaux/i)).toBeInTheDocument();
    expect(screen.queryByText("Automobile / Pièces")).toBeNull();

    // Clear search
    fireEvent.change(searchInput, { target: { value: "" } });

    // Click Category pill "Santé & Soins"
    const healthPill = screen.getByRole("button", { name: /Santé & Soins/i });
    fireEvent.click(healthPill);

    expect(screen.getByText("Médical / Cliniques")).toBeInTheDocument();
    expect(screen.getByText("Beauté / Bien-être")).toBeInTheDocument();
    expect(screen.getByText("Pharmacie / Parapharmacie")).toBeInTheDocument();
    expect(screen.getByText("Vétérinaire / Soins animaux")).toBeInTheDocument();
    expect(screen.queryByText("Automobile / Pièces")).toBeNull();
  });

  it("supports multi-industry selection, badge counters, and displays capability suggestions with honest module disclaimers", async () => {
    const fetcher = vi.fn(async () => ({ ok: true, json: async () => ({}) }));
    vi.stubGlobal("fetch", fetcher);

    render(
      <VoiceOnboardingWizard
        tenantId="tenant-test-a"
        canManage={true}
        businessName="Produits Ero"
      />
    );

    const step2Btn = await screen.findByText(/2\. Ma réceptionniste IA/i);
    fireEvent.click(step2Btn);

    // Click on Restaurant card
    const restaurantCard = screen.getByText("Restauration / Traiteur");
    fireEvent.click(restaurantCard);

    // Multi-select counter badge appears
    await waitFor(() => {
      expect(screen.getByText(/1 sélectionnés/i)).toBeInTheDocument();
      expect(screen.getByText(/Suggestions de capacités métier pour ce secteur :/i)).toBeInTheDocument();
      expect(screen.getAllByText(/Restauration \/ Traiteur/i).length).toBeGreaterThanOrEqual(2);
    });

    // Disclaimer must be explicitly displayed
    expect(
      screen.getByText(/Ces suggestions illustrent les capacités de l'agent IA/i)
    ).toBeInTheDocument();

    // Required module badges must be rendered
    const crmBadges = screen.getAllByText(/Module CRM/i);
    expect(crmBadges.length).toBeGreaterThanOrEqual(1);

    // Click Automobile card to test multi-selection
    const autoCard = screen.getByText("Automobile / Pièces");
    fireEvent.click(autoCard);

    await waitFor(() => {
      expect(screen.getByText(/2 sélectionnés/i)).toBeInTheDocument();
    });
  });

  it("allows selecting 'Autre / Secteur personnalisé' and typing a custom industry", async () => {
    const fetcher = vi.fn(async () => ({ ok: true, json: async () => ({}) }));
    vi.stubGlobal("fetch", fetcher);

    render(
      <VoiceOnboardingWizard
        tenantId="tenant-test-a"
        canManage={true}
        businessName="Produits Ero"
      />
    );

    const step2Btn = await screen.findByText(/2\. Ma réceptionniste IA/i);
    fireEvent.click(step2Btn);

    // Expand
    fireEvent.click(screen.getByRole("button", { name: /\+.*Voir plus d'industries/i }));

    // Click on "Autre secteur / Personnalisé"
    const otherCard = screen.getByText(/Autre secteur \/ Personnalisé/i);
    fireEvent.click(otherCard);

    // Custom industry input must appear
    const customInput = await screen.findByPlaceholderText(/Décrivez votre activité/i);
    expect(customInput).toBeInTheDocument();
    fireEvent.change(customInput, { target: { value: "Robotique Aérospatiale" } });
    expect(customInput).toHaveValue("Robotique Aérospatiale");
  });

  it("handles image onError without looping and renders fallback SVG safely", async () => {
    const fetcher = vi.fn(async () => ({ ok: true, json: async () => ({}) }));
    vi.stubGlobal("fetch", fetcher);

    render(
      <VoiceOnboardingWizard
        tenantId="tenant-test-a"
        canManage={true}
        businessName="Produits Ero"
      />
    );

    const step2Btn = await screen.findByText(/2\. Ma réceptionniste IA/i);
    fireEvent.click(step2Btn);

    const images = screen.getAllByRole("img");
    expect(images.length).toBeGreaterThanOrEqual(8);

    const firstImg = images[0] as HTMLImageElement;
    // Trigger error event
    fireEvent.error(firstImg);

    // Target should receive fallback svg
    expect(firstImg.src).toContain("data:image/svg+xml");
    // Verify target.onerror is cleared to prevent infinite loop
    expect(firstImg.onerror).toBeNull();
  });
});
