import React from "react";
import { AppShell } from "@/components/shell/app-shell";
import { SettingsView } from "@/components/settings/settings-view";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Paramètres | Avenqo Enterprise AI",
  description: "Configuration de l'organisation, gestion des droits et activation des modules Avenqo.",
};

export default function SettingsPage() {
  return (
    <AppShell>
      <SettingsView />
    </AppShell>
  );
}
