"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-request";

type InvoiceEvidence = {
  sheet_name: string | null;
  vendor: string | null;
  issue_date: string | null;
  description: string | null;
  currency: string | null;
  math_verified: boolean;
  total_amount: { amount: string; amount_formatted_fr: string; cell_ref: string } | null;
};
type SourceDocument = { dataset_id: string; name: string; status: string; extraction: { invoices: InvoiceEvidence[] } | null };

export function SelectedDocumentInvoices({ isFr }: { isFr: boolean }) {
  const [documents, setDocuments] = useState<SourceDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true); setError(false); setDocuments([]);
    apiFetch("/api/v1/accounting/selected-documents")
      .then(response => response.json())
      .then(result => { if (active) setDocuments(result.documents ?? []); })
      .catch(() => { if (active) setError(true); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [revision]);
  return <section className="rounded-2xl border border-slate-200 dark:border-white/10 p-5 space-y-3">
    <div className="flex justify-between gap-4">
      <h2 className="font-bold">{isFr ? "Factures dans les fichiers sélectionnés" : "Invoices in selected files"}</h2>
      <button type="button" onClick={() => setRevision(value => value + 1)} disabled={loading}>{isFr ? "Actualiser la lecture" : "Refresh document reading"}</button>
    </div>
    <p className="text-sm">{isFr ? "Lecture des pièces originales. Ces montants restent à vérifier et sont exclus des soldes comptabilisés." : "Original document readings. These amounts require review and are excluded from posted balances."}</p>
    {loading && <p role="status">{isFr ? "Lecture en cours…" : "Reading…"}</p>}
    {error && <p role="alert">{isFr ? "Lecture indisponible. Aucun montant n’a été supposé." : "Reading unavailable. No amounts were assumed."}</p>}
    {!loading && !error && documents.length === 0 && <p>{isFr ? "Aucun fichier sélectionné et autorisé." : "No selected and authorized file."}</p>}
    {documents.map(document => <article key={document.dataset_id} className="rounded-xl border border-slate-200 dark:border-white/10 p-3 space-y-2">
      <h3 className="font-semibold">{document.name}</h3>
      {document.status !== "read" && <p role="alert">{isFr ? "Original indisponible : lecture non validée." : "Original unavailable: reading not verified."}</p>}
      {document.status === "read" && !document.extraction?.invoices.some(invoice => invoice.total_amount) && <p>{isFr ? "Aucun montant de facture identifiable dans cette pièce." : "No identifiable invoice amount in this document."}</p>}
      {document.extraction?.invoices.filter(invoice => invoice.total_amount).map((invoice, index) => <div key={`${invoice.sheet_name}:${index}`} className="text-sm space-y-1">
        <p>{invoice.vendor} · {invoice.issue_date} · {invoice.sheet_name}</p>
        <p>{invoice.description}</p>
        <p className="font-semibold">{isFr ? invoice.total_amount?.amount_formatted_fr : invoice.total_amount?.amount} {invoice.currency ?? (isFr ? "(devise non spécifiée)" : "(currency unspecified)")}</p>
        <p>{invoice.total_amount?.cell_ref} · {invoice.math_verified ? (isFr ? "Calcul vérifié" : "Arithmetic verified") : (isFr ? "Calcul à vérifier" : "Arithmetic requires review")}</p>
      </div>)}
    </article>)}
  </section>;
}
