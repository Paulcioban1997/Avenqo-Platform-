import React from "react";
import { AppShell } from "@/components/shell/app-shell";
import { ModulePreview } from "@/components/common/module-preview";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "OCR AI | Avenqo Enterprise AI",
  description: "Extraction automatique et structuration des factures, bons de commande et reçus par vision IA.",
};

export default function OcrPage() {
  return (
    <AppShell>
      <ModulePreview
        iconType="ocr"
        titleEn="Document OCR & Vision AI"
        titleFr="Numérisation & OCR Intelligent"
        descriptionEn="High-accuracy document extraction for invoices, delivery slips, and vendor receipts. Automatically reconciles records with your accounting ledger."
        descriptionFr="Extraction haute fidélité pour factures fournisseurs, bons de livraison et reçus. Rapprochement automatique avec votre grand livre comptable."
        featuresEn={[
          "Instant parsing of PDF, JPEG, PNG, and TIFF documents",
          "Automatic line-item extraction with tax breakdown",
          "Automated ledger entry into Avenqo Accounting module",
          "Secure per-tenant document storage with retention controls",
        ]}
        featuresFr={[
          "Analyse instantanée des PDF, JPEG, PNG et TIFF",
          "Extraction automatique des lignes de détail et taxes",
          "Écriture automatique dans le module Comptabilité Avenqo",
          "Stockage sécurisé scellé par organisation avec règles de rétention",
        ]}
        badge="Vision AI"
        targetRelease="Q4 2026"
      />
    </AppShell>
  );
}
