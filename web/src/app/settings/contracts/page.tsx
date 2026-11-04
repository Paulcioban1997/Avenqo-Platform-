import React from "react";
import { AppShell } from "@/components/shell/app-shell";
import { ContractsView } from "@/components/settings/contracts-view";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Documents Juridiques & Contrats | Avenqo Enterprise AI",
  description: "Consultation, signature électronique et gestion des contrats d'entreprise (NDA, abonnement, licence, DPA).",
};

export default function ContractsPage() {
  return (
    <AppShell>
      <ContractsView />
    </AppShell>
  );
}

