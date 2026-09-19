import React from "react";
import { AppShell } from "@/components/shell/app-shell";
import { ModulePreview } from "@/components/common/module-preview";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Chatbots IA | Avenqo Enterprise AI",
  description: "Assistants conversationnels connectés à votre catalogue produit et à votre support client.",
};

export default function ChatbotsPage() {
  return (
    <AppShell>
      <ModulePreview
        iconType="chatbots"
        titleEn="AI Chatbots & Conversational Commerce"
        titleFr="Chatbots IA & Commerce Conversationnel"
        descriptionEn="Embeddable conversational agents grounded directly on your synchronized store catalog, inventory status, and business policies."
        descriptionFr="Agents conversationnels intégrables alimentés en direct par votre catalogue produit, vos stocks et vos politiques de vente."
        featuresEn={[
          "Zero-hallucination answers grounded in store inventory",
          "One-click cart addition and checkout link generation",
          "Omnichannel deployment: Web widget, WhatsApp, Instagram",
          "Seamless handoff to human support with full conversation history",
        ]}
        featuresFr={[
          "Réponses exactes sans hallucination basées sur vos stocks réels",
          "Ajout au panier et génération de liens de paiement en un clic",
          "Déploiement omnicanal : Widget web, WhatsApp, Instagram",
          "Transfert fluide vers vos conseillers avec historique complet",
        ]}
        badge="Conversational AI"
        targetRelease="Q4 2026"
      />
    </AppShell>
  );
}
