import React from "react";
import { AppShell } from "@/components/shell/app-shell";
import { ConnectionsView } from "@/components/connections/connections-view";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Connexions | Avenqo Enterprise AI",
  description: "Gestion unifiée des sources de données, importations de fichiers et synchronisation e-commerce Avenqo.",
};

export default function ConnectionsPage() {
  return (
    <AppShell>
      <ConnectionsView />
    </AppShell>
  );
}
