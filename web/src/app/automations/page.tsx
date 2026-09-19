import React from "react";
import { AppShell } from "@/components/shell/app-shell";
import { ModulePreview } from "@/components/common/module-preview";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Automations | Avenqo Enterprise AI",
  description: "Workflows automatisés déclenchés par les événements e-commerce et synchronisations de données.",
};

export default function AutomationsPage() {
  return (
    <AppShell>
      <ModulePreview
        iconType="automations"
        titleEn="AI Automations & Workflows"
        titleFr="Automatisations & Workflows IA"
        descriptionEn="Event-driven autonomous workflows connecting inventory alerts, automated purchase orders, customer notifications, and ledger entries."
        descriptionFr="Flux opérationnels automatisés pilotés par événements : alertes de réapprovisionnement, notifications clients intelligentes et écritures comptables automatiques."
        featuresEn={[
          "Webhook and event triggers for Shopify, WooCommerce, and CSV imports",
          "Automated stock reconciliation with safety threshold alerts",
          "Cross-module triggers: connect Retail AI predictions to Accounting",
          "Visual workflow builder with conditional execution branches",
        ]}
        featuresFr={[
          "Déclencheurs webhooks pour Shopify, WooCommerce et imports CSV",
          "Rapprochement automatique des stocks avec seuils d'alerte configurables",
          "Liaison inter-modules : prédictions Retail AI directement vers Comptabilité",
          "Éditeur visuel de workflows avec branches d'exécution conditionnelles",
        ]}
        badge="Enterprise Automation"
        targetRelease="Q4 2026"
      />
    </AppShell>
  );
}
