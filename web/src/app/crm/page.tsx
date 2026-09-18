import { Metadata } from "next";
import { AppShell } from "@/components/shell/app-shell";
import { CRMView } from "@/components/crm/crm-view";

export const metadata: Metadata = {
  title: "CRM AI & Planification Intelligente | AVENQO",
  description: "Plateforme CRM multi-tenant avec prise de rendez-vous, synchronisation Google Calendar, fiche client 360 et Copilot IA.",
};

export default function CRMPage() {
  return (
    <AppShell>
      <CRMView />
    </AppShell>
  );
}
