"use client";

import React, { useState, useEffect } from "react";
import { Check, Globe, Layers, Store, File, AlertCircle, LoaderCircle, X } from "lucide-react";
import { useLocale } from "@/lib/i18n/locale-context";
import { MULTI_SOURCE_SELECTION_COPY } from "@/lib/i18n/source-selector-copy";
import { apiFetch } from "@/lib/api-request";

export interface SourceItem {
  id: string;
  source_type: string;
  display_name: string;
  provider: string | null;
  status: string;
  enabled: boolean;
  last_synchronized_at: string | null;
  is_selected: boolean;
}

export interface WorkspaceSourceSelectionData {
  mode: "ALL" | "CUSTOM_SET" | "SINGLE";
  selected_source_ids: string[];
  selected_sources: SourceItem[];
  available_sources: SourceItem[];
  effective_count: number;
}

interface WorkspaceSourceSelectionModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectionSaved?: (data: WorkspaceSourceSelectionData) => void;
}

export function WorkspaceSourceSelectionModal({
  isOpen,
  onClose,
  onSelectionSaved,
}: WorkspaceSourceSelectionModalProps) {
  const { locale } = useLocale();
  const copy = MULTI_SOURCE_SELECTION_COPY[locale] || MULTI_SOURCE_SELECTION_COPY.en;

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [mode, setMode] = useState<"ALL" | "CUSTOM_SET" | "SINGLE">("ALL");
  const [availableSources, setAvailableSources] = useState<SourceItem[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    setError(null);

    apiFetch("/api/v1/workspace/sources/selection")
      .then((res) => res.json())
      .then((data: WorkspaceSourceSelectionData) => {
        setMode(data.mode);
        setAvailableSources(data.available_sources || []);
        setSelectedIds(data.selected_source_ids || []);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Erreur de chargement des sources");
      })
      .finally(() => setLoading(false));
  }, [isOpen]);

  const toggleSource = (sourceId: string) => {
    if (mode === "SINGLE") {
      setSelectedIds([sourceId]);
    } else if (mode === "CUSTOM_SET") {
      setSelectedIds((prev) =>
        prev.includes(sourceId) ? prev.filter((id) => id !== sourceId) : [...prev, sourceId]
      );
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);

    if (mode === "SINGLE" && selectedIds.length !== 1) {
      setError("Veuillez sélectionner exactement une source.");
      setSaving(false);
      return;
    }

    if (mode === "CUSTOM_SET" && selectedIds.length === 0) {
      setError("Veuillez sélectionner au moins une source.");
      setSaving(false);
      return;
    }

    try {
      const res = await apiFetch(
        "/api/v1/workspace/sources/selection",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            mode,
            selected_source_ids: mode === "ALL" ? [] : selectedIds,
          }),
        }
      );
      const updated = (await res.json()) as WorkspaceSourceSelectionData;
      if (onSelectionSaved) {
        onSelectionSaved(updated);
      }
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur d'enregistrement");
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="source-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
    >
      <div className="relative w-full max-w-lg rounded-xl border border-gray-200 bg-white p-6 shadow-2xl dark:border-gray-800 dark:bg-[#0B132B]">
        {/* En-tête */}
        <div className="flex items-center justify-between border-b border-gray-100 pb-4 dark:border-gray-800">
          <div className="flex items-center gap-2">
            <Layers className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
            <h2 id="source-modal-title" className="text-base font-semibold text-gray-900 dark:text-white">
              {copy.title}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 dark:hover:bg-white/10"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {error && (
          <div className="mt-4 flex items-center gap-2 rounded-lg bg-red-50 p-3 text-xs text-red-700 dark:bg-red-950/40 dark:text-red-300">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {loading ? (
          <div className="flex h-48 items-center justify-center">
            <LoaderCircle className="h-6 w-6 animate-spin text-emerald-600" />
          </div>
        ) : (
          <div className="mt-4 space-y-4">
            {/* Sélecteur de Mode */}
            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                onClick={() => setMode("ALL")}
                className={`flex flex-col items-center justify-center rounded-lg border p-3 text-xs font-medium transition-all ${
                  mode === "ALL"
                    ? "border-emerald-500 bg-emerald-50 text-emerald-900 dark:border-emerald-400 dark:bg-emerald-950/40 dark:text-emerald-200"
                    : "border-gray-200 bg-gray-50 text-gray-700 hover:bg-gray-100 dark:border-gray-800 dark:bg-white/5 dark:text-gray-300"
                }`}
              >
                <Globe className="mb-1.5 h-4 w-4" />
                <span>{copy.all}</span>
              </button>

              <button
                type="button"
                onClick={() => setMode("CUSTOM_SET")}
                className={`flex flex-col items-center justify-center rounded-lg border p-3 text-xs font-medium transition-all ${
                  mode === "CUSTOM_SET"
                    ? "border-emerald-500 bg-emerald-50 text-emerald-900 dark:border-emerald-400 dark:bg-emerald-950/40 dark:text-emerald-200"
                    : "border-gray-200 bg-gray-50 text-gray-700 hover:bg-gray-100 dark:border-gray-800 dark:bg-white/5 dark:text-gray-300"
                }`}
              >
                <Layers className="mb-1.5 h-4 w-4" />
                <span>{copy.custom}</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  setMode("SINGLE");
                  if (selectedIds.length > 1) {
                    setSelectedIds([selectedIds[0]]);
                  }
                }}
                className={`flex flex-col items-center justify-center rounded-lg border p-3 text-xs font-medium transition-all ${
                  mode === "SINGLE"
                    ? "border-emerald-500 bg-emerald-50 text-emerald-900 dark:border-emerald-400 dark:bg-emerald-950/40 dark:text-emerald-200"
                    : "border-gray-200 bg-gray-50 text-gray-700 hover:bg-gray-100 dark:border-gray-800 dark:bg-white/5 dark:text-gray-300"
                }`}
              >
                <Store className="mb-1.5 h-4 w-4" />
                <span>{copy.single}</span>
              </button>
            </div>

            {/* Liste des sources */}
            <div className="max-h-60 overflow-y-auto space-y-2 rounded-lg border border-gray-100 p-2 dark:border-gray-800">
              {availableSources.length === 0 ? (
                <p className="py-6 text-center text-xs text-gray-500">Aucune source connectée.</p>
              ) : (
                availableSources.map((source) => {
                  const isChecked =
                    mode === "ALL"
                      ? source.enabled && source.status.toUpperCase() !== "DISCONNECTED"
                      : selectedIds.includes(source.id);

                  const isClickable = mode !== "ALL" && source.status.toUpperCase() !== "DISCONNECTED";

                  return (
                    <div
                      key={source.id}
                      onClick={() => isClickable && toggleSource(source.id)}
                      className={`flex items-center justify-between rounded-lg p-2.5 text-xs transition-colors ${
                        isClickable ? "cursor-pointer hover:bg-gray-50 dark:hover:bg-white/5" : "opacity-75"
                      } ${isChecked ? "bg-emerald-50/50 dark:bg-emerald-950/20" : ""}`}
                    >
                      <div className="flex items-center gap-2.5">
                        {source.source_type === "connector" ? (
                          <Store className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                        ) : (
                          <File className="h-4 w-4 text-blue-500" />
                        )}
                        <div>
                          <p className="font-medium text-gray-900 dark:text-white">
                            {source.provider && (
                              <span className="capitalize text-gray-500">{source.provider} — </span>
                            )}
                            {source.display_name}
                          </p>
                          <p className="text-[10px] text-gray-500">
                            Statut : <span className="uppercase">{source.status}</span>
                          </p>
                        </div>
                      </div>

                      <div
                        className={`flex h-4 w-4 items-center justify-center rounded border ${
                          isChecked
                            ? "border-emerald-600 bg-emerald-600 text-white"
                            : "border-gray-300 dark:border-gray-700"
                        }`}
                      >
                        {isChecked && <Check className="h-3 w-3" />}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        )}

        {/* Pied de dialogue */}
        <div className="mt-6 flex items-center justify-end gap-2 border-t border-gray-100 pt-4 dark:border-gray-800">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-xs font-medium text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-white/10"
          >
            Annuler
          </button>
          <button
            type="button"
            disabled={saving || loading}
            onClick={handleSave}
            className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-medium text-white transition-colors hover:bg-emerald-700 disabled:opacity-50"
          >
            {saving && <LoaderCircle className="h-3.5 w-3.5 animate-spin" />}
            <span>{copy.save}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
