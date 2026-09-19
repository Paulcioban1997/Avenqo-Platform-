import { Metadata } from "next";
import { AppShell } from "@/components/shell/app-shell";
import { AccountingView } from "@/components/accounting/accounting-view";

export const metadata: Metadata = {
  title: "Comptabilité & Finance IA | AVENQO",
  description: "Gestion financière consolidée, grand livre, flux de trésorerie et détection d'anomalies IA.",
};

export default function AccountingPage() {
  return (
    <AppShell>
      <AccountingView />
    </AppShell>
  );
}
