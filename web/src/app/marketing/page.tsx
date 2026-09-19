import { Metadata } from "next";
import { AppShell } from "@/components/shell/app-shell";
import { MarketingView } from "@/components/marketing/marketing-view";

export const metadata: Metadata = {
  title: "Marketing & Croissance IA | AVENQO",
  description: "Génération de campagnes automatisées, segmentation prédictive et optimisation du ROI.",
};

export default function MarketingPage() {
  return (
    <AppShell>
      <MarketingView />
    </AppShell>
  );
}
