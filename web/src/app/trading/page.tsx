import { Metadata } from "next";
import { AppShell } from "@/components/shell/app-shell";
import { TradingView } from "@/components/trading/trading-view";

export const metadata: Metadata = {
  title: "Trading AI | AVENQO",
  description: "Espace démo Trading AI. Aucune cote réelle et aucun conseil d'investissement.",
};

export default function TradingPage() {
  return (
    <AppShell>
      <TradingView />
    </AppShell>
  );
}
