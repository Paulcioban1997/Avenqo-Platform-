import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VoiceBusinessOnboarding } from "../src/components/voice/voice-business-onboarding";
vi.mock("@/lib/i18n/locale-context", () => ({ useLocale: () => ({ locale: "fr" }) }));
vi.mock("@/lib/api-request", () => ({ apiFetch: (...args: unknown[]) => fetch(...args as [string, RequestInit?]) }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const setup = { profile: { expected_version: 1, business_name: "Entreprise A", industry: "Custom", description: "",
  activities: [], locations: [], timezone: "America/Toronto", opening_hours: {}, primary_locale: "fr", secondary_locales: [],
  contact_phone: null, website: "", bookable_service_ids: [], allowed_actions: [], cancellation_policy: "",
  communication_style: "professional", accent_preference: "", vocabulary: [] }, industry_suggestions: [], context_version: "fixture",
  services: [{ id: "service-a", name: "Démonstration produits", duration_minutes: 15, price: 0, currency: "CAD" }],
  actions: [{ id: "crm:create_appointment", module: "crm", granted: false, module_active: true }],
  readiness: { configuration_saved: true, booking_authorized: false, telephone_verified: false } };

describe("Business-aware Voice onboarding", () => {
  it("requires management access and never claims telephone acceptance", async () => {
    const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher);
    render(<VoiceBusinessOnboarding tenantId="a" canManage={false} />);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("saves canonical services without granting a permission or activating audio", async () => {
    const fetcher = vi.fn(async () => ({ json: async () => setup })); vi.stubGlobal("fetch", fetcher);
    render(<VoiceBusinessOnboarding tenantId="a" canManage />);
    await screen.findByLabelText("Nom de l’entreprise");
    fireEvent.click(screen.getByRole("button", { name: "2. Produits et rendez-vous" }));
    fireEvent.click(screen.getByRole("checkbox", { name: /Démonstration produits/ }));
    fireEvent.click(screen.getByRole("button", { name: "3. Capacités autorisées" }));
    expect(screen.getByRole("checkbox", { name: /Créer un rendez-vous/ })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer mes réglages" }));
    await screen.findByText("Réglages enregistrés.");
    const calls = fetcher.mock.calls as unknown as [string, RequestInit?][];
    const body = JSON.parse(calls[1][1]!.body as string);
    expect(body.bookable_service_ids).toEqual(["service-a"]);
    expect(body.allowed_actions).toEqual([]);
    expect(body.company_id).toBeUndefined();
    expect(body.enabled).toBeUndefined();
    expect(body.voice_provider).toBeUndefined();
  });
  it("does not show a late response belonging to another company", async () => {
    let resolve!: (value: unknown) => void;
    const late = new Promise(r => { resolve = r; });
    const fetcher = vi.fn().mockImplementationOnce(() => late).mockResolvedValue({ json: async () => ({ ...setup, profile: { ...setup.profile, business_name: "Entreprise B" } }) });
    vi.stubGlobal("fetch", fetcher);
    const { rerender } = render(<VoiceBusinessOnboarding tenantId="a" canManage />);
    rerender(<VoiceBusinessOnboarding tenantId="b" canManage />);
    expect(await screen.findByLabelText("Nom de l’entreprise")).toHaveValue("Entreprise B");
    resolve({ json: async () => setup });
    await waitFor(() => expect(screen.getByLabelText("Nom de l’entreprise")).toHaveValue("Entreprise B"));
  });
  it("fails visibly on malformed data instead of showing invented defaults", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ json: async () => ({}) })));
    render(<VoiceBusinessOnboarding tenantId="a" canManage />);
    await screen.findByRole("alert");
    expect(screen.queryByLabelText("Nom de l’entreprise")).toBeNull();
  });
});
