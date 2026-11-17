import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VoiceOnboardingWizard } from "../src/components/voice/voice-onboarding-wizard";

vi.mock("@/lib/i18n/locale-context", () => ({
  useLocale: () => ({ locale: "fr" }),
}));

vi.mock("@/lib/api-request", () => ({
  apiFetch: (...args: unknown[]) => fetch(...(args as [string, RequestInit?])),
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("VoiceOnboardingWizard - Personal Employee PIN Workflow", () => {
  it("initializes PIN status using GET /api/v1/voice/auth/pin/status with field adaptation", async () => {
    const fetcher = vi.fn(async (url: string) => {
      if (url.includes("/api/v1/voice/auth/pin/status")) {
        return {
          ok: true,
          json: async () => ({
            has_pin: true,
            phone_access_enabled: true,
            phone_number: "+1514 *** **20",
            is_locked: false,
            failed_attempts: 0,
            active_sessions_count: 1,
          }),
        };
      }
      return { ok: true, json: async () => ({}) };
    });
    vi.stubGlobal("fetch", fetcher);

    render(
      <VoiceOnboardingWizard
        tenantId="tenant-test-a"
        canManage={true}
        businessName="Produits Ero"
      />
    );

    // Open Step 4
    await screen.findByText(/4\. Téléphone et employés/i);
    fireEvent.click(screen.getByText(/4\. Téléphone et employés/i));

    await waitFor(() => {
      expect(screen.getByText(/NIP actif et configuré/i)).toBeInTheDocument();
      expect(screen.getByText(/Modifier votre code NIP personnel employé/i)).toBeInTheDocument();
    });

    const calls = fetcher.mock.calls as unknown as [string, RequestInit?][];
    const pinCalls = calls.filter(([url]) => url.includes("/auth/pin"));
    expect(pinCalls.some(([url]) => url.endsWith("/auth/pin/status"))).toBe(true);
  });

  it("submits PIN creation via PUT /api/v1/voice/auth/pin and requires current password", async () => {
    let pinConfigured = false;
    const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.includes("/api/v1/voice/auth/pin/status")) {
        return {
          ok: true,
          json: async () => ({
            has_pin: pinConfigured,
            phone_access_enabled: pinConfigured,
            phone_number: pinConfigured ? "+1514 *** **20" : null,
            is_locked: false,
            failed_attempts: 0,
          }),
        };
      }
      if (url.includes("/api/v1/voice/auth/pin") && init?.method === "PUT") {
        const payload = JSON.parse(String(init.body));
        if (payload.pin === "849201" && payload.current_password === "SecretPassword123!") {
          pinConfigured = true;
          return {
            ok: true,
            json: async () => ({ status: "CONFIGURED", configured: true, enabled: true }),
          };
        }
      }
      return { ok: true, json: async () => ({}) };
    });
    vi.stubGlobal("fetch", fetcher);

    render(
      <VoiceOnboardingWizard
        tenantId="tenant-test-a"
        canManage={true}
        businessName="Produits Ero"
      />
    );

    await screen.findByText(/4\. Téléphone et employés/i);
    fireEvent.click(screen.getByText(/4\. Téléphone et employés/i));

    // Inputs
    const passwordInput = screen.getByPlaceholderText(/Mot de passe actuel/i);
    const phoneInput = screen.getByPlaceholderText(/\+15142955720/i);
    const pinInputs = screen.getAllByPlaceholderText(/••••••/i);

    fireEvent.change(passwordInput, { target: { value: "SecretPassword123!" } });
    fireEvent.change(phoneInput, { target: { value: "+15142955720" } });
    fireEvent.change(pinInputs[0], { target: { value: "849201" } });
    fireEvent.change(pinInputs[1], { target: { value: "849201" } });

    const submitBtn = screen.getByRole("button", { name: /Enregistrer le NIP|Mettre à jour le NIP/i });
    expect(submitBtn).not.toBeDisabled();
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/NIP personnel configuré et vérifié avec succès/i)
      ).toBeInTheDocument();
    });

    const calls = fetcher.mock.calls as unknown as [string, RequestInit?][];
    const putCall = calls.find(([url, init]) => url.includes("/auth/pin") && init?.method === "PUT");
    expect(putCall).toBeDefined();
    const sentBody = JSON.parse(String(putCall![1]?.body));
    expect(sentBody.pin).toBe("849201");
    expect(sentBody.confirm_pin).toBe("849201");
    expect(sentBody.current_password).toBe("SecretPassword123!");
    expect(sentBody.phone_number).toBe("+15142955720");
  });

  it("handles wrong password rejection (HTTP 403) and displays server error message", async () => {
    const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.includes("/api/v1/voice/auth/pin/status")) {
        return {
          ok: true,
          json: async () => ({ has_pin: false, phone_access_enabled: false }),
        };
      }
      if (url.includes("/api/v1/voice/auth/pin") && init?.method === "PUT") {
        return {
          ok: false,
          status: 403,
          json: async () => ({ detail: "Le mot de passe actuel est incorrect." }),
        };
      }
      return { ok: true, json: async () => ({}) };
    });
    vi.stubGlobal("fetch", fetcher);

    render(
      <VoiceOnboardingWizard
        tenantId="tenant-test-a"
        canManage={true}
        businessName="Produits Ero"
      />
    );

    await screen.findByText(/4\. Téléphone et employés/i);
    fireEvent.click(screen.getByText(/4\. Téléphone et employés/i));

    const passwordInput = screen.getByPlaceholderText(/Mot de passe actuel/i);
    const phoneInput = screen.getByPlaceholderText(/\+15142955720/i);
    const pinInputs = screen.getAllByPlaceholderText(/••••••/i);

    fireEvent.change(passwordInput, { target: { value: "WrongPass" } });
    fireEvent.change(phoneInput, { target: { value: "+15142955720" } });
    fireEvent.change(pinInputs[0], { target: { value: "654321" } });
    fireEvent.change(pinInputs[1], { target: { value: "654321" } });

    fireEvent.click(screen.getByRole("button", { name: /Enregistrer le NIP|Mettre à jour le NIP/i }));

    await waitFor(() => {
      expect(screen.getByText("Le mot de passe actuel est incorrect.")).toBeInTheDocument();
      expect(screen.queryByText(/NIP personnel configuré/i)).toBeNull();
    });
  });

  it("displays lockout warning when status reports is_locked or excessive failed attempts", async () => {
    const fetcher = vi.fn(async (url: string) => {
      if (url.includes("/api/v1/voice/auth/pin/status")) {
        return {
          ok: true,
          json: async () => ({
            has_pin: true,
            phone_access_enabled: false,
            phone_number: "+1514 *** **20",
            is_locked: true,
            failed_attempts: 3,
            locked_until: "2026-11-17T12:00:00Z",
          }),
        };
      }
      return { ok: true, json: async () => ({}) };
    });
    vi.stubGlobal("fetch", fetcher);

    render(
      <VoiceOnboardingWizard
        tenantId="tenant-test-a"
        canManage={true}
        businessName="Produits Ero"
      />
    );

    await screen.findByText(/4\. Téléphone et employés/i);
    fireEvent.click(screen.getByText(/4\. Téléphone et employés/i));

    await waitFor(() => {
      expect(screen.getByText(/Attention : Le NIP est verrouillé/i)).toBeInTheDocument();
    });
  });

  it("strictly isolates multi-tenant credentials between different tenants", async () => {
    const fetcher = vi.fn(async (url: string) => {
      return {
        ok: true,
        json: async () => ({
          has_pin: false,
          phone_access_enabled: false,
          phone_number: null,
          is_locked: false,
        }),
      };
    });
    vi.stubGlobal("fetch", fetcher);

    const { rerender } = render(
      <VoiceOnboardingWizard
        tenantId="tenant-company-1"
        canManage={true}
        businessName="Entreprise 1"
      />
    );

    await screen.findByText(/4\. Téléphone et employés/i);

    rerender(
      <VoiceOnboardingWizard
        tenantId="tenant-company-2"
        canManage={true}
        businessName="Entreprise 2"
      />
    );

    await waitFor(() => {
      expect(screen.queryByText("Entreprise 1")).toBeNull();
      expect(screen.getByText("Entreprise 2")).toBeInTheDocument();
    });
  });
});
