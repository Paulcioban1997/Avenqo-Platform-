import React from "react";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CRMCalendarConnectionCard } from "@/components/crm/crm-calendar-connection-card";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
vi.mock("@/lib/i18n/locale-context", () => ({ useLocale: () => ({locale:"fr"}) }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
it("never renders Connected for revoked credentials and does not auto-sync", async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json({ connected:false, provider:"google", connection_status:"RECONNECT_REQUIRED", requires_reconnect:true, sync_status:"error", account_email:"fixture@example.test" }));
  vi.stubGlobal("fetch", fetcher);
  render(<CRMCalendarConnectionCard t={getAppTranslations("fr")} />);
  await screen.findByRole("button", {name:"Reconnecter Google Calendar"});
  expect(screen.queryByText("Connecté", {exact:true})).toBeNull();
  expect(fetcher).toHaveBeenCalledTimes(1);
});
it("shows provider errors rather than a connected footer", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null,{status:503})));
  render(<CRMCalendarConnectionCard t={getAppTranslations("fr")} />);
  await waitFor(() => expect(screen.getAllByText("Erreur de connexion")).toHaveLength(2));
  expect(screen.queryByText("Connecté", {exact:true})).toBeNull();
});
