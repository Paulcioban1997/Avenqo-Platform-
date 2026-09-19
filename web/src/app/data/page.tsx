import { Metadata } from "next";
import { AppShell } from "@/components/shell/app-shell";
import { DataHubView } from "@/components/data/data-hub-view";

export const metadata: Metadata = {
  title: "Data Hub - Gestion des donnees | AVENQO",
  description: "Centre de donnees Avenqo : importez, gerez, et analysez vos fichiers CSV, Excel, PDF et JSON en toute securite.",
};

export default function DataPage() {
  return (
    <AppShell>
      <DataHubView />
    </AppShell>
  );
}
