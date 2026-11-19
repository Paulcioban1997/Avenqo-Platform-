import { AppShell } from "@/components/shell/app-shell";
import { HRWorkspace } from "@/components/hr/hr-workspace";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Ressources Humaines & Hiérarchie | Avenqo",
  description: "Organigramme, SOPs par industrie, compétences, gestion des congés et Voice Coach.",
  robots: { index: false, follow: false },
};

export default function HRPage() {
  return (
    <AppShell>
      <HRWorkspace />
    </AppShell>
  );
}
