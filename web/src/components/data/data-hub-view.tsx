"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  Upload,
  Database,
  FileSpreadsheet,
  FileText,
  FileJson,
  FileType2,
  Plus,
  Trash2,
  Eye,
  AlertCircle,
  CheckCircle2,
  Loader2,
  ChevronRight,
  X,
  Search,
  RefreshCw,
  ArrowLeft,
  Save,
  Printer,
} from "lucide-react";
import { getAuthHeaders } from "@/lib/api-headers";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
import { DatasetExportMenu } from "@/components/data/dataset-export-menu";
import { useSession } from "@/lib/session-context";

// ---- Types ----
interface Dataset {
  id: string;
  name: string;
  status: string;
  row_count?: number;
  rows_count?: number;
  column_count?: number;
  columns_count?: number;
  file_type?: string;
  type?: string;
  created_at?: string;
  uploaded_at?: string;
  error_message?: string | null;
  source_missing?: boolean;
  source_missing_message?: string | null;
}

interface DatasetRow {
  [key: string]: unknown;
}

type StatusCategory = "ready" | "processing" | "failed";

function getStatusCategory(status?: string): StatusCategory {
  if (!status) return "processing";
  const s = status.toLowerCase();
  if (s === "ready" || s === "completed" || s === "validated") return "ready";
  if (
    s === "processing" ||
    s === "parsing" ||
    s === "cleaning" ||
    s === "uploaded" ||
    s === "pending"
  )
    return "processing";
  return "failed";
}

function getStatusLabel(status?: string): string {
  const cat = getStatusCategory(status);
  if (cat === "ready") return "Prêt";
  if (cat === "processing") return "Traitement…";
  return "Échec";
}

