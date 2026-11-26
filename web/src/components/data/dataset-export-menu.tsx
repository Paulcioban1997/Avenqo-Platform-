"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  Download,
  FileSpreadsheet,
  FileJson,
  FileText,
  FileType2,
  Database,
  Archive,
  Lock,
  CheckCircle2,
  AlertCircle,
  Loader2,
  X,
  ChevronDown,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { getAuthHeaders } from "@/lib/api-headers";

export type ExportScopeCode =
  | "cleaned"
  | "normalized"
  | "filtered_preview"
  | "all_authorized"
  | "quality_report"
  | "original";

export type ExportFormatCode =
  | "csv"
  | "xlsx"
  | "json"
  | "parquet"
  | "pdf"
  | "docx"
  | "txt"
  | "original";

interface ScopeOption {
  code: ExportScopeCode;
  label_fr: string;
  label_en: string;
  available: boolean;
  permitted: boolean;
  description_fr: string;
}

interface FormatOption {
  code: ExportFormatCode;
  label_fr: string;
  label_en: string;
  extension: string;
  kind: string;
  available: boolean;
  permitted: boolean;
  supports_scopes: ExportScopeCode[];
  max_tabular_rows?: number;
}

interface ExportOptionsResponse {
  dataset_id: string;
  dataset_name: string;
  rows_count: number;
  columns_count: number;
  printable: boolean;
  original_available: boolean;
  limits?: {
    max_export_rows: number;
    max_pdf_rows: number;
    max_docx_rows: number;
    max_preview_rows: number;
  };
  scopes: ScopeOption[];
  formats: FormatOption[];
}

export interface DatasetExportMenuProps {
  datasetId: string;
  datasetName: string;
  isFr?: boolean;
  compact?: boolean;
  activeSearchQuery?: string;
  previewLimit?: number;
  onExportError?: (msg: string) => void;
}

const FALLBACK_SCOPES: ScopeOption[] = [
  {
    code: "cleaned",
    label_fr: "Données nettoyées",
    label_en: "Cleaned data",
    available: true,
    permitted: true,
    description_fr: "Lignes nettoyées, typées et dédupliquées prêtes pour l'analyse.",
  },
  {
    code: "normalized",
    label_fr: "Données normalisées",
    label_en: "Normalized data",
    available: true,
    permitted: true,
    description_fr: "Colonnes métier canoniques sans clés techniques internes.",
  },
  {
    code: "filtered_preview",
    label_fr: "Aperçu filtré",
    label_en: "Filtered preview",
    available: true,
    permitted: true,
    description_fr: "Sous-ensemble filtré et paginé de l'aperçu courant.",
  },
  {
    code: "all_authorized",
    label_fr: "Toutes les lignes autorisées",
    label_en: "All authorized rows",
    available: true,
    permitted: true,
    description_fr: "Intégralité des lignes accessibles selon vos permissions.",
  },
  {
    code: "quality_report",
    label_fr: "Rapport de qualité & nettoyage",
    label_en: "Quality & cleaning report",
    available: true,
    permitted: true,
    description_fr: "Synthèse d'audit qualité, conversions de types et anomalies corrigées.",
  },
  {
    code: "original",
    label_fr: "Données originales (brutes)",
    label_en: "Original raw data",
    available: true,
    permitted: true,
    description_fr: "Données brutes telles qu'importées avant nettoyage.",
  },
];

