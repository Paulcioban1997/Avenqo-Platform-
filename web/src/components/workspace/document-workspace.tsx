"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";

type DocumentRow = {
  id: string;
  filename: string;
  classification: string | null;
  extracted_text: string;
  disclaimer?: string | null;
  created_at: string | null;
};

export function DocumentWorkspace({
  kind,
  titleFr,
  titleEn,
}: {
  kind: "ocr" | "legal";
  titleFr: string;
  titleEn: string;
}) {
  const { locale } = useLocale();
  const fr = locale.startsWith("fr");
  const [rows, setRows] = useState<DocumentRow[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const endpoint = kind === "ocr" ? "/api/v1/ocr/documents" : "/api/v1/legal/documents";

  const load = useCallback(async () => {
    try {
      const response = await apiFetch(endpoint);
      if (!response.ok) {
        setError(fr ? "Activez le module dans Paramètres pour utiliser cet espace." : "Activate the module in Settings to use this workspace.");
        return;
      }
      setRows(await response.json());
      setError("");
    } catch {
      setError(fr ? "Chargement impossible." : "Unable to load.");
    }
  }, [endpoint, fr]);

  useEffect(() => { void load(); }, [load]);

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    const body = new FormData();
    body.append("file", file);
    try {
      const response = await apiFetch(endpoint, { method: "POST", body });
      if (!response.ok) {
        setError(fr ? "Import refusé. Vérifiez le format et l’activation du module." : "Upload rejected. Check the file format and module activation.");
      } else {
        await load();
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-widest text-cyan-600">Avenqo</p>
        <h1 className="mt-2 text-3xl font-bold">{fr ? titleFr : titleEn}</h1>
        <p className="mt-2 text-sm text-slate-500">
          {fr
            ? "Les extraits proviennent du fichier téléversé. Aucune donnée n’est simulée."
            : "Extracts come from the uploaded file. Nothing is simulated."}
        </p>
      </header>
      {kind === "legal" && (
        <p className="rounded-2xl border border-amber-300/60 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
          {fr
            ? "Assistance documentaire uniquement. Ce n’est pas un avis juridique."
            : "Document assistance only. This is not legal advice."}
        </p>
      )}
      {error && <p role="alert" className="text-sm text-rose-500">{error}</p>}
      <label className="block rounded-2xl border border-dashed border-slate-300 p-6 text-sm dark:border-white/15">
        {fr ? "Téléverser un PDF, DOCX, TXT, CSV ou XLSX" : "Upload a PDF, DOCX, TXT, CSV or XLSX file"}
        <input className="mt-3 block" type="file" disabled={busy} onChange={(event) => void upload(event.target.files?.[0])} />
      </label>
      <ul className="space-y-4">
        {rows.map((row) => (
          <li key={row.id} className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-[#0B132B]">
            <p className="font-semibold">{row.filename}</p>
            <p className="text-xs text-slate-500">{row.classification} · {row.created_at}</p>
            <pre className="mt-3 max-h-56 overflow-auto whitespace-pre-wrap text-sm">{row.extracted_text || (fr ? "Aucun texte extractible." : "No extractable text.")}</pre>
            {row.disclaimer && <p className="mt-3 text-xs text-slate-500">{row.disclaimer}</p>}
          </li>
        ))}
      </ul>
    </div>
  );
}
