import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VoiceCallPolicy } from "../src/components/voice/voice-call-policy";
vi.mock("@/lib/i18n/locale-context", () => ({ useLocale: () => ({ locale: "fr" }) }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const limits = { enabled: false, plan_duration_seconds: 3600, plan_concurrent_calls: 1,
  auth_max_seconds: 600, cost_rate_configured: false, policy: { max_call_seconds: 3600,
    idle_seconds: 120, concurrent_calls: 1, call_budget_usd: "5", monthly_budget_usd: "50",
    monthly_minutes: 600, alert_percent: 80, auth_seconds: 600 } };
describe("Voice tenant call rules", () => {
  it("reports an invalid backend response without crashing or showing fabricated limits", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({}) })));
    render(<VoiceCallPolicy tenantId="alpha" canManage />);
    await screen.findByRole("alert");
    expect(screen.queryByLabelText("Durée maximale (minutes)")).toBeNull();
  });
  it("saves hour-long limits without activating audio or exposing operator configuration", async () => {
    const fetcher = vi.fn(async () => ({ ok: true, json: async () => limits }));
    vi.stubGlobal("fetch", fetcher);
    render(<VoiceCallPolicy tenantId="alpha" canManage />);
    const duration = await screen.findByLabelText("Durée maximale (minutes)");
    expect(duration).toHaveValue(60);
    expect(duration).toHaveAttribute("max", "60");
    expect(screen.queryByLabelText("Sans durée fixe, dans les limites du budget")).toBeNull();
    fireEvent.change(duration, { target: { value: "30" } });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    await screen.findByText("Limites enregistrées.");
    const request = fetcher.mock.calls as unknown as [string, RequestInit?][];
    expect(request).toHaveLength(2);
    const body = JSON.parse(request[1][1]!.body as string);
    expect(body.max_call_seconds).toBe(1800);
    expect(body.voice_long_calls_enabled).toBeUndefined();
    expect(body.voice_budget_rate_ceiling_usd_per_minute).toBeUndefined();
  });
  it("does not display another tenant's outstanding response after switching", async () => {
    let resolve!: (value: unknown) => void;
    const late = new Promise(r => { resolve = r; });
    const fetcher = vi.fn().mockImplementationOnce(() => late)
      .mockResolvedValue({ ok: true, json: async () => ({ ...limits, policy: { ...limits.policy, max_call_seconds: 1800 } }) });
    vi.stubGlobal("fetch", fetcher);
    const { rerender } = render(<VoiceCallPolicy tenantId="alpha" canManage />);
    rerender(<VoiceCallPolicy tenantId="beta" canManage />);
    expect(await screen.findByLabelText("Durée maximale (minutes)")).toHaveValue(30);
    resolve({ ok: true, json: async () => limits });
    await waitFor(() => expect(screen.getByLabelText("Durée maximale (minutes)")).toHaveValue(30));
  });
});
