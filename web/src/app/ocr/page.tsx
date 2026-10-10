import { AppShell } from "@/components/shell/app-shell";
import { DocumentWorkspace } from "@/components/workspace/document-workspace";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "OCR AI | Avenqo",
  description: "Téléversement sécurisé et extraction réelle de documents d'entreprise.",
};

export default function OcrPage() {
  return (
    <AppShell>
      <DocumentWorkspace kind="ocr" titleFr="OCR AI" titleEn="OCR AI" />
    </AppShell>
  );
}
