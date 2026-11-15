import { Metadata } from "next";
import { AppShell } from "@/components/shell/app-shell";
import { TradingView } from "@/components/trading/trading-view";

export const metadata: Metadata = {
  title: "Trading AI | AVENQO",
  description: "Cours crypto publics Binance et Coinbase. Aucun ordre et aucun conseil d'investissement.",
};

export default function TradingPage() {
  return (
    <AppShell>
      <TradingView />
    </AppShell>
  );
}
