import { Metadata } from "next";
import { AppShell } from "@/components/shell/app-shell";
import { DashboardView } from "@/components/dashboard/dashboard-view";

export const metadata: Metadata = {
  title: "Dashboard Enterprise | AVENQO",
  description: "Vue d'ensemble opérationnelle, métriques de performance en temps réel et synthèses IA multi-agents.",
};

export default function DashboardPage() {
  return (
    <AppShell>
      <DashboardView />
    </AppShell>
  );
}