const FALLBACK_FORMATS: FormatOption[] = [
  {
    code: "csv",
    label_fr: "CSV (UTF-8)",
    label_en: "CSV (UTF-8)",
    extension: ".csv",
    kind: "tabular",
    available: true,
    permitted: true,
    supports_scopes: ["cleaned", "normalized", "filtered_preview", "all_authorized", "quality_report", "original"],
  },
  {
    code: "xlsx",
    label_fr: "Excel (.xlsx)",
    label_en: "Excel (.xlsx)",
    extension: ".xlsx",
    kind: "tabular",
    available: true,
    permitted: true,
    supports_scopes: ["cleaned", "normalized", "filtered_preview", "all_authorized", "quality_report", "original"],
  },
  {
    code: "json",
    label_fr: "JSON structuré",
    label_en: "Structured JSON",
    extension: ".json",
    kind: "structured",
    available: true,
    permitted: true,
    supports_scopes: ["cleaned", "normalized", "filtered_preview", "all_authorized", "quality_report", "original"],
  },
  {
    code: "parquet",
    label_fr: "Apache Parquet (.parquet)",
    label_en: "Apache Parquet (.parquet)",
    extension: ".parquet",
    kind: "columnar",
    available: true,
    permitted: true,
    supports_scopes: ["cleaned", "normalized", "filtered_preview", "all_authorized", "quality_report", "original"],
  },
  {
    code: "pdf",
    label_fr: "PDF tabulaire",
    label_en: "Tabular PDF",
    extension: ".pdf",
    kind: "document",
    available: true,
    permitted: true,
    supports_scopes: ["cleaned", "normalized", "filtered_preview", "all_authorized", "quality_report", "original"],
    max_tabular_rows: 1500,
  },
  {
    code: "docx",
    label_fr: "Word (.docx)",
    label_en: "Word (.docx)",
    extension: ".docx",
    kind: "document",
    available: true,
    permitted: true,
    supports_scopes: ["cleaned", "normalized", "filtered_preview", "all_authorized", "quality_report", "original"],
    max_tabular_rows: 1500,
  },
  {
    code: "txt",
    label_fr: "Texte aligné (.txt)",
    label_en: "Aligned text (.txt)",
    extension: ".txt",
    kind: "text",
    available: true,
    permitted: true,
    supports_scopes: ["cleaned", "normalized", "filtered_preview", "all_authorized", "quality_report", "original"],
  },
  {
    code: "original",
    label_fr: "Fichier original importé",
    label_en: "Original uploaded file",
    extension: "",
    kind: "raw_file",
    available: true,
    permitted: true,
    supports_scopes: ["original"],
  },
];

function formatIcon(code: ExportFormatCode) {
  switch (code) {
    case "csv":
    case "xlsx":
      return <FileSpreadsheet size={15} />;
    case "json":
      return <FileJson size={15} />;
    case "parquet":
      return <Database size={15} />;
    case "pdf":
      return <FileType2 size={15} />;
    case "docx":
    case "txt":
      return <FileText size={15} />;
    case "original":
      return <Archive size={15} />;
  }
}

function parseFilenameFromHeader(disposition: string | null, fallback: string): string {
  if (!disposition) return fallback;
  const match = /filename="?([^";]+)"?/i.exec(disposition);
  return match?.[1]?.trim() || fallback;
}

