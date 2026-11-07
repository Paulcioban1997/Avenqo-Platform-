import { AppShell } from "@/components/shell/app-shell";
import { DocumentWorkspace } from "@/components/workspace/document-workspace";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Legal AI | Avenqo",
  description: "Assistance documentaire juridique avec limites clairement affichées.",
};

export default function LegalPage() {
  return (
    <AppShell>
      <DocumentWorkspace kind="legal" titleFr="Legal AI" titleEn="Legal AI" />
    </AppShell>
  );
}
