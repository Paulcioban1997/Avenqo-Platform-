import React from "react";
import { AppShell } from "@/components/shell/app-shell";
import { ModulePreview } from "@/components/common/module-preview";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Agents IA | Avenqo Enterprise AI",
  description: "Flotte d'agents spécialisés autonomes collaborant pour piloter la chaîne logistique et commerciale.",
};

export default function AgentsPage() {
  return (
    <AppShell>
      <ModulePreview
        iconType="agents"
        titleEn="Autonomous AI Agents Fleet"
        titleFr="Flotte d'Agents IA Autonomes"
        descriptionEn="Multi-agent orchestration where specialized agents coordinate sales forecasting, supplier negotiations, and marketing execution."
        descriptionFr="Orchestration multi-agents où des agents spécialisés collaborent pour la prévision des ventes, les alertes fournisseurs et l'exécution marketing."
        featuresEn={[
          "Multi-agent collaborative problem solving with human-in-the-loop validation",
          "Automated pricing optimization based on margin targets and competitor feeds",
          "Deep grounding in your isolated tenant database and connected stores",
          "Comprehensive execution audit logs and explainability traces",
        ]}
        featuresFr={[
          "Résolution collaborative multi-agents avec validation supervisée",
          "Optimisation dynamique des prix selon vos marges cibles et vos concurrents",
          "Ancrage strict sur vos données d'entreprise et vos boutiques connectées",
          "Traçabilité complète des décisions avec journal d'audit transparent",
        ]}
        badge="Multi-Agent System"
        targetRelease="Q4 2026"
      />
    </AppShell>
  );
}
