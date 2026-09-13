import { Metadata } from "next";
import { AppShell } from "@/components/shell/app-shell";
import { RetailIntelligenceView } from "@/components/retail/retail-intelligence-view";

export const metadata: Metadata = {
  title: "Retail Intelligence & Data Cleaning | AVENQO",
  description: "Pipeline universel de nettoyage de données par IA, prévision de demande et monitoring des stocks en temps réel.",
};

export default function RetailPage() {
  return (
    <AppShell>
      <RetailIntelligenceView />
    </AppShell>
  );
}
