import React from "react";
import { AppShell } from "@/components/shell/app-shell";
import { ModulePreview } from "@/components/common/module-preview";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Voice AI | Avenqo Enterprise AI",
  description: "Agent vocal intelligent et synthèse conversationnelle pour le commerce et le service client.",
};

export default function VoicePage() {
  return (
    <AppShell>
      <ModulePreview
        iconType="voice"
        titleEn="Voice AI Agent"
        titleFr="Agent Vocal & Téléphonie IA"
        descriptionEn="Autonomous voice agents capable of handling customer inbound and outbound calls, order status inquiries, and appointment scheduling with human-like latency."
        descriptionFr="Agents vocaux autonomes capables de traiter les appels entrants et sortants, le suivi des commandes et la prise de rendez-vous avec une latence quasi instantanée."
        featuresEn={[
          "Sub-500ms voice response latency",
          "Multi-lingual real-time speech translation",
          "Automated CRM logging and sentiment analysis",
          "Direct integration with Shopify and WooCommerce order status",
        ]}
        featuresFr={[
          "Latence de réponse vocale inférieure à 500ms",
          "Traduction vocale multilingue en temps réel",
          "Journalisation automatique dans le CRM avec analyse de sentiment",
          "Intégration directe aux états de commandes Shopify et WooCommerce",
        ]}
        badge="Voice Intelligence"
        targetRelease="Q4 2026"
      />
    </AppShell>
  );
}