export function DatasetExportMenu({
  datasetId,
  datasetName,
  isFr = true,
  compact = false,
  activeSearchQuery = "",
  previewLimit = 0,
  onExportError,
}: DatasetExportMenuProps) {
  const [open, setOpen] = useState(false);
  const [loadingOptions, setLoadingOptions] = useState(false);
  const [options, setOptions] = useState<ExportOptionsResponse | null>(null);
  const [selectedScope, setSelectedScope] = useState<ExportScopeCode>("cleaned");
  const [selectedFormat, setSelectedFormat] = useState<ExportFormatCode>("csv");
  const [includeEnvelope, setIncludeEnvelope] = useState(true);
  const [exportOffset, setExportOffset] = useState(0);
  const [isDownloading, setIsDownloading] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [lastExportMeta, setLastExportMeta] = useState<{
    filename: string;
    rows: string;
    totalRows: number;
    offset: number;
    nextOffset: number | null;
    paginated: boolean;
  } | null>(null);

  const loadOptions = useCallback(async () => {
    setLoadingOptions(true);
    setLocalError(null);
    try {
      const resp = await fetch(`/api/v1/datasets/${datasetId}/export-options`, {
        headers: getAuthHeaders(),
      });
      if (resp.ok) {
        const data: ExportOptionsResponse = await resp.json();
        setOptions(data);
      }
    } catch {
      // Graceful fallback to default capabilities
    } finally {
      setLoadingOptions(false);
    }
  }, [datasetId]);

  useEffect(() => {
    if (open) {
      void loadOptions();
    }
  }, [open, loadOptions]);

  const scopes = options?.scopes ?? FALLBACK_SCOPES;
  const formats = options?.formats ?? FALLBACK_FORMATS;
  const emptyFilteredPreview = selectedScope === "filtered_preview" && previewLimit === 0;

  const handleSelectScope = (code: ExportScopeCode) => {
    setSelectedScope(code);
    setExportOffset(0);
    setLastExportMeta(null);
    if (code !== "original" && selectedFormat === "original") {
      setSelectedFormat("csv");
    }
  };

  const handleSelectFormat = (code: ExportFormatCode) => {
    setSelectedFormat(code);
    setExportOffset(0);
    setLastExportMeta(null);
    if (code === "original") {
      setSelectedScope("original");
    }
  };

  const resolveFormatDisplayLabel = (fmt: FormatOption): string => {
    if (fmt.code === "pdf") {
      if (selectedScope === "quality_report") {
        return isFr ? "Rapport PDF de nettoyage" : "Cleaning Report PDF";
      }
      return isFr ? "PDF tabulaire (données)" : "Tabular Data PDF";
    }
    if (fmt.code === "docx") {
      if (selectedScope === "quality_report") {
        return isFr ? "Rapport Word (.docx)" : "Cleaning Report (.docx)";
      }
      return isFr ? "Word tabulaire (.docx)" : "Tabular Word (.docx)";
    }
    return isFr ? fmt.label_fr : fmt.label_en;
  };

  const executeDownloadWithOffset = async (requestedOffset: number) => {
    if (emptyFilteredPreview) return;
    setIsDownloading(true);
    setLocalError(null);
    try {
      const params = new URLSearchParams();
      params.set("scope", selectedFormat === "original" ? "original" : selectedScope);
      if (requestedOffset > 0) {
        params.set("offset", String(requestedOffset));
      }
      if (selectedFormat === "json") {
        params.set("envelope", includeEnvelope ? "true" : "false");
      }
      if (selectedScope === "filtered_preview") {
        if (activeSearchQuery.trim()) {
          params.set("search", activeSearchQuery.trim());
        }
        params.set("limit", String(previewLimit));
      }

      const resp = await fetch(
        `/api/v1/datasets/${datasetId}/export/${selectedFormat}?${params.toString()}`,
        { headers: getAuthHeaders() }
      );

      if (!resp.ok) {
        const errBody = await resp.json().catch(() => ({ detail: `Erreur ${resp.status}` }));
        const msg =
          typeof errBody.detail === "string"
            ? errBody.detail
            : isFr
              ? `Échec de l'export (${resp.status})`
              : `Export failed (${resp.status})`;
        throw new Error(msg);
      }

      const blob = await resp.blob();
      const safeBase = datasetName.replace(/\.[^.]+$/, "") || "dataset";
      const ext = selectedFormat === "original" ? "" : `.${selectedFormat}`;
      const filename = parseFilenameFromHeader(
        resp.headers.get("Content-Disposition"),
        `${safeBase}-${selectedScope}${ext}`
      );
      const exportedRowsStr = resp.headers.get("X-Export-Row-Count") ?? "0";
      const totalRowsStr = resp.headers.get("X-Export-Total-Rows") ?? exportedRowsStr;
      const exportedCount = Number(exportedRowsStr) || 0;
      const totalCount = Number(totalRowsStr) || exportedCount;
      const isPaginated = resp.headers.get("X-Export-Paginated") === "true";
      const nextOffset =
        isPaginated && requestedOffset + exportedCount < totalCount
          ? requestedOffset + exportedCount
          : null;

      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);

      setExportOffset(requestedOffset);
      setLastExportMeta({
        filename,
        rows: exportedRowsStr,
        totalRows: totalCount,
        offset: requestedOffset,
        nextOffset,
        paginated: isPaginated,
      });
    } catch (e) {
      const message = e instanceof Error ? e.message : isFr ? "Erreur d'export." : "Export error.";
      setLocalError(message);
      onExportError?.(message);
    } finally {
      setIsDownloading(false);
    }
  };

  const handleDownload = async () => {
    await executeDownloadWithOffset(exportOffset);
  };

  return (
    <>
      {compact ? (
        <button
          type="button"
          title={isFr ? "Télécharger les données (multi-formats)" : "Download data (multi-format)"}
          onClick={(e) => {
            e.stopPropagation();
            setOpen(true);
          }}
        >
          <Download size={15} />
        </button>
      ) : (
        <button
          type="button"
          className="data-hub-action-btn inline-flex items-center gap-1.5"
          onClick={() => setOpen(true)}
        >
          <Download size={15} />
          <span>{isFr ? "Télécharger les données" : "Download data"}</span>
          <ChevronDown size={14} className="opacity-70" />
        </button>
      )}

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/65 backdrop-blur-xs p-4"
          onClick={() => setOpen(false)}
        >
          <div
            className="w-full max-w-2xl rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200 dark:border-white/[0.1] shadow-2xl overflow-hidden text-left"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-start justify-between gap-4 px-6 py-4 border-b border-slate-200/80 dark:border-white/[0.08] bg-slate-50/70 dark:bg-[#111D3D]/60">
              <div>
                <div className="flex items-center gap-2">
                  <span className="p-1.5 rounded-lg bg-blue-500/10 text-[#0076FF] dark:text-[#00D4FF]">
                    <Download size={17} />
                  </span>
                  <h3 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB]">
                    {isFr ? "Télécharger les données" : "Download Dataset"}
                  </h3>
                </div>
                <p className="text-xs text-slate-500 dark:text-[#94A3B8] mt-1">
                  <span className="font-semibold text-slate-700 dark:text-slate-200">{datasetName}</span>
                  {options?.rows_count != null && (
                    <span>
                      {" · "}
                      {options.rows_count.toLocaleString()} {isFr ? "lignes" : "rows"} · {options.columns_count}{" "}
                      {isFr ? "colonnes" : "columns"}
                    </span>
                  )}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-200/50 dark:hover:bg-white/[0.06] transition-colors cursor-pointer"
              >
                <X size={18} />
              </button>
            </div>

            {/* Body */}
            <div className="p-6 space-y-5 max-h-[75vh] overflow-y-auto">
              {loadingOptions && (
                <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                  <Loader2 size={14} className="animate-spin text-[#0076FF]" />
                  <span>
                    {isFr
                      ? "Vérification des formats disponibles et permissions..."
                      : "Checking available formats and permissions..."}
                  </span>
                </div>
              )}

              {/* Step 1: Portée / Source */}
              <div className="space-y-2.5">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-[#94A3B8]">
                    {isFr ? "1. Portée / Source des données" : "1. Data Scope / Source"}
                  </label>
                  <span className="inline-flex items-center gap-1 text-[11px] text-emerald-600 dark:text-emerald-400 font-medium">
                    <ShieldCheck size={13} />
                    {isFr ? "Contrôle RBAC actif" : "RBAC enforced"}
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  {scopes.map((sc) => {
                    const disabled = !sc.available || !sc.permitted || (sc.code === "filtered_preview" && previewLimit === 0);
                    const active = selectedScope === sc.code;
                    const isReport = sc.code === "quality_report";
                    return (
                      <button
                        key={sc.code}
                        type="button"
                        disabled={disabled}
                        onClick={() => handleSelectScope(sc.code)}
                        className={`flex flex-col items-start p-3 rounded-xl border text-left transition-all ${
                          disabled
                            ? "opacity-50 cursor-not-allowed border-slate-200 dark:border-white/[0.05] bg-slate-50 dark:bg-white/[0.01]"
                            : active
                              ? "cursor-pointer border-[#0076FF] bg-blue-50/70 dark:bg-[#0076FF]/15 ring-1 ring-[#0076FF]"
                              : "cursor-pointer border-slate-200 dark:border-white/[0.08] hover:border-slate-300 dark:hover:border-white/[0.18] bg-white dark:bg-[#060B13]/50"
                        }`}
                      >
                        <div className="flex items-center justify-between w-full gap-2">
                          <span className="text-xs font-bold text-slate-900 dark:text-[#F4F7FB] flex items-center gap-1.5">
                            {isReport && <Sparkles size={13} className="text-amber-500" />}
                            {isFr ? sc.label_fr : sc.label_en}
                          </span>
                          {!sc.permitted ? (
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-500/15 text-amber-600 dark:text-amber-400">
                              <Lock size={10} /> {isFr ? "Restreint" : "Restricted"}
                            </span>
                          ) : !sc.available ? (
                            <span className="text-[10px] text-slate-400">
                              {isFr ? "Indisponible" : "Unavailable"}
                            </span>
                          ) : null}
                        </div>
                        <span className="text-[11px] text-slate-500 dark:text-[#94A3B8] mt-1 leading-snug">
                          {sc.description_fr}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Step 2: Format */}
              <div className="space-y-2.5">
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-[#94A3B8]">
                  {isFr ? "2. Format de fichier" : "2. File Format"}
                </label>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {formats.map((fmt) => {
                    const scopeCompatible =
                      fmt.code === "original"
                        ? true
                        : fmt.supports_scopes.includes(selectedScope);
                    const disabled = !fmt.available || !fmt.permitted || !scopeCompatible;
                    const active = selectedFormat === fmt.code;

                    return (
                      <button
                        key={fmt.code}
                        type="button"
                        disabled={disabled}
                        onClick={() => handleSelectFormat(fmt.code)}
                        className={`flex items-center gap-2 px-3 py-2.5 rounded-xl border text-xs font-semibold transition-all ${
                          disabled
                            ? "opacity-45 cursor-not-allowed border-slate-200 dark:border-white/[0.05] text-slate-400"
                            : active
                              ? "cursor-pointer border-[#0076FF] bg-[#0076FF] text-white shadow-xs"
                              : "cursor-pointer border-slate-200 dark:border-white/[0.08] text-slate-700 dark:text-[#F4F7FB] hover:bg-slate-50 dark:hover:bg-white/[0.04]"
                        }`}
                      >
                        {formatIcon(fmt.code)}
                        <span className="truncate">{resolveFormatDisplayLabel(fmt)}</span>
                        {!fmt.permitted && <Lock size={11} className="ml-auto shrink-0" />}
                      </button>
                    );
                  })}
                </div>

                {/* Explicit distinction banner for PDF / DOCX / JSON */}
                {(selectedFormat === "pdf" || selectedFormat === "docx") && (
                  <div className="rounded-xl px-3.5 py-2.5 text-xs border border-blue-200/80 dark:border-blue-500/20 bg-blue-50/60 dark:bg-blue-950/30 text-slate-700 dark:text-slate-200">
                    {selectedScope === "quality_report" ? (
                      <span>
                        <strong>{isFr ? "Mode Rapport d'Audit :" : "Audit Report Mode:"}</strong>{" "}
                        {isFr
                          ? "Génère le document exécutif de synthèse du nettoyage (scores qualité, anomalies, conversions) avec un échantillon de lignes."
                          : "Generates the executive cleaning summary document (quality scores, anomalies, conversions) with a row sample."}
                      </span>
                    ) : (
                      <span>
                        <strong>{isFr ? "Mode Données Tabulaires :" : "Tabular Data Mode:"}</strong>{" "}
                        {isFr
                          ? `Exporte la table paginée complète avec en-têtes répétés (borné à ${options?.limits?.max_pdf_rows ?? 1500} lignes par document ; utilisez CSV, Parquet ou JSON pour les très grands volumes).`
                          : `Exports the full paginated data table with repeating headers (bounded at ${options?.limits?.max_pdf_rows ?? 1500} rows per document; use CSV, Parquet, or JSON for massive volumes).`}
                      </span>
                    )}
                  </div>
                )}

                {selectedFormat === "json" && (
                  <label className="flex items-center gap-2 pt-1 text-xs text-slate-600 dark:text-[#94A3B8] cursor-pointer">
                    <input
                      type="checkbox"
                      checked={includeEnvelope}
                      onChange={(e) => setIncludeEnvelope(e.target.checked)}
                      className="rounded border-slate-300 text-[#0076FF] focus:ring-[#0076FF]"
                    />
                    <span>
                      {isFr
                        ? "Inclure l'enveloppe de métadonnées et de provenance (version, portée, colonnes)"
                        : "Include provenance & metadata envelope (version, scope, columns)"}
                    </span>
                  </label>
                )}
              </div>

              {/* Error or Success feedback */}
              {localError && (
                <div className="flex items-center gap-2 rounded-xl px-3.5 py-2.5 text-xs bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300">
                  <AlertCircle size={15} className="shrink-0" />
                  <span>{localError}</span>
                </div>
              )}

              {lastExportMeta && (
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl px-3.5 py-2.5 text-xs bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 size={15} className="shrink-0" />
                    <span>
                      {isFr ? "Téléchargement prêt :" : "Download ready:"}{" "}
                      <strong className="font-mono">{lastExportMeta.filename}</strong> ({lastExportMeta.rows}{" "}
                      {isFr ? "lignes" : "rows"}
                      {lastExportMeta.totalRows > 0
                        ? ` / ${lastExportMeta.totalRows}`
                        : ""})
                      {lastExportMeta.paginated
                        ? isFr
                          ? ` · Lot paginé (offset ${lastExportMeta.offset})`
                          : ` · Paginated slice (offset ${lastExportMeta.offset})`
                        : ""}
                    </span>
                  </div>
                  {lastExportMeta.nextOffset != null && (
                    <button
                      type="button"
                      disabled={isDownloading}
                      onClick={() => void executeDownloadWithOffset(lastExportMeta.nextOffset!)}
                      className="px-2.5 py-1 rounded-lg bg-emerald-700 hover:bg-emerald-800 text-white font-bold text-[11px] cursor-pointer"
                    >
                      {isFr
                        ? `Télécharger le lot suivant (offset ${lastExportMeta.nextOffset})`
                        : `Download next batch (offset ${lastExportMeta.nextOffset})`}
                    </button>
                  )}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-2.5 px-6 py-4 border-t border-slate-200/80 dark:border-white/[0.08] bg-slate-50/50 dark:bg-[#111D3D]/40">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="px-4 py-2 rounded-xl border border-slate-200 dark:border-white/[0.1] text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-white/[0.05] cursor-pointer"
              >
                {isFr ? "Fermer" : "Close"}
              </button>
              <button
                type="button"
                disabled={isDownloading || emptyFilteredPreview}
                onClick={handleDownload}
                className="inline-flex items-center gap-2 px-5 py-2 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] disabled:opacity-60 text-white text-xs font-bold shadow-sm transition-colors cursor-pointer"
              >
                {isDownloading ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    <span>{isFr ? "Préparation..." : "Preparing..."}</span>
                  </>
                ) : (
                  <>
                    <Download size={14} />
                    <span>{isFr ? "Télécharger maintenant" : "Download now"}</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
