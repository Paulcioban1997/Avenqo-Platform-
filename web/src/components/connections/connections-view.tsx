"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import {
  UploadCloud,
  FileText,
  FileSpreadsheet,
  Database,
  RefreshCw,
  Trash2,
  Download,
  Eye,
  CheckCircle2,
  AlertCircle,
  Clock,
  ExternalLink,
  Plus,
  ShoppingBag,
  Store,
  Layers,
  Sparkles,
  AlertTriangle,
  X,
  Lock,
} from "lucide-react";
import { getAuthHeaders } from "@/lib/api-headers";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";

interface DatasetItem {
  id: string;
  name: string;
  type: string;
  module_code?: string;
  rows_count?: number;
  columns_count?: number;
  quality_score?: number;
  missing_values?: number;
  duplicates?: number;
  status: string;
  pipeline_status?: string;
  source_missing?: boolean;
  source_missing_message?: string | null;
  uploaded_at: string;
  columns?: Array<{ name: string; type?: string }>;
}

interface CommerceConnectionItem {
  id: string;
  provider: string;
  store_name?: string;
  store_url?: string;
  status: string;
  is_active: boolean;
  last_synced_at?: string | null;
  records_count?: number;
  sync_orders?: boolean;
  sync_products?: boolean;
  sync_customers?: boolean;
  sync_inventory?: boolean;
}

interface SyncLogItem {
  id: string;
  timestamp: string;
  provider: string;
  status: string;
  records_synced: number;
  records_updated: number;
  records_failed: number;
  message?: string;
}

