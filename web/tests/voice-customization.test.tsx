import { afterEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { VoiceCustomizationSection } from "@/components/voice/voice-customization-section";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("clears a greeting and rereads saved values without falling back to another endpoint", async () => {
  let greeting = "Bienvenue";
  const fetch = vi.fn(async (url, init) => {
    if (String(url).endsWith("/voices")) return Response.json([{ id: "ballad", name: "Ballad", gender: "neutral", provider: "openai", supported_languages: ["fr"] }]);
    if (init?.method === "PUT") greeting = JSON.parse(init.body).greeting_message;
    return Response.json({ voice_id: "ballad", speech_speed: 1.15, personality_tone: "chaleureux", custom_pronunciation: {}, greeting_message: greeting, farewell_message: "Au revoir" });
  });
  vi.stubGlobal("fetch", fetch);
  render(<VoiceCustomizationSection tenantId="tenant-a" />);
  const save = screen.getByRole("button", { name: "Enregistrer les réglages" });
  await waitFor(() => expect(save).toBeEnabled());
  fireEvent.change(screen.getByPlaceholderText(/Ex: Bonjour et bienvenue/), { target: { value: "" } });
  fireEvent.click(save);
  await screen.findByText("Enregistré avec succès !");
  expect(greeting).toBe("");
  expect(fetch.mock.calls.filter(([url, init]) => String(url).endsWith("/customization") && !init?.method)).toHaveLength(2);
  expect(fetch.mock.calls.some(([url]) => String(url).endsWith("/config"))).toBe(false);
});

it("keeps saving disabled when loading fails", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 403 })));
  render(<VoiceCustomizationSection tenantId="tenant-a" />);
  await screen.findByText(/Impossible de charger les réglages/);
  expect(screen.getByRole("button", { name: "Enregistrer les réglages" })).toBeDisabled();
});
