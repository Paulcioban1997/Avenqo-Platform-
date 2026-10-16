"use client";

import { useCallback, useEffect, useState, useRef } from "react";
import { apiFetch, ApiRequestError } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";
import {
  FileText,
  Upload,
  Trash2,
  AlertTriangle,
  CheckCircle,
  Sparkles,
  RefreshCw,
  Lock,
  ArrowRight,
  Eye,
  FileCheck,
} from "lucide-react";

type DocumentRow = {
  id: string;
  filename: string;
  classification: string | null;
  byte_size?: number;
  extracted_text: string;
  analysis?: Record<string, unknown> | null;
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
  const [error, setError] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [activating, setActivating] = useState(false);
  const [isInactive, setIsInactive] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const endpoint = kind === "ocr" ? "/api/v1/ocr/documents" : "/api/v1/legal/documents";

  const load = useCallback(async () => {
    try {
      const response = await apiFetch(endpoint);
      const data = await response.json();
      setRows(Array.isArray(data) ? data : []);
      setError("");
      setIsInactive(false);
    } catch (err) {
      if (err instanceof ApiRequestError) {
        if (err.status === 403 || err.category === "unauthorized") {
          setIsInactive(true);
          setError("");
          return;
        }
        setError(err.publicMessage || (fr ? "Erreur de connexion au serveur." : "Server connection error."));
      } else {
        setError(fr ? "Chargement impossible." : "Unable to load.");
      }
    }
  }, [endpoint, fr]);

  useEffect(() => {
    void load();
  }, [load]);

  const activateModule = async () => {
    setActivating(true);
    setError("");
    try {
      const response = await apiFetch(`/api/v1/modules/${kind}/activate`, {
        method: "POST",
      });
      if (response.ok) {
        setIsInactive(false);
        if (typeof window !== "undefined") {
          window.dispatchEvent(new CustomEvent("avenqo:sources-changed"));
        }
        await load();
      }
    } catch (err) {
      if (err instanceof ApiRequestError) {
        setError(
          err.publicMessage ||
            (fr
              ? "Impossible d'activer ce module. Vérifiez votre abonnement."
              : "Unable to activate this module. Please check your subscription.")
        );
      } else {
        setError(fr ? "Erreur lors de l'activation." : "Activation error.");
      }
    } finally {
      setActivating(false);
    }
  };

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    setError("");
    const body = new FormData();
    body.append("file", file);
    try {
      const response = await apiFetch(endpoint, { method: "POST", body });
      if (response.ok) {
        if (fileInputRef.current) fileInputRef.current.value = "";
        await load();
      }
    } catch (err) {
      if (err instanceof ApiRequestError) {
        if (err.status === 403) {
          setIsInactive(true);
        } else {
          setError(
            err.publicMessage ||
              (fr
                ? "Format de fichier non supporté ou analyse impossible. (Formats autorisés : PDF, DOCX, TXT, CSV, XLSX)"
                : "Unsupported file format or extraction failed. (Allowed: PDF, DOCX, TXT, CSV, XLSX)")
          );
        }
      } else {
        setError(
          fr
            ? "Import refusé. Vérifiez le format et l'activation du module."
            : "Upload rejected. Check the file format and module activation."
        );
      }
    } finally {
      setBusy(false);
    }
  };

  const deleteDoc = async (id: string) => {
    if (!confirm(fr ? "Supprimer ce document ?" : "Delete this document?")) return;
    setDeletingId(id);
    try {
      const response = await apiFetch(`${endpoint}/${id}`, { method: "DELETE" });
      if (response.ok || response.status === 204) {
        setRows((prev) => prev.filter((r) => r.id !== id));
      }
    } catch {
      setError(fr ? "Impossible de supprimer ce document." : "Failed to delete document.");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 animate-in fade-in duration-300">
      <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-slate-200 dark:border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold uppercase tracking-widest text-[#0076FF] dark:text-[#00D4FF]">
              Avenqo {kind.toUpperCase()} AI
            </span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300 font-medium">
              v7.6 Live
            </span>
          </div>
          <h1 className="mt-1 text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">
            {fr ? titleFr : titleEn}
          </h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            {fr
              ? "Traitement et extraction réelle de documents sans données simulées."
              : "Genuine document processing and data extraction with zero simulated data."}
          </p>
        </div>

        <button
          onClick={() => void load()}
          disabled={busy}
          className="self-start sm:self-auto flex items-center gap-2 px-3 py-2 text-xs font-semibold rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 hover:bg-slate-50 transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${busy ? "animate-spin" : ""}`} />
          <span>{fr ? "Actualiser" : "Refresh"}</span>
        </button>
      </header>

      {/* INACTIVE MODULE CALLOUT WITH 1-CLICK ACTIVATION */}
      {isInactive && (
        <div className="rounded-2xl border border-amber-300/80 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-700/60 p-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-amber-900 dark:text-amber-200 font-bold">
              <Lock className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0" />
              <span>{fr ? "Module non activé" : "Module Not Active"}</span>
            </div>
            <p className="text-sm text-amber-800 dark:text-amber-300">
              {fr
                ? `Le module ${titleFr} est inclus dans votre espace mais n'est pas encore activé. Activez-le en 1 clic pour commencer.`
                : `The ${titleEn} module is available in your workspace but not active yet. Activate it in 1 click to get started.`}
            </p>
          </div>
          <button
            onClick={() => void activateModule()}
            disabled={activating}
            className="shrink-0 flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-cyan-500 text-white font-bold text-xs shadow-md hover:shadow-lg transition"
          >
            {activating ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Sparkles className="w-4 h-4" />
            )}
            <span>{fr ? "Activer le module maintenant" : "Activate Module Now"}</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {kind === "legal" && (
        <div className="flex items-start gap-3 rounded-2xl border border-amber-300/60 bg-amber-50/70 px-4 py-3 text-xs sm:text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-100 dark:border-amber-900/40">
          <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold">{fr ? "Clause de non-responsabilité légale : " : "Legal Disclaimer: "}</span>
            {fr
              ? "Avenqo Legal AI fournit une assistance documentaire et d'analyse contractuelle. Ce n’est pas un avis juridique et ne remplace pas un professionnel certifié."
              : "Avenqo Legal AI provides document review and clause extraction assistance. It is not licensed legal representation and cannot substitute for a qualified lawyer."}
          </div>
        </div>
      )}

      {error && (
        <div role="alert" className="flex items-center gap-2.5 p-4 rounded-xl border border-rose-200 bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 text-sm">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* UPLOAD DROPZONE */}
      <div className={`relative rounded-2xl border-2 border-dashed transition p-8 text-center ${
        isInactive
          ? "border-slate-200 dark:border-slate-800 opacity-60 pointer-events-none"
          : "border-slate-300 dark:border-slate-700 hover:border-[#0076FF] dark:hover:border-[#00D4FF] bg-slate-50/50 dark:bg-[#0B132B]/50"
      }`}>
        <input
          ref={fileInputRef}
          type="file"
          id="document-upload-input"
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
          disabled={busy || isInactive}
          onChange={(event) => void upload(event.target.files?.[0])}
        />
        <div className="flex flex-col items-center justify-center gap-3">
          <div className="p-3.5 rounded-2xl bg-blue-50 dark:bg-blue-950/60 text-[#0076FF] dark:text-[#00D4FF]">
            {busy ? <RefreshCw className="w-8 h-8 animate-spin" /> : <Upload className="w-8 h-8" />}
          </div>
          <div>
            <p className="font-bold text-slate-800 dark:text-slate-100 text-sm sm:text-base">
              {busy
                ? fr
                  ? "Analyse et extraction en cours..."
                  : "Extracting and analyzing document..."
                : fr
                ? "Cliquez ou glissez un fichier à analyser"
                : "Click or drag a file to analyze"}
            </p>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              {fr
                ? "Formats pris en charge : PDF, DOCX, TXT, CSV, XLSX (Extraction automatique OCR & IA)"
                : "Supported formats: PDF, DOCX, TXT, CSV, XLSX (Automatic OCR & AI extraction)"}
            </p>
          </div>
        </div>
      </div>

      {/* DOCUMENT LIST */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <FileText className="w-4 h-4 text-[#0076FF]" />
            <span>{fr ? "Documents traités" : "Processed Documents"}</span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-mono">
              {rows.length}
            </span>
          </h2>
        </div>

        {rows.length === 0 && !busy && !isInactive && (
          <div className="rounded-2xl border border-slate-200 dark:border-slate-800 p-12 text-center text-slate-500 dark:text-slate-400 bg-white dark:bg-[#0B132B]">
            <FileCheck className="w-10 h-10 mx-auto text-slate-400 dark:text-slate-600 mb-3" />
            <p className="text-sm font-semibold">{fr ? "Aucun document traité pour le moment." : "No documents processed yet."}</p>
            <p className="text-xs mt-1 text-slate-400">{fr ? "Téléversez une facture ou un contrat ci-dessus pour lancer l'analyse." : "Upload an invoice or contract above to begin analysis."}</p>
          </div>
        )}

        <ul className="space-y-4">
          {rows.map((row) => (
            <li
              key={row.id}
              className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-[#0B132B] shadow-xs space-y-4"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-slate-100 dark:border-slate-800">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 rounded-xl bg-blue-50 dark:bg-blue-950 text-[#0076FF] dark:text-[#00D4FF]">
                    <FileText className="w-5 h-5" />
                  </div>
                  <div>
                    <p className="font-bold text-slate-900 dark:text-white text-sm">{row.filename}</p>
                    <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                      <span className="px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 font-medium">
                        {row.classification || (fr ? "Général" : "General")}
                      </span>
                      {row.created_at && (
                        <span>
                          {new Date(row.created_at).toLocaleDateString(fr ? "fr-CA" : "en-US", {
                            day: "numeric",
                            month: "short",
                            year: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                <button
                  onClick={() => void deleteDoc(row.id)}
                  disabled={deletingId === row.id}
                  className="self-end sm:self-auto p-2 text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/40 rounded-xl transition"
                  title={fr ? "Supprimer le document" : "Delete document"}
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>

              {/* STRUCTURED ANALYSIS IF PRESENT */}
              {row.analysis && typeof row.analysis === "object" && Object.keys(row.analysis).length > 0 && (
                <div className="p-3.5 rounded-xl bg-blue-50/50 dark:bg-blue-950/20 border border-blue-100 dark:border-blue-900/40">
                  <div className="flex items-center gap-2 text-xs font-bold text-blue-700 dark:text-blue-300 mb-2">
                    <Sparkles className="w-3.5 h-3.5 text-[#0076FF]" />
                    <span>{fr ? "Données extraites par l'IA" : "AI Extracted Fields"}</span>
                  </div>
                  <pre className="text-xs text-slate-700 dark:text-slate-300 whitespace-pre-wrap font-mono overflow-auto max-h-40">
                    {JSON.stringify(row.analysis, null, 2)}
                  </pre>
                </div>
              )}

              {/* EXTRACTED TEXT */}
              <div>
                <p className="text-xs font-bold text-slate-600 dark:text-slate-400 uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
                  <Eye className="w-3.5 h-3.5" />
                  <span>{fr ? "Texte extrait" : "Extracted Content"}</span>
                </p>
                <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded-xl bg-slate-50 dark:bg-slate-900/80 p-3.5 text-xs text-slate-700 dark:text-slate-300 font-mono border border-slate-200 dark:border-slate-800">
                  {row.extracted_text || (fr ? "Aucun texte extractible trouvé dans ce document." : "No extractable text found in this document.")}
                </pre>
              </div>

              {row.disclaimer && (
                <p className="text-xs text-slate-400 italic border-t border-slate-100 dark:border-slate-800/60 pt-2">
                  {row.disclaimer}
                </p>
              )}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