export function ConnectionsView() {
  const { locale } = useLocale();
  const t = getAppTranslations(locale);

  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [alertSuccess, setAlertSuccess] = useState<string | null>(null);
  const [alertError, setAlertError] = useState<string | null>(null);

  // Datasets & Files
  const [datasets, setDatasets] = useState<DatasetItem[]>([]);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Connectors
  const [connections, setConnections] = useState<CommerceConnectionItem[]>([]);
  const [syncHistory, setSyncHistory] = useState<SyncLogItem[]>([]);

  // Preview & Delete Modals
  const [previewDataset, setPreviewDataset] = useState<DatasetItem | null>(null);
  const [deleteModalDataset, setDeleteModalDataset] = useState<DatasetItem | null>(null);

  // WooCommerce manual connection form modal
  const [isWooModalOpen, setIsWooModalOpen] = useState(false);
  const [wooStoreUrl, setWooStoreUrl] = useState("");
  const [wooKey, setWooKey] = useState("");
  const [wooSecret, setWooSecret] = useState("");

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const headers = getAuthHeaders();
      const [dsRes, connRes, syncRes] = await Promise.all([
        fetch("/api/v1/datasets", { headers }).catch(() => null),
        fetch("/api/v1/connectors/connections", { headers }).catch(() => null),
        fetch("/api/v1/connectors/sync/history?limit=10", { headers }).catch(() => null),
      ]);

      if (dsRes && dsRes.ok) {
        const dsData = await dsRes.json();
        if (Array.isArray(dsData)) {
          setDatasets(dsData);
        }
      }

      if (connRes && connRes.ok) {
        const connData = await connRes.json();
        if (Array.isArray(connData)) {
          setConnections(connData);
        }
      }

      if (syncRes && syncRes.ok) {
        const sData = await syncRes.json();
        if (Array.isArray(sData)) {
          setSyncHistory(sData);
        }
      }
    } catch {
      // keep existing state
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // File Upload Handlers
  const handleFiles = async (files: FileList | File[]) => {
    const validExtensions = [".csv", ".xls", ".xlsx", ".json", ".pdf", ".txt", ".parquet"];
    const fileList = Array.from(files);

    if (fileList.length === 0) return;

    for (const file of fileList) {
      const ext = "." + (file.name.split(".").pop() || "").toLowerCase();
      if (!validExtensions.includes(ext)) {
        setAlertError(`Format de fichier non pris en charge pour "${file.name}". Formats acceptés : CSV, XLS, XLSX, PDF, JSON, TXT et Parquet.`);
        return;
      }
      if (file.size > 50 * 1024 * 1024) {
        setAlertError(`Le fichier "${file.name}" dépasse la limite autorisée de 50 Mo.`);
        return;
      }
    }

    setUploadProgress(15);
    setAlertError(null);
    setAlertSuccess(null);

    try {
      for (let i = 0; i < fileList.length; i++) {
        const file = fileList[i];
        const formData = new FormData();
        formData.append("file", file);
        formData.append("module_code", "retail");

        setUploadProgress(Math.round(((i + 0.5) / fileList.length) * 100));

        const res = await fetch("/api/v1/datasets/upload", {
          method: "POST",
          headers: getAuthHeaders(),
          body: formData,
        });

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          const detail = typeof errData?.detail === "string"
            ? errData.detail
            : typeof errData?.error?.message === "string"
              ? errData.error.message
              : `Erreur lors de l'import de ${file.name}`;
          console.error("[Avenqo dataset upload] request failed", {
            fileName: file.name,
            status: res.status,
            statusText: res.statusText,
            detail,
          });
          throw new Error(`${detail} (HTTP ${res.status})`);
        }
      }

      setUploadProgress(100);
      setAlertSuccess(`${fileList.length} fichier(s) importé(s) et nettoyé(s) automatiquement par l'IA.`);
      setTimeout(() => setUploadProgress(null), 1500);
      setTimeout(() => setAlertSuccess(null), 5000);
      loadData();
    } catch (err: any) {
      setUploadProgress(null);
      setAlertError(err.message || "Erreur lors du traitement des fichiers.");
    }
  };

  // Sync Trigger
  const handleTriggerSync = async (connId?: string) => {
    setActionLoading(true);
    setAlertError(null);
    try {
      const url = connId
        ? `/api/v1/connectors/connections/${connId}/sync`
        : `/api/v1/connectors/sync`;
      const res = await fetch(url, {
        method: "POST",
        headers: getAuthHeaders(),
      });
      if (!res.ok) {
        throw new Error("Impossible de déclencher la synchronisation.");
      }
      setAlertSuccess("Synchronisation lancée avec succès en arrière-plan.");
      setTimeout(() => setAlertSuccess(null), 4000);
      loadData();
    } catch (err: any) {
      setAlertError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // Connect WooCommerce
  const handleConnectWooCommerce = async (e: React.FormEvent) => {
    e.preventDefault();
    setActionLoading(true);
    setAlertError(null);
    try {
      let formattedUrl = wooStoreUrl.trim();
      if (!formattedUrl.startsWith("http://") && !formattedUrl.startsWith("https://")) {
        formattedUrl = `https://${formattedUrl}`;
      }
      const res = await fetch("/api/v1/connectors/woocommerce/manual", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({
          store_url: formattedUrl,
          consumer_key: wooKey.trim(),
          consumer_secret: wooSecret.trim(),
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.detail || "Échec de connexion WooCommerce.");
      }

      setIsWooModalOpen(false);
      setWooStoreUrl("");
      setWooKey("");
      setWooSecret("");
      setAlertSuccess("Boutique WooCommerce connectée avec succès !");
      loadData();
    } catch (err: any) {
      setAlertError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // Download Dataset
  const handleDownloadDataset = async (dataset: DatasetItem, format: "original" | "csv" | "xlsx" | "json") => {
    try {
      const endpoint = format === "original"
        ? `/api/v1/datasets/${dataset.id}/export/csv`
        : `/api/v1/datasets/${dataset.id}/export/${format}`;

      const res = await fetch(endpoint, { headers: getAuthHeaders() });
      if (!res.ok) throw new Error("Erreur de téléchargement");

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${dataset.name.replace(/\.[^/.]+$/, "")}-${format}.${format === "original" ? "csv" : format}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch {
      setAlertError("Impossible de télécharger le fichier.");
    }
  };

  // Delete Dataset
  const handleConfirmDelete = async () => {
    if (!deleteModalDataset) return;
    setActionLoading(true);
    try {
      const res = await fetch(`/api/v1/datasets/${deleteModalDataset.id}`, {
        method: "DELETE",
        headers: getAuthHeaders(),
      });
      if (!res.ok) throw new Error("Erreur lors de la suppression.");

      setDatasets((prev) => prev.filter((d) => d.id !== deleteModalDataset.id));
      setDeleteModalDataset(null);
      setAlertSuccess(`Jeu de données "${deleteModalDataset.name}" supprimé avec succès.`);
      setTimeout(() => setAlertSuccess(null), 4000);
    } catch (err: any) {
      setAlertError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const failedDatasets = datasets.filter(
    (d) => d.status === "failed" || d.pipeline_status === "failed" || d.status === "invalid"
  );

  return (
    <div className="space-y-8 max-w-7xl mx-auto pb-16">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-200/80 dark:border-white/[0.08]">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-blue-50 dark:bg-[#111D3D] text-[#0076FF] dark:text-[#00D4FF]">
              <Database size={22} />
            </div>
            <div>
              <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 dark:text-[#F4F7FB]">
                {t.navigation?.connections || "Connexions"}
              </h1>
              <p className="mt-0.5 text-xs text-slate-500 dark:text-[#94A3B8]">
                Centralisez vos boutiques en ligne, imports de fichiers et flux de données prêts pour l'intelligence artificielle.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={loadData}
            disabled={loading}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-slate-200 dark:border-white/[0.08] hover:bg-slate-100 dark:hover:bg-white/[0.04] text-xs font-semibold text-slate-700 dark:text-[#F4F7FB] transition-colors cursor-pointer"
          >
            <RefreshCw size={14} className={loading ? "animate-spin text-[#0076FF]" : ""} />
            <span>Actualiser</span>
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer"
          >
            <Plus size={14} />
            <span>Ajouter des fichiers</span>
          </button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".csv,.xls,.xlsx,.json,.pdf,.doc,.docx,.parquet"
            className="hidden"
            onChange={(e) => {
              if (e.target.files) handleFiles(e.target.files);
            }}
          />
        </div>
      </div>

      {/* Alerts */}
      {alertError && (
        <div className="p-4 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/60 flex items-center justify-between text-xs text-amber-800 dark:text-amber-300">
          <div className="flex items-center gap-2.5">
            <AlertCircle size={16} className="text-amber-600 dark:text-amber-400 shrink-0" />
            <span>{alertError}</span>
          </div>
          <button onClick={() => setAlertError(null)} className="cursor-pointer">
            <X size={14} />
          </button>
        </div>
      )}

      {alertSuccess && (
        <div className="p-4 rounded-xl bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/60 flex items-center justify-between text-xs text-emerald-800 dark:text-emerald-300">
          <div className="flex items-center gap-2.5">
            <CheckCircle2 size={16} className="text-emerald-600 dark:text-emerald-400 shrink-0" />
            <span>{alertSuccess}</span>
          </div>
          <button onClick={() => setAlertSuccess(null)} className="cursor-pointer">
            <X size={14} />
          </button>
        </div>
      )}

      {/* Section A: Files from computer (Dropzone & Multi-upload) */}
      <div className="p-6 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB] flex items-center gap-2">
              <UploadCloud size={18} className="text-[#0076FF]" />
              <span>A. Fichiers depuis votre ordinateur</span>
            </h2>
            <p className="text-xs text-slate-500 dark:text-[#94A3B8] mt-0.5">
              Glissez-déposez vos fichiers pour une ingestion universelle et un nettoyage automatique certifié.
            </p>
          </div>
        </div>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setIsDragging(false);
            if (e.dataTransfer.files) handleFiles(e.dataTransfer.files);
          }}
          onClick={() => fileInputRef.current?.click()}
          className={`p-8 border-2 border-dashed rounded-2xl text-center cursor-pointer transition-colors ${
            isDragging
              ? "border-[#0076FF] bg-blue-50/50 dark:bg-blue-950/20"
              : "border-slate-200 dark:border-white/[0.12] hover:border-slate-300 dark:hover:border-white/[0.2] bg-slate-50/50 dark:bg-[#060B13]/30"
          }`}
        >
          <div className="w-12 h-12 rounded-2xl bg-blue-50 dark:bg-[#111D3D] text-[#0076FF] dark:text-[#00D4FF] flex items-center justify-center mx-auto mb-3">
            <UploadCloud size={24} />
          </div>
          <div className="text-xs font-bold text-slate-800 dark:text-[#F4F7FB]">
            Cliquez pour importer ou glissez-déposez vos fichiers ici
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
            Formats supportés : CSV, XLS, XLSX, JSON, PDF, DOC, DOCX, Parquet (Max 50 Mo par fichier)
          </div>
        </div>

        {uploadProgress !== null && (
          <div className="space-y-1.5 pt-2">
            <div className="flex items-center justify-between text-xs text-slate-600 dark:text-slate-400 font-semibold">
              <span>Ingestion et nettoyage automatique en cours...</span>
              <span>{uploadProgress}%</span>
            </div>
            <div className="h-2 w-full rounded-full bg-slate-100 dark:bg-white/[0.08] overflow-hidden">
              <div
                className="h-full rounded-full bg-[#0076FF] transition-all duration-300"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Section B: Online stores */}
      <div className="p-6 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
        <div>
          <h2 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB] flex items-center gap-2">
            <Store size={18} className="text-[#0076FF]" />
            <span>B. Boutiques en ligne & Places de marché</span>
          </h2>
          <p className="text-xs text-slate-500 dark:text-[#94A3B8] mt-0.5">
            Intégrations testées et certifiées pour l'extraction de vos commandes, stocks et clients.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {/* Shopify */}
          {(() => {
            const conn = connections.find((c) => c.provider.toLowerCase() === "shopify");
            const isSyncing = conn?.status === "syncing" || actionLoading;
            const isError = conn && (conn.status === "error" || conn.status === "failed");
            const isConnected = conn && (conn.is_active || conn.status === "active" || conn.status === "completed");

            return (
              <div className="p-5 rounded-2xl bg-slate-50 dark:bg-[#111D3D] border border-slate-200/60 dark:border-white/[0.06] flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="font-extrabold text-sm text-slate-900 dark:text-[#F4F7FB]">Shopify</span>
                      <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-medium">Disponible</span>
                    </div>
                    {isSyncing ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 text-[#0076FF] dark:bg-blue-950/40 dark:text-blue-400 animate-pulse">
                        <RefreshCw size={10} className="animate-spin" />
                        <span>Synchronisation</span>
                      </span>
                    ) : isError ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-400">
                        <AlertTriangle size={10} />
                        <span>Erreur</span>
                      </span>
                    ) : isConnected ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400">
                        <CheckCircle2 size={10} />
                        <span>Connecté</span>
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-200/70 dark:bg-white/[0.08] text-slate-600 dark:text-slate-400">
                        Non connecté
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-500 dark:text-[#94A3B8] mt-1.5">
                    Commandes, produits, inventaire et clients synchronisés via OAuth 2.0 officiel.
                  </p>
                </div>
                <div className="mt-4 pt-3 border-t border-slate-200/60 dark:border-white/[0.06] flex items-center justify-between">
                  <span className="text-[11px] text-slate-400">OAuth / REST</span>
                  {isConnected ? (
                    <button
                      onClick={() => handleTriggerSync(conn.id)}
                      disabled={actionLoading}
                      className="px-3 py-1.5 rounded-xl bg-blue-50 text-[#0076FF] hover:bg-blue-100 dark:bg-white/[0.08] dark:text-[#00D4FF] text-xs font-semibold transition-colors cursor-pointer"
                    >
                      Synchroniser
                    </button>
                  ) : (
                    <button
                      onClick={() => {
                        const shop = prompt("Entrez le domaine de votre boutique Shopify (ex: ma-boutique.myshopify.com) :");
                        if (shop) {
                          window.location.href = `/api/v1/connectors/shopify/authorize?shop=${encodeURIComponent(shop)}`;
                        }
                      }}
                      className="px-3 py-1.5 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer"
                    >
                      Connecter
                    </button>
                  )}
                </div>
              </div>
            );
          })()}

          {/* WooCommerce */}
          {(() => {
            const conn = connections.find((c) => c.provider.toLowerCase() === "woocommerce");
            const isSyncing = conn?.status === "syncing" || actionLoading;
            const isError = conn && (conn.status === "error" || conn.status === "failed");
            const isConnected = conn && (conn.is_active || conn.status === "active" || conn.status === "completed");

            return (
              <div className="p-5 rounded-2xl bg-slate-50 dark:bg-[#111D3D] border border-slate-200/60 dark:border-white/[0.06] flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="font-extrabold text-sm text-slate-900 dark:text-[#F4F7FB]">WooCommerce</span>
                      <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-medium">Disponible</span>
                    </div>
                    {isSyncing ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 text-[#0076FF] dark:bg-blue-950/40 dark:text-blue-400 animate-pulse">
                        <RefreshCw size={10} className="animate-spin" />
                        <span>Synchronisation</span>
                      </span>
                    ) : isError ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-400">
                        <AlertTriangle size={10} />
                        <span>Erreur</span>
                      </span>
                    ) : isConnected ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400">
                        <CheckCircle2 size={10} />
                        <span>Connecté</span>
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-200/70 dark:bg-white/[0.08] text-slate-600 dark:text-slate-400">
                        Non connecté
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-500 dark:text-[#94A3B8] mt-1.5">
                    Connexion directe par clés API REST sécurisées avec synchronisation bidirectionnelle.
                  </p>
                </div>
                <div className="mt-4 pt-3 border-t border-slate-200/60 dark:border-white/[0.06] flex items-center justify-between">
                  <span className="text-[11px] text-slate-400">API REST v3</span>
                  {isConnected ? (
                    <button
                      onClick={() => handleTriggerSync(conn.id)}
                      disabled={actionLoading}
                      className="px-3 py-1.5 rounded-xl bg-blue-50 text-[#0076FF] hover:bg-blue-100 dark:bg-white/[0.08] dark:text-[#00D4FF] text-xs font-semibold transition-colors cursor-pointer"
                    >
                      Synchroniser
                    </button>
                  ) : (
                    <button
                      onClick={() => setIsWooModalOpen(true)}
                      className="px-3 py-1.5 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer"
                    >
                      Connecter
                    </button>
                  )}
                </div>
              </div>
            );
          })()}

          {/* Etsy */}
          <div className="p-5 rounded-2xl bg-slate-50/70 dark:bg-[#111D3D]/60 border border-slate-200/50 dark:border-white/[0.05] flex flex-col justify-between opacity-90">
            <div>
              <div className="flex items-center justify-between">
                <span className="font-extrabold text-sm text-slate-900 dark:text-[#F4F7FB]">Etsy</span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-200/70 dark:bg-white/[0.08] text-slate-500 dark:text-slate-400">
                  Bientôt disponible
                </span>
              </div>
              <p className="text-xs text-slate-500 dark:text-[#94A3B8] mt-1.5">
                Marketplace Etsy (en cours de certification officielle pour une prochaine mise à jour).
              </p>
            </div>
            <div className="mt-4 pt-3 border-t border-slate-200/60 dark:border-white/[0.06] flex items-center justify-between">
              <span className="text-[11px] text-slate-400">Open API v3</span>
              <button
                disabled
                className="px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-white/[0.05] text-slate-400 text-xs font-medium cursor-not-allowed"
              >
                Bientôt disponible
              </button>
            </div>
          </div>

          {/* Honest "Coming soon" cards for other platforms */}
          {["Amazon", "eBay", "PrestaShop", "BigCommerce", "Magento", "Square"].map((platform) => (
            <div
              key={platform}
              className="p-5 rounded-2xl bg-slate-50/60 dark:bg-[#111D3D]/50 border border-slate-200/40 dark:border-white/[0.04] flex flex-col justify-between opacity-80"
            >
              <div>
                <div className="flex items-center justify-between">
                  <span className="font-extrabold text-sm text-slate-700 dark:text-slate-300">{platform}</span>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-200 dark:bg-white/[0.08] text-slate-500 dark:text-slate-400">
                    Bientôt disponible
                  </span>
                </div>
                <p className="text-xs text-slate-400 dark:text-slate-500 mt-1.5">
                  Connecteur en cours d'intégration certifiée pour la prochaine mise à jour.
                </p>
              </div>
              <div className="mt-4 pt-3 border-t border-slate-200/40 dark:border-white/[0.04] flex items-center justify-between">
                <span className="text-[11px] text-slate-400 flex items-center gap-1">
                  <Lock size={12} /> Prévu
                </span>
                <button
                  disabled
                  className="px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-white/[0.05] text-slate-400 text-xs font-medium cursor-not-allowed"
                >
                  Bientôt
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Section C: Connected sources */}
      <div className="p-6 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-slate-100 dark:border-white/[0.06]">
          <div>
            <h2 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB] flex items-center gap-2">
              <CheckCircle2 size={18} className="text-emerald-500" />
              <span>C. Sources actuellement connectées</span>
            </h2>
            <p className="text-xs text-slate-500 dark:text-[#94A3B8] mt-0.5">
              Boutiques actives alimentant les modules Retail AI, CRM AI et Comptabilité de votre organisation.
            </p>
          </div>

          {connections.length > 0 && (
            <button
              onClick={() => handleTriggerSync()}
              disabled={actionLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer"
            >
              <RefreshCw size={13} className={actionLoading ? "animate-spin" : ""} />
              <span>Tout resynchroniser</span>
            </button>
          )}
        </div>

        {connections.length === 0 ? (
          <div className="p-8 text-center rounded-xl bg-slate-50/50 dark:bg-[#060B13]/30 border border-dashed border-slate-200 dark:border-white/[0.06] text-xs text-slate-400 dark:text-slate-500">
            Aucune boutique connectée pour le moment. Choisissez WooCommerce, Shopify ou Etsy ci-dessus pour connecter vos données.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {connections.map((conn) => (
              <div
                key={conn.id}
                className="p-4 rounded-xl bg-slate-50 dark:bg-[#111D3D] border border-slate-100 dark:border-white/[0.06] space-y-3"
              >
                <div className="flex items-center justify-between">
                  <div className="font-bold text-xs text-slate-900 dark:text-white capitalize flex items-center gap-2">
                    <Store size={14} className="text-[#0076FF]" />
                    <span>{conn.provider} — {conn.store_name || conn.store_url || "Boutique"}</span>
                  </div>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400 flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                    <span>Connecté</span>
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-500 dark:text-slate-400">
                  <div>
                    Dernière synchro: {conn.last_synced_at ? new Date(conn.last_synced_at).toLocaleString(locale) : "Récente"}
                  </div>
                  <div className="text-right font-semibold text-slate-700 dark:text-slate-300">
                    {conn.records_count || 0} enregistrements
                  </div>
                </div>

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-200/60 dark:border-white/[0.06]">
                  <button
                    onClick={() => handleTriggerSync(conn.id)}
                    disabled={actionLoading}
                    className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-blue-50 text-[#0076FF] dark:bg-white/[0.08] dark:text-[#00D4FF] text-[11px] font-semibold transition-colors cursor-pointer"
                  >
                    <RefreshCw size={12} className={actionLoading ? "animate-spin" : ""} />
                    <span>Synchroniser</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Section D: Synchronization history */}
      <div className="p-6 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
        <div>
          <h2 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB] flex items-center gap-2">
            <Clock size={18} className="text-[#0076FF]" />
            <span>D. Historique des synchronisations</span>
          </h2>
          <p className="text-xs text-slate-500 dark:text-[#94A3B8] mt-0.5">
            Journal complet des cycles d'extraction, données reçues et mises à jour incrémentales.
          </p>
        </div>

        {syncHistory.length === 0 ? (
          <div className="p-8 text-center rounded-xl bg-slate-50/50 dark:bg-[#060B13]/30 border border-dashed border-slate-200 dark:border-white/[0.06] text-xs text-slate-400 dark:text-slate-500">
            Aucun historique de synchronisation enregistré.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-200/80 dark:border-white/[0.08] bg-slate-50/70 dark:bg-[#060B13]/40 text-slate-500 dark:text-slate-400 font-semibold">
                  <th className="py-3 px-4">Date</th>
                  <th className="py-3 px-4">Source</th>
                  <th className="py-3 px-4">Enregistrements</th>
                  <th className="py-3 px-4">Mises à jour</th>
                  <th className="py-3 px-4">Erreurs</th>
                  <th className="py-3 px-4 text-right">Statut</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-white/[0.04]">
                {syncHistory.map((log) => (
                  <tr key={log.id} className="hover:bg-slate-50/80 dark:hover:bg-white/[0.02]">
                    <td className="py-3 px-4 text-slate-600 dark:text-slate-400">
                      {new Date(log.timestamp).toLocaleString(locale)}
                    </td>
                    <td className="py-3 px-4 font-bold capitalize text-slate-800 dark:text-white">
                      {log.provider}
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-700 dark:text-slate-300">
                      {log.records_synced}
                    </td>
                    <td className="py-3 px-4 font-mono text-emerald-600 dark:text-emerald-400">
                      +{log.records_updated}
                    </td>
                    <td className="py-3 px-4 font-mono text-rose-600">
                      {log.records_failed}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-600 dark:text-emerald-400">
                        <CheckCircle2 size={12} />
                        <span>Réussi</span>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Section E: Imported datasets */}
      <div className="p-6 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB] flex items-center gap-2">
              <Layers size={18} className="text-[#0076FF]" />
              <span>E. Jeux de données & Fichiers importés ({datasets.length})</span>
            </h2>
            <p className="text-xs text-slate-500 dark:text-[#94A3B8] mt-0.5">
              Consultez, prévisualisez et téléchargez vos données brutes et traitées par l'IA.
            </p>
          </div>
        </div>

        {datasets.length === 0 ? (
          <div className="p-8 text-center rounded-xl bg-slate-50/50 dark:bg-[#060B13]/30 border border-dashed border-slate-200 dark:border-white/[0.06] text-xs text-slate-400 dark:text-slate-500">
            Aucun jeu de données importé. Utilisez le bouton "Ajouter des fichiers" ci-dessus pour importer votre premier fichier.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-200/80 dark:border-white/[0.08] bg-slate-50/70 dark:bg-[#060B13]/40 text-slate-500 dark:text-slate-400 font-semibold">
                  <th className="py-3 px-4">Nom du fichier / Source</th>
                  <th className="py-3 px-4">Lignes</th>
                  <th className="py-3 px-4">Colonnes</th>
                  <th className="py-3 px-4">Qualité</th>
                  <th className="py-3 px-4">Statut</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-white/[0.04]">
                {datasets.map((ds) => (
                  <tr key={ds.id} className="hover:bg-slate-50/80 dark:hover:bg-white/[0.02]">
                    <td className="py-3 px-4 font-bold text-slate-900 dark:text-white">
                      <div className="flex items-center gap-2">
                        <FileText size={15} className="text-[#0076FF] shrink-0" />
                        <span className="truncate max-w-xs">{ds.name}</span>
                      </div>
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-600 dark:text-slate-400">
                      {ds.rows_count?.toLocaleString() || "—"}
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-600 dark:text-slate-400">
                      {ds.columns_count || ds.columns?.length || "—"}
                    </td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400 text-[10px] font-bold">
                        {ds.quality_score ? `${ds.quality_score}%` : "100%"}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      {ds.source_missing || ds.pipeline_status === "source_missing" ? (
                        <span
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400 text-[10px] font-bold"
                          title={ds.source_missing_message || "Fichier source indisponible"}
                        >
                          <AlertTriangle size={12} className="shrink-0 text-amber-500" />
                          <span>Fichier source indisponible</span>
                        </span>
                      ) : ds.pipeline_status === "analyzing" || ds.status === "analyzing" ? (
                        <span className="inline-flex items-center gap-1 text-[10px] font-bold text-blue-600 dark:text-blue-400">
                          <RefreshCw size={12} className="animate-spin" />
                          <span>Analyse...</span>
                        </span>
                      ) : ds.status === "failed" || ds.pipeline_status === "failed" ? (
                        <span className="inline-flex items-center gap-1 text-[10px] font-bold text-rose-600 dark:text-rose-400">
                          <AlertCircle size={12} />
                          <span>Échec</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-600 dark:text-emerald-400">
                          <CheckCircle2 size={12} />
                          <span>Prêt</span>
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        {ds.source_missing || ds.pipeline_status === "source_missing" ? (
                          <button
                            onClick={() => fileInputRef.current?.click()}
                            title="Réimporter ce fichier pour restaurer l'analyse"
                            className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-amber-50 hover:bg-amber-100 dark:bg-amber-950/40 dark:hover:bg-amber-900/50 text-amber-700 dark:text-amber-300 text-[11px] font-semibold transition-colors cursor-pointer"
                          >
                            <UploadCloud size={12} />
                            <span>Réimporter</span>
                          </button>
                        ) : (
                          <>
                            <button
                              onClick={() => setPreviewDataset(ds)}
                              title="Aperçu des colonnes et données"
                              className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/[0.06] text-slate-500 dark:text-slate-400 cursor-pointer"
                            >
                              <Eye size={14} />
                            </button>
                            <button
                              onClick={() => handleDownloadDataset(ds, "csv")}
                              title="Télécharger les données nettoyées (CSV)"
                              className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/[0.06] text-[#0076FF] cursor-pointer"
                            >
                              <Download size={14} />
                            </button>
                          </>
                        )}
                        <button
                          onClick={() => setDeleteModalDataset(ds)}
                          title="Supprimer ce jeu de données"
                          className="p-1.5 rounded-lg hover:bg-rose-50 dark:hover:bg-rose-950/20 text-slate-400 hover:text-rose-600 cursor-pointer"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Section F: Failed imports requiring attention */}
      {failedDatasets.length > 0 && (
        <div className="p-6 rounded-2xl bg-amber-50/50 dark:bg-amber-950/20 border border-amber-200/80 dark:border-amber-800/40 shadow-xs space-y-3">
          <div className="flex items-center gap-2 text-amber-800 dark:text-amber-300 font-bold text-sm">
            <AlertTriangle size={18} />
            <span>F. Imports nécessitant votre attention ({failedDatasets.length})</span>
          </div>
          <p className="text-xs text-amber-700 dark:text-amber-400">
            Ces fichiers n'ont pas pu être traités complètement (format corrompu ou colonnes manquantes). Vous pouvez les réimporter ou les supprimer.
          </p>
          <div className="space-y-2">
            {failedDatasets.map((fd) => (
              <div
                key={fd.id}
                className="p-3 rounded-xl bg-white dark:bg-[#0B132B] border border-amber-200/60 dark:border-amber-800/40 flex items-center justify-between text-xs"
              >
                <div className="font-semibold text-slate-800 dark:text-white">
                  {fd.name}
                </div>
                <button
                  onClick={() => setDeleteModalDataset(fd)}
                  className="px-2.5 py-1 rounded-lg bg-rose-50 hover:bg-rose-100 text-rose-600 text-[11px] font-semibold cursor-pointer"
                >
                  Supprimer
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Modal: Preview Dataset */}
      {previewDataset && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="w-full max-w-2xl rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200 dark:border-white/[0.12] p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-white/[0.06]">
              <div>
                <h3 className="text-base font-bold text-slate-900 dark:text-white">
                  Aperçu : {previewDataset.name}
                </h3>
                <div className="text-xs text-slate-400 mt-0.5">
                  {previewDataset.rows_count || 0} lignes • {previewDataset.columns_count || 0} colonnes
                </div>
              </div>
              <button
                onClick={() => setPreviewDataset(null)}
                className="p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-white/[0.06] text-slate-400 cursor-pointer"
              >
                <X size={16} />
              </button>
            </div>

            <div className="space-y-3">
              {(previewDataset.source_missing || previewDataset.pipeline_status === "source_missing") && (
                <div className="p-3.5 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200/80 dark:border-amber-800/50 text-xs text-amber-800 dark:text-amber-300 flex items-start gap-2.5">
                  <AlertTriangle size={16} className="shrink-0 text-amber-600 dark:text-amber-400 mt-0.5" />
                  <div>
                    <div className="font-bold">Fichier source indisponible</div>
                    <div className="text-[11px] text-amber-700 dark:text-amber-400 mt-0.5">
                      {previewDataset.source_missing_message ||
                        "Le fichier original n'est plus accessible sur le stockage. Utilisez le bouton Réimporter pour recharger ce fichier et relancer l'analyse."}
                    </div>
                  </div>
                </div>
              )}
              <div className="text-xs font-bold text-slate-700 dark:text-slate-300">
                Colonnes détectées et typées par l'IA :
              </div>
              <div className="flex flex-wrap gap-2 max-h-60 overflow-y-auto">
                {previewDataset.columns && previewDataset.columns.length > 0 ? (
                  previewDataset.columns.map((col, idx) => (
                    <div
                      key={idx}
                      className="px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-[#111D3D] text-xs text-slate-800 dark:text-[#F4F7FB] border border-slate-200/60 dark:border-white/[0.06]"
                    >
                      <span className="font-semibold">{col.name}</span>
                      {col.type && (
                        <span className="ml-1.5 text-[10px] text-slate-400 uppercase font-mono">
                          ({col.type})
                        </span>
                      )}
                    </div>
                  ))
                ) : (
                  <div className="text-xs text-slate-400">Colonnes standards synchronisées avec succès.</div>
                )}
              </div>
            </div>

            <div className="flex justify-end pt-3 border-t border-slate-100 dark:border-white/[0.06]">
              <button
                onClick={() => setPreviewDataset(null)}
                className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-white/[0.1] text-xs font-semibold text-slate-800 dark:text-white cursor-pointer"
              >
                Fermer
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Delete Dataset Confirmation */}
      {deleteModalDataset && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="w-full max-w-md rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200 dark:border-white/[0.12] p-6 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-rose-600">
              <div className="p-2 rounded-xl bg-rose-50 dark:bg-rose-950/40">
                <Trash2 size={20} />
              </div>
              <h3 className="text-base font-bold text-slate-900 dark:text-white">
                Confirmer la suppression
              </h3>
            </div>

            <div className="space-y-2 text-xs text-slate-600 dark:text-slate-300">
              <p>
                Êtes-vous sûr de vouloir supprimer définitivement le jeu de données{" "}
                <strong>"{deleteModalDataset.name}"</strong> ?
              </p>
              <div className="p-3 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200/60 dark:border-amber-800/40 text-[11px] text-amber-800 dark:text-amber-300">
                <strong>Impact :</strong> Ce jeu de données ne sera plus utilisé par les analyses prédictives du Retail AI et du Dashboard. Vos boutiques en ligne connectées resteront intactes.
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100 dark:border-white/[0.06]">
              <button
                onClick={() => setDeleteModalDataset(null)}
                className="px-4 py-2 rounded-xl border border-slate-200 dark:border-white/[0.08] hover:bg-slate-100 dark:hover:bg-white/[0.04] text-xs font-semibold text-slate-700 dark:text-slate-300 cursor-pointer"
              >
                Annuler
              </button>
              <button
                onClick={handleConfirmDelete}
                disabled={actionLoading}
                className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer"
              >
                {actionLoading ? "Suppression..." : "Supprimer définitivement"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Connect WooCommerce */}
      {isWooModalOpen && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200 dark:border-white/[0.12] p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-white/[0.06]">
              <div className="flex items-center gap-2">
                <Store size={18} className="text-[#0076FF]" />
                <h3 className="text-base font-bold text-slate-900 dark:text-white">
                  Connecter WooCommerce
                </h3>
              </div>
              <button
                onClick={() => setIsWooModalOpen(false)}
                className="p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-white/[0.06] text-slate-400 cursor-pointer"
              >
                <X size={16} />
              </button>
            </div>

            <form onSubmit={handleConnectWooCommerce} className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  URL de la boutique WooCommerce
                </label>
                <input
                  type="text"
                  required
                  value={wooStoreUrl}
                  onChange={(e) => setWooStoreUrl(e.target.value)}
                  placeholder="https://votre-boutique.com"
                  className="w-full px-3.5 py-2 rounded-xl bg-slate-50 dark:bg-[#111D3D] border border-slate-200 dark:border-white/[0.08] text-xs text-slate-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-[#0076FF]"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Clé client (Consumer Key)
                </label>
                <input
                  type="text"
                  required
                  value={wooKey}
                  onChange={(e) => setWooKey(e.target.value)}
                  placeholder="ck_..."
                  className="w-full px-3.5 py-2 rounded-xl bg-slate-50 dark:bg-[#111D3D] border border-slate-200 dark:border-white/[0.08] text-xs text-slate-800 dark:text-white font-mono focus:outline-none focus:ring-2 focus:ring-[#0076FF]"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Secret client (Consumer Secret)
                </label>
                <input
                  type="password"
                  required
                  value={wooSecret}
                  onChange={(e) => setWooSecret(e.target.value)}
                  placeholder="cs_..."
                  className="w-full px-3.5 py-2 rounded-xl bg-slate-50 dark:bg-[#111D3D] border border-slate-200 dark:border-white/[0.08] text-xs text-slate-800 dark:text-white font-mono focus:outline-none focus:ring-2 focus:ring-[#0076FF]"
                />
              </div>

              <div className="text-[11px] text-slate-400">
                Vos clés API sont chiffrées côté serveur et restent isolées à votre entreprise.
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100 dark:border-white/[0.06]">
                <button
                  type="button"
                  onClick={() => setIsWooModalOpen(false)}
                  className="px-4 py-2 rounded-xl border border-slate-200 dark:border-white/[0.08] hover:bg-slate-100 dark:hover:bg-white/[0.04] text-xs font-semibold text-slate-700 dark:text-slate-300 cursor-pointer"
                >
                  Annuler
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="px-4 py-2 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer"
                >
                  {actionLoading ? "Vérification..." : "Valider et connecter"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
