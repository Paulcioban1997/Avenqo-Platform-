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
  it("saves and reloads the company's reception language and noise reduction", async () => {
    let stored = { ...setup, profile: { ...setup.profile, input_noise_reduction: "off" } };
    const fetcher = vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === "PUT") stored = { ...stored, profile: JSON.parse(String(init.body)) };
      return { json: async () => stored };
    });
    vi.stubGlobal("fetch", fetcher);
    const first = render(<VoiceBusinessOnboarding tenantId="a" canManage />);
    await screen.findByLabelText("Langue principale");
    fireEvent.change(screen.getByLabelText("Langue principale"), { target: { value: "ro" } });
    fireEvent.change(screen.getByLabelText(/Atténuation du bruit entrant/), { target: { value: "near_field" } });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer mes réglages" }));
    await screen.findByText("Réglages enregistrés.");
    expect(stored.profile.primary_locale).toBe("ro");
    expect(stored.profile.input_noise_reduction).toBe("near_field");
    first.unmount();
    render(<VoiceBusinessOnboarding tenantId="a" canManage />);
    expect(await screen.findByLabelText("Langue principale")).toHaveValue("ro");
    expect(screen.getByLabelText(/Atténuation du bruit entrant/)).toHaveValue("near_field");
  });
  it("preserves CRM split hours and date overrides when saving other settings", async () => {
    const hours = { weekly: { monday: [{ open: "09:00", close: "12:00" }, { open: "13:00", close: "17:00" }] }, date_overrides: { "2030-01-07": [] }, verification_only: true };
    const fetcher = vi.fn(async () => ({ json: async () => ({ ...setup, profile: { ...setup.profile, opening_hours: hours } }) }));
    vi.stubGlobal("fetch", fetcher);
    render(<VoiceBusinessOnboarding tenantId="a" canManage />);
    await screen.findByText(/Horaires CRM/);
    expect(screen.getByText(/09:00–12:00, 13:00–17:00/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer mes réglages" }));
    await screen.findByText("Réglages enregistrés.");
    const calls = fetcher.mock.calls as unknown as [string, RequestInit?][];
    expect(JSON.parse(calls[1][1]!.body as string).opening_hours).toEqual(hours);
  });
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