function formatDatasetDate(d?: Dataset): string {
  if (!d) return "—";
  const raw = d.uploaded_at || d.created_at;
  if (!raw) return "—";
  try {
    const dt = new Date(raw);
    if (isNaN(dt.getTime())) return "—";
    return dt.toLocaleDateString("fr-CA", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
  } catch {
    return "—";
  }
}

const STATUS_COLOR: Record<StatusCategory, string> = {
  ready: "var(--color-success, #22c55e)",
  processing: "var(--color-warning, #f59e0b)",
  failed: "var(--color-error, #ef4444)",
};

const STATUS_ICON: Record<StatusCategory, React.ReactNode> = {
  ready: <CheckCircle2 size={14} />,
  processing: <Loader2 size={14} className="spin" />,
  failed: <AlertCircle size={14} />,
};

const FILE_ICON: Record<string, React.ReactNode> = {
  csv: <FileSpreadsheet size={20} />,
  tsv: <FileSpreadsheet size={20} />,
  xls: <FileSpreadsheet size={20} />,
  xlsx: <FileSpreadsheet size={20} />,
  pdf: <FileType2 size={20} />,
  json: <FileJson size={20} />,
  txt: <FileText size={20} />,
  parquet: <Database size={20} />,
};

const ACCEPTED_TYPES =
  ".csv,.tsv,.xls,.xlsx,.pdf,.json,.txt,.parquet";

// ---- Main Component ----
export function DataHubView() {
  const { locale } = useLocale();
  const t = getAppTranslations(locale);
  const isFr = locale.toLowerCase().startsWith("fr");
  const session = useSession();
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedDataset, setSelectedDataset] = useState<Dataset | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});
  const [searchQuery, setSearchQuery] = useState("");
  const [detailFilterQuery, setDetailFilterQuery] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Dataset detail state
  const [rows, setRows] = useState<DatasetRow[]>([]);
  const [columns, setColumns] = useState<string[]>([]);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [activationError, setActivationError] = useState<string | null>(null);
  const detailPending = useRef(false);
  const [editingCell, setEditingCell] = useState<{ rowIdx: number; col: string } | null>(null);
  const [editValue, setEditValue] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null); // dataset id to delete

  // Pagination
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 50;

  const fetchDatasets = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const resp = await fetch("/api/v1/datasets/", {
        headers: getAuthHeaders(),
      });
      if (!resp.ok) throw new Error(`Erreur ${resp.status}`);
      const data = await resp.json();
      setDatasets(Array.isArray(data) ? data : data.items ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur de chargement des datasets.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDatasets();
  }, [fetchDatasets]);

  // Poll processing datasets
  useEffect(() => {
    const processing = datasets.filter(
      (d) => getStatusCategory(d.status) === "processing"
    );
    if (processing.length === 0) return;
    const id = setInterval(fetchDatasets, 4000);
    return () => clearInterval(id);
  }, [datasets, fetchDatasets]);

  const fetchDatasetDetail = useCallback(async (dataset: Dataset) => {
    if (detailPending.current) return;
    detailPending.current = true;
    setSelectedDataset(dataset);
    setIsLoadingDetail(true);
    setDetailError(null);
    setActivationError(null);
    setDetailFilterQuery("");
    setRows([]);
    setColumns([]);
    setPage(1);
    try {
      try {
        await session.selectSource("dataset", dataset.id);
      } catch {
        setActivationError(isFr
          ? "Impossible d’activer ce fichier comme source. La comptabilité peut encore utiliser la source précédente."
          : "Could not activate this file as the source. Accounting may still use the previous source.");
      }
      const resp = await fetch(`/api/v1/datasets/${dataset.id}/rows?limit=${PAGE_SIZE}&offset=0`, {
        headers: getAuthHeaders(),
      });
      if (!resp.ok) throw new Error(`Erreur ${resp.status}`);
      const data = await resp.json();
      const rowData: DatasetRow[] = Array.isArray(data) ? data : data.rows ?? [];
      setRows(rowData);
      if (rowData.length > 0) setColumns(Object.keys(rowData[0]));
    } catch (e) {
      setDetailError(e instanceof Error ? e.message : "Erreur de chargement des données.");
    } finally {
      detailPending.current = false;
      setIsLoadingDetail(false);
    }
  }, [session, isFr]);

  const handleUpload = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    for (const file of Array.from(files)) {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("module_code", "retail");
      const fileId = `${file.name}_${Date.now()}`;
      setUploadProgress((p) => ({ ...p, [fileId]: 0 }));
      try {
        const resp = await fetch("/api/v1/datasets/upload", {
          method: "POST",
          headers: getAuthHeaders(), // no Content-Type for multipart
          body: formData,
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({ message: "Erreur d'upload" }));
          const errMsg = typeof err.detail === "string"
            ? err.detail
            : Array.isArray(err.detail)
              ? err.detail.map((d: any) => d.msg || JSON.stringify(d)).join(", ")
              : err.message ?? `Erreur ${resp.status}`;
          throw new Error(errMsg);
        }
        setUploadProgress((p) => ({ ...p, [fileId]: 100 }));
        await fetchDatasets();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erreur d'upload.");
        setUploadProgress((p) => {
          const copy = { ...p };
          delete copy[fileId];
          return copy;
        });
      }
    }
    // clear progress after 2s
    setTimeout(() => setUploadProgress({}), 2000);
  }, [fetchDatasets]);

  const handleDeleteDataset = async (datasetId: string) => {
    try {
      const resp = await fetch(`/api/v1/datasets/${datasetId}`, {
        method: "DELETE",
        headers: getAuthHeaders(),
      });
      if (!resp.ok) throw new Error(`Erreur ${resp.status}`);
      setDatasets((ds) => ds.filter((d) => d.id !== datasetId));
      if (selectedDataset?.id === datasetId) setSelectedDataset(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur de suppression.");
    } finally {
      setDeleteConfirm(null);
    }
  };

  const handleSaveCell = async (rowIdx: number, col: string) => {
    if (!selectedDataset) return;
    const row = rows[rowIdx];
    const rowId = row["id"] ?? row["_id"] ?? rowIdx;
    const updated = { ...row, [col]: editValue };
    try {
      const resp = await fetch(`/api/v1/datasets/${selectedDataset.id}/rows/${rowId}`, {
        method: "PUT",
        headers: { ...getAuthHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify(updated),
      });
      if (!resp.ok) throw new Error(`Erreur ${resp.status}`);
      setRows((r) => r.map((row, i) => (i === rowIdx ? updated : row)));
    } catch (e) {
      setDetailError(e instanceof Error ? e.message : "Erreur de modification.");
    } finally {
      setEditingCell(null);
    }
  };

  const handleDeleteRow = async (rowIdx: number) => {
    if (!selectedDataset) return;
    const row = rows[rowIdx];
    const rowId = row["id"] ?? row["_id"] ?? rowIdx;
    try {
      const resp = await fetch(`/api/v1/datasets/${selectedDataset.id}/rows/${rowId}`, {
        method: "DELETE",
        headers: getAuthHeaders(),
      });
      if (!resp.ok) throw new Error(`Erreur ${resp.status}`);
      setRows((r) => r.filter((_, i) => i !== rowIdx));
    } catch (e) {
      setDetailError(e instanceof Error ? e.message : "Erreur de suppression de ligne.");
    }
  };

  const handlePrintDataset = (dataset: Dataset) => {
    if (columns.length === 0 || columns.length > 25) return;
    window.print();
  };

  const indexedRows = rows.map((row, originalIndex) => ({ row, originalIndex }));
  const visibleDetailRows = detailFilterQuery.trim()
    ? indexedRows.filter(({ row }) =>
        columns.some((col) =>
          String(row[col] ?? "")
            .toLowerCase()
            .includes(detailFilterQuery.trim().toLowerCase())
        )
      )
    : indexedRows;

  const filteredDatasets = datasets.filter((d) =>
    d.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Drag & Drop
  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(true); };
  const handleDragLeave = () => setIsDragging(false);
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleUpload(e.dataTransfer.files);
  };

  // --- Render: Dataset Detail ---
  if (selectedDataset) {
    const canPrint = columns.length > 0 && columns.length <= 25 && visibleDetailRows.length > 0;
    return (
      <div className="data-hub-detail print:p-0 print:bg-white print:text-black">
        <style>{`
          @media print {
            body * { visibility: hidden; }
            .data-hub-detail, .data-hub-detail * { visibility: visible; }
            .data-hub-detail { position: absolute; left: 0; top: 0; width: 100%; padding: 16px !important; background: #fff !important; color: #0f172a !important; }
            .data-hub-no-print { display: none !important; }
            .data-hub-table-wrap { overflow: visible !important; max-height: none !important; }
            .data-hub-table { width: 100% !important; border-collapse: collapse !important; font-size: 10px !important; }
            .data-hub-table th, .data-hub-table td { border: 1px solid #cbd5e1 !important; padding: 4px 6px !important; color: #0f172a !important; }
          }
        `}</style>
        <div className="data-hub-detail-header">
          <button
            className="data-hub-back-btn data-hub-no-print"
            disabled={isLoadingDetail}
            onClick={() => {
              setSelectedDataset(null);
              setDetailFilterQuery("");
            }}
          >
            <ArrowLeft size={16} /> {t.crm.calendar.previous}
          </button>
          <div className="data-hub-detail-title">
            {FILE_ICON[selectedDataset.type ?? selectedDataset.file_type ?? "csv"] ?? <Database size={20} />}
            <span>{selectedDataset.name}</span>
            <span
              className="data-hub-status-badge"
              style={{ color: STATUS_COLOR[getStatusCategory(selectedDataset.status)] }}
            >
              {STATUS_ICON[getStatusCategory(selectedDataset.status)]} {getStatusLabel(selectedDataset.status)}
            </span>
          </div>
          <div className="data-hub-detail-actions data-hub-no-print">
            <DatasetExportMenu
              datasetId={selectedDataset.id}
              datasetName={selectedDataset.name}
              isFr={isFr}
              activeSearchQuery={detailFilterQuery}
              previewLimit={visibleDetailRows.length || 50}
              onExportError={(msg) => setDetailError(msg)}
            />
            <button
              type="button"
              className="data-hub-action-btn inline-flex items-center gap-1.5 disabled:opacity-45"
              disabled={!canPrint}
              title={
                canPrint
                  ? isFr
                    ? "Imprimer la vue tabulaire formatée"
                    : "Print formatted table view"
                  : isFr
                    ? "Impression directe indisponible (aucune donnée ou trop de colonnes)"
                    : "Direct print unavailable (no rows or too many columns)"
              }
              onClick={() => handlePrintDataset(selectedDataset)}
            >
              <Printer size={15} />
              <span>{isFr ? "Imprimer" : "Print"}</span>
            </button>
            <button
              className="data-hub-action-btn danger"
              onClick={() => setDeleteConfirm(selectedDataset.id)}
            >
              <Trash2 size={15} /> {t.common.deletePermanently}
            </button>
          </div>
        </div>

        {/* Inline filter bar for preview & filtered exports */}
        {columns.length > 0 && (
          <div className="data-hub-search data-hub-no-print">
            <Search size={15} />
            <input
              placeholder={
                isFr
                  ? "Filtrer les lignes affichées (pris en compte dans l'export « Aperçu filtré »)…"
                  : "Filter displayed rows (applied to 'Filtered preview' export)…"
              }
              value={detailFilterQuery}
              onChange={(e) => setDetailFilterQuery(e.target.value)}
            />
            {detailFilterQuery && (
              <button
                type="button"
                onClick={() => setDetailFilterQuery("")}
                className="text-xs text-slate-400 hover:text-slate-600"
              >
                <X size={14} />
              </button>
            )}
          </div>
        )}

        {activationError && (
          <div role="alert" className="data-hub-error data-hub-no-print">
            <AlertCircle size={16} /> {activationError}
            <button type="button" disabled={isLoadingDetail} onClick={() => void fetchDatasetDetail(selectedDataset)}>
              {isFr ? "Réessayer" : "Retry"}
            </button>
          </div>
        )}

        {detailError && (
          <div className="data-hub-error">
            <AlertCircle size={16} /> {detailError}
          </div>
        )}

        {isLoadingDetail ? (
          <div className="data-hub-loading">
            <Loader2 size={28} className="spin" /> {t.integrations.syncing}
          </div>
        ) : columns.length > 0 ? (
          <div className="data-hub-table-wrap">
            <table className="data-hub-table">
              <thead>
                <tr>
                  {columns.map((col) => (
                    <th key={col}>{col}</th>
                  ))}
                  <th className="data-hub-no-print">{t.crm.actions.modify}</th>
                </tr>
              </thead>
              <tbody>
                {visibleDetailRows.map(({ row, originalIndex }) => (
                  <tr key={originalIndex}>
                    {columns.map((col) => (
                      <td key={col} onDoubleClick={() => {
                        setEditingCell({ rowIdx: originalIndex, col });
                        setEditValue(String(row[col] ?? ""));
                      }}>
                        {editingCell?.rowIdx === originalIndex && editingCell?.col === col ? (
                          <div className="data-hub-cell-edit">
                            <input
                              autoFocus
                              value={editValue}
                              onChange={(e) => setEditValue(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") handleSaveCell(originalIndex, col);
                                if (e.key === "Escape") setEditingCell(null);
                              }}
                            />
                            <button onClick={() => handleSaveCell(originalIndex, col)} title={t.crm.actions.save}>
                              <Save size={13} />
                            </button>
                            <button onClick={() => setEditingCell(null)} title={t.crm.actions.close}>
                              <X size={13} />
                            </button>
                          </div>
                        ) : (
                          <span>{String(row[col] ?? "")}</span>
                        )}
                      </td>
                    ))}
                    <td className="data-hub-no-print">
                      <button
                        className="data-hub-row-delete"
                        onClick={() => handleDeleteRow(originalIndex)}
                        title={t.common.deletePermanently}
                      >
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="data-hub-empty-detail">{t.common.noPreview}</div>
        )}

        {/* Delete dataset confirm */}
        {deleteConfirm && (
          <div className="data-hub-confirm-overlay" onClick={() => setDeleteConfirm(null)}>
            <div className="data-hub-confirm-modal" onClick={(e) => e.stopPropagation()}>
              <h3>{t.integrations.drawerTitle}</h3>
              <p>{t.integrations.noLogs}</p>
              <div className="data-hub-confirm-actions">
                <button onClick={() => setDeleteConfirm(null)}>{t.common.cancel}</button>
                <button className="danger" onClick={() => handleDeleteDataset(deleteConfirm)}>
                  {t.common.deletePermanently}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // --- Render: Dataset List ---
  return (
    <div className="data-hub">
      <div className="data-hub-header">
        <div>
          <h1 className="data-hub-title">{t.navigation.dataHub}</h1>
          <p className="data-hub-subtitle">
            {t.common.dataHubSubtitle}
          </p>
        </div>
        <div className="data-hub-header-actions">
          <button className="data-hub-refresh-btn" onClick={fetchDatasets} disabled={isLoading}>
            <RefreshCw size={15} className={isLoading ? "spin" : ""} />
          </button>
          <button
            className="data-hub-upload-btn"
            onClick={() => fileInputRef.current?.click()}
          >
            <Plus size={16} /> {t.integrations.uploadedRetailSource}
          </button>
        </div>
      </div>

      {error && (
        <div className="data-hub-error">
          <AlertCircle size={16} /> {error}
          <button onClick={() => setError(null)}><X size={14} /></button>
        </div>
      )}

      {/* Upload progress */}
      {Object.entries(uploadProgress).map(([fileId, pct]) => (
        <div key={fileId} className="data-hub-upload-progress">
          <Loader2 size={14} className="spin" />
          <span>{t.integrations.syncing}</span>
          <div className="data-hub-progress-bar">
            <div style={{ width: `${pct}%` }} />
          </div>
        </div>
      ))}

      {/* Drag & Drop zone */}
      <div
        className={`data-hub-dropzone${isDragging ? " dragging" : ""}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <Upload size={28} />
        <p>
          {t.common.dropFilesPrompt}{" "}
          <span className="data-hub-dropzone-link">{t.integrations.selectSource}</span>
        </p>
        <p className="data-hub-dropzone-formats">
            {Object.keys(FILE_ICON).map((format) => format.replace(".", "").toUpperCase()).join(" · ")}
        </p>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ACCEPTED_TYPES}
          style={{ display: "none" }}
          onChange={(e) => handleUpload(e.target.files)}
        />
      </div>

      {/* Search */}
      <div className="data-hub-search">
        <Search size={15} />
        <input
          placeholder={t.integrations.selectSource}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
      </div>

      {/* Dataset list */}
      {isLoading && datasets.length === 0 ? (
        <div className="data-hub-loading">
          <Loader2 size={28} className="spin" /> {t.integrations.syncing}
        </div>
      ) : filteredDatasets.length === 0 ? (
        <div className="data-hub-empty">
          <Database size={48} />
          <p>{t.integrations.noUploadedRetailSources}</p>
        </div>
      ) : (
        <div className="data-hub-list">
          {filteredDatasets.map((ds) => {
            const statusCat = getStatusCategory(ds.status);
            const statusLabel = getStatusLabel(ds.status);
            const rowCount = ds.rows_count ?? ds.row_count;
            const colCount = ds.columns_count ?? ds.column_count;
            const fileType = ds.type ?? ds.file_type ?? "csv";

            return (
              <div key={ds.id} className="data-hub-card">
                <div className="data-hub-card-icon">
                  {FILE_ICON[fileType] ?? <Database size={20} />}
                </div>
                <div className="data-hub-card-info">
                  <span className="data-hub-card-name">{ds.name}</span>
                  <span className="data-hub-card-meta">
                    {rowCount != null ? `${rowCount.toLocaleString()} lignes` : "—"}
                    {colCount != null ? ` · ${colCount} colonnes` : ""}
                    {" · "}
                    {formatDatasetDate(ds)}
                  </span>
                  {statusCat === "failed" && ds.error_message && (
                    <span className="data-hub-card-error">{ds.error_message}</span>
                  )}
                  {ds.source_missing && ds.source_missing_message && (
                    <span className="data-hub-card-error">{ds.source_missing_message}</span>
                  )}
                </div>
                <div
                  className="data-hub-card-status"
                  style={{ color: STATUS_COLOR[statusCat] }}
                >
                  {STATUS_ICON[statusCat]}{" "}
                  {statusLabel}
                </div>
                <div className="data-hub-card-actions">
                  {statusCat === "ready" && (
                    <button title={t.integrations.currentRetailSource} onClick={() => fetchDatasetDetail(ds)}>
                      <Eye size={15} />
                    </button>
                  )}
                  <DatasetExportMenu
                    datasetId={ds.id}
                    datasetName={ds.name}
                    isFr={isFr}
                    compact
                    onExportError={(msg) => setError(msg)}
                  />
                  <button
                    title={t.common.deletePermanently}
                    className="danger"
                    onClick={() => setDeleteConfirm(ds.id)}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
                {statusCat === "ready" && (
                  <button className="data-hub-card-open" onClick={() => fetchDatasetDetail(ds)}>
                    <ChevronRight size={18} />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Delete confirm */}
      {deleteConfirm && (
        <div className="data-hub-confirm-overlay" onClick={() => setDeleteConfirm(null)}>
          <div className="data-hub-confirm-modal" onClick={(e) => e.stopPropagation()}>
            <h3>{t.integrations.drawerTitle}</h3>
            <p>{t.integrations.noLogs}</p>
            <div className="data-hub-confirm-actions">
              <button onClick={() => setDeleteConfirm(null)}>{t.common.cancel}</button>
              <button className="danger" onClick={() => handleDeleteDataset(deleteConfirm)}>
                {t.common.deletePermanently}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}



