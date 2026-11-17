import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import React from "react";
import {
  INDUSTRY_CATALOG,
  INDUSTRY_CATEGORIES,
} from "../src/components/voice/voice-industry-catalog";
import { VoiceOnboardingWizard } from "../src/components/voice/voice-onboarding-wizard";

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
    expect(screen.getByText("Cabinets juridiques / Notaires")).toBeInTheDocument();
    expect(screen.getByText("Pharmacies")).toBeInTheDocument();

    // Toggle button changes to "- Réduire les secteurs"
    expect(screen.getByRole("button", { name: /-.*Réduire les secteurs/i })).toBeInTheDocument();
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
    const searchInput = screen.getByPlaceholderText(/Rechercher parmi les 30 industries/i);
    fireEvent.change(searchInput, { target: { value: "vétérinaire" } });

    expect(screen.getByText(/Vétérinaires/i)).toBeInTheDocument();
    expect(screen.queryByText("Automobile / Pièces")).toBeNull();

    // Clear search
    fireEvent.change(searchInput, { target: { value: "" } });

    // Click Category pill "Santé & Soins"
    const healthPill = screen.getByRole("button", { name: /Santé & Soins/i });
    fireEvent.click(healthPill);

    expect(screen.getByText("Médical / Cliniques")).toBeInTheDocument();
    expect(screen.getByText("Beauté / Bien-être")).toBeInTheDocument();
    expect(screen.getByText("Pharmacies")).toBeInTheDocument();
    expect(screen.getByText("Vétérinaires / Cliniques animales")).toBeInTheDocument();
    expect(screen.queryByText("Automobile / Pièces")).toBeNull();
  });

  it("renders voice capability suggestions panel when an industry is selected", async () => {
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

    // Suggested capabilities for Restaurant must appear in the suggestions banner
    await waitFor(() => {
      expect(
        screen.getByText(/Capacités vocales adaptées à votre secteur \(Restauration \/ Traiteur\)/i)
      ).toBeInTheDocument();
      expect(screen.getByText(/Réservation de table et confirmation par SMS/i)).toBeInTheDocument();
      expect(screen.getByText(/Questions sur les allergènes fondées sur sources vérifiées/i)).toBeInTheDocument();
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
    const customInput = await screen.findByPlaceholderText(/Ex : Blanchisserie industrielle/i);
    expect(customInput).toBeInTheDocument();
    fireEvent.change(customInput, { target: { value: "Robotique Aérospatiale" } });
    expect(customInput).toHaveValue("Robotique Aérospatiale");
  });
});
