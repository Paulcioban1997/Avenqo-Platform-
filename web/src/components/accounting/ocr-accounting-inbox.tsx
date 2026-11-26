"use client";
import { useEffect, useState } from "react";
import { apiFetch, ApiRequestError } from "@/lib/api-request";
import type { EnrichedInvoiceItem } from "@/components/accounting/invoice-detail-drawer";

export function OcrAccountingInbox({ isFr, onSelect }: { isFr: boolean; onSelect: (invoice: EnrichedInvoiceItem) => void }) {
  const [invoices, setInvoices] = useState<Array<EnrichedInvoiceItem & { verification_status?: string }>>([]);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setInvoices([]);
    setError("");
    apiFetch("/api/v1/accounting/invoices?document_scope=true&limit=200")
      .then(response => response.json())
      .then(rows => { if (active) setInvoices(Array.isArray(rows) ? rows : []); })
      .catch(err => { if (active) setError(err instanceof ApiRequestError && err.publicMessage ? err.publicMessage : (isFr ? "Documents indisponibles." : "Documents unavailable.")); });
    return () => { active = false; };
  }, [revision, isFr]);
  return <section id="ocr-documents" className="rounded-2xl border border-slate-700 p-5 space-y-3">
    <div className="flex justify-between gap-4"><h2 className="font-bold">{isFr ? "Documents OCR de l’entreprise" : "Company OCR documents"}</h2>
      <button type="button" onClick={() => setRevision(value => value + 1)}>{isFr ? "Actualiser" : "Refresh"}</button></div>
    <p className="text-sm text-slate-400">{isFr ? "Documents indépendants du fichier sélectionné. Les propositions doivent être vérifiées avant comptabilisation. Jusqu’à 200 documents affichés." : "Documents independent of the selected dataset. Proposals require review before posting. Up to 200 documents shown."}</p>
    {error && <p role="alert">{error}</p>}
    {!error && invoices.length === 0 && <a className="text-blue-500 underline" href="/ocr">{isFr ? "Préparer vos factures depuis OCR AI" : "Prepare invoices in OCR AI"}</a>}
    <ul className="space-y-2">{invoices.map(invoice => <li key={invoice.id}><button type="button" className="w-full rounded-xl border border-slate-700 p-3 text-left" onClick={() => onSelect(invoice)}>
      {invoice.invoice_number} · {invoice.party_name} · {invoice.total_amount} {invoice.currency} · {invoice.verification_status}
    </button></li>)}</ul>
  </section>;
}
