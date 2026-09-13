import { Metadata } from "next";
import { AppShell } from "@/components/shell/app-shell";
import { IntegrationsHubView } from "@/components/integrations/integrations-hub-view";

export const metadata: Metadata = {
  title: "Hub d'Intégrations & Connecteurs | AVENQO",
  description: "Connectez vos sources de vente, marketing et comptabilité pour alimenter le registre unifié d'AVENQO.",
};

export default function IntegrationsPage() {
  return (
    <AppShell>
      <IntegrationsHubView />
    </AppShell>
  );
}
