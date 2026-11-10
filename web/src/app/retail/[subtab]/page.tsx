import { Metadata } from "next";
import { notFound } from "next/navigation";
import { AppShell } from "@/components/shell/app-shell";
import { RetailIntelligenceView, RetailSubTab } from "@/components/retail/retail-intelligence-view";

export const metadata: Metadata = {
  title: "Retail Intelligence & Data Cleaning | AVENQO",
  description: "Pipeline universel de nettoyage de données par IA, prévision de demande et monitoring des stocks en temps réel.",
};

const VALID_TABS: readonly RetailSubTab[] = [
  "overview",
  "sales",
  "products",
  "customers",
  "inventory",
  "forecasts",
  "anomalies",
  "recommendations",
];

export function generateStaticParams() {
  return VALID_TABS.map((subtab) => ({ subtab }));
}

interface RetailSubTabPageProps {
  params: Promise<{ subtab: string }> | { subtab: string };
}

export default async function RetailSubTabPage({ params }: RetailSubTabPageProps) {
  const resolvedParams = await params;
  const subtab = resolvedParams.subtab as RetailSubTab;

  if (!VALID_TABS.includes(subtab)) {
    notFound();
  }

  return (
    <AppShell>
      <RetailIntelligenceView defaultTab={subtab} />
    </AppShell>
  );
}
