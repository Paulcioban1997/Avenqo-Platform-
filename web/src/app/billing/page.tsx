import { Metadata } from "next";
import { AppShell } from "@/components/shell/app-shell";
import { BillingView } from "@/components/billing/billing-view";

export const metadata: Metadata = {
  title: "Facturation & Crédits IA | AVENQO",
  description: "Gérez votre abonnement, vos factures certifiées et votre solde de crédits IA Avenqo.",
};

export default function BillingPage() {
  return (
    <AppShell>
      <BillingView />
    </AppShell>
  );
}
