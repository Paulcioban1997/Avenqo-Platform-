"use client";

import React, { useState, useEffect } from "react";
import {
  TrendingUp,
  Plus,
  DollarSign,
  User,
  Calendar,
  ChevronRight,
  CheckCircle2,
  AlertCircle,
  X,
} from "lucide-react";
import type { AppTranslations } from "@/lib/i18n/app-dictionary";
import { getAuthHeaders } from "@/lib/api-headers";

interface OpportunityItem {
  id: string;
  title: string;
  client_id?: string;
  client_name?: string;
  amount: number;
  probability: number;
  expected_close_date?: string | null;
  stage_id: string;
}

interface StageItem {
  id: string;
  name: string;
  order_index: number;
  opportunities: OpportunityItem[];
}

interface PipelineItem {
  id: string;
  name: string;
  stages: StageItem[];
}

interface CRMPipelinesViewProps {
  t: AppTranslations;
}

export function CRMPipelinesView({ t }: CRMPipelinesViewProps) {
  const [pipelines, setPipelines] = useState<PipelineItem[]>([]);
  const [selectedPipelineId, setSelectedPipelineId] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);

  // New Opportunity modal
  const [isNewOppOpen, setIsNewOppOpen] = useState(false);
  const [oppTitle, setOppTitle] = useState("");
  const [oppAmount, setOppAmount] = useState<number>(0);
  const [oppStageId, setOppStageId] = useState("");
  const [oppCloseDate, setOppCloseDate] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    fetchPipelines();
  }, []);

  const fetchPipelines = async () => {
    setIsLoading(true);
    try {
      const headers = getAuthHeaders();

      const res = await fetch("/api/v1/crm/pipelines", { headers });
      if (res.ok) {
        const data = await res.json();
        setPipelines(data || []);
        if (data && data.length > 0 && !selectedPipelineId) {
          setSelectedPipelineId(data[0].id);
        }
      }
    } catch {
      // Keep empty
    } finally {
      setIsLoading(false);
    }
  };

  const activePipeline = pipelines.find((p) => p.id === selectedPipelineId) || pipelines[0];

  const handleCreateOpportunity = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!oppTitle || !oppStageId) return;

    setIsSubmitting(true);
    try {
      const res = await fetch(`/api/v1/crm/pipelines/${activePipeline.id}/opportunities`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          title: oppTitle,
          amount: oppAmount,
          stage_id: oppStageId,
          expected_close_date: oppCloseDate ? new Date(oppCloseDate).toISOString() : null,
        }),
      });

      if (res.ok) {
        setIsNewOppOpen(false);
        setOppTitle("");
        setOppAmount(0);
        fetchPipelines();
      }
    } catch {
      // ignore
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleMoveStage = async (oppId: string, currentStageIndex: number) => {
    if (!activePipeline) return;
    const nextStage = activePipeline.stages[currentStageIndex + 1];
    if (!nextStage) return;

    try {
      await fetch(`/api/v1/crm/pipelines/opportunities/${oppId}/stage`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify({ stage_id: nextStage.id }),
      });
      fetchPipelines();
    } catch {
      // ignore
    }
  };

  return (
    <div className="space-y-4">
      {/* Top Controls */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-white dark:bg-[#0B0F19] p-4 rounded-2xl border border-slate-200 dark:border-slate-800">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-[#0076FF]" />
          <h3 className="text-sm font-bold text-slate-900 dark:text-white">
            {t.crm.tabs.pipelines || "Pipelines de ventes & opportunités"}
          </h3>
          {pipelines.length > 1 && (
            <select
              value={selectedPipelineId}
              onChange={(e) => setSelectedPipelineId(e.target.value)}
              className="text-xs px-2.5 py-1 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white"
            >
              {pipelines.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          )}
        </div>

        <button
          onClick={() => {
            if (activePipeline?.stages?.[0]) {
              setOppStageId(activePipeline.stages[0].id);
            }
            setIsNewOppOpen(true);
          }}
          className="px-4 py-2 text-xs font-semibold rounded-xl bg-gradient-to-r from-[#0076FF] to-[#00D4FF] text-white shadow-md hover:opacity-90 transition flex items-center gap-1.5"
        >
          <Plus className="w-4 h-4" />
          <span>Nouvelle opportunité</span>
        </button>
      </div>

      {/* Kanban Board */}
      {isLoading ? (
        <div className="py-16 text-center text-slate-400 text-xs">
          Chargement des étapes du pipeline...
        </div>
      ) : !activePipeline || !activePipeline.stages || activePipeline.stages.length === 0 ? (
        <div className="p-8 text-center bg-white dark:bg-[#0B0F19] rounded-2xl border border-slate-200 dark:border-slate-800">
          <p className="text-xs text-slate-400">Aucune étape configurée dans ce pipeline.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 overflow-x-auto pb-4">
          {activePipeline.stages.map((stage, sIdx) => {
            const opps = stage.opportunities || [];
            const totalStageValue = opps.reduce((sum, o) => sum + (o.amount || 0), 0);
            return (
              <div
                key={stage.id}
                className="flex flex-col bg-slate-50 dark:bg-slate-900/40 rounded-2xl p-3 border border-slate-200 dark:border-slate-800 min-h-[500px]"
              >
                {/* Column header */}
                <div className="pb-3 mb-3 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
                  <div>
                    <span className="text-xs font-bold text-slate-900 dark:text-white block">
                      {stage.name}
                    </span>
                    <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-semibold">
                      {totalStageValue.toLocaleString()} $
                    </span>
                  </div>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-semibold border border-slate-200 dark:border-slate-700">
                    {opps.length}
                  </span>
                </div>

                {/* Opps Cards */}
                <div className="flex-1 space-y-2.5 overflow-y-auto">
                  {opps.length === 0 ? (
                    <div className="py-8 text-center text-[11px] text-slate-400 italic">
                      Aucun dossier
                    </div>
                  ) : (
                    opps.map((opp) => (
                      <div
                        key={opp.id}
                        className="p-3.5 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm hover:shadow-md transition text-xs space-y-2"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <h4 className="font-bold text-slate-900 dark:text-white leading-snug">
                            {opp.title}
                          </h4>
                          <span className="font-bold text-emerald-600 dark:text-emerald-400 shrink-0">
                            {opp.amount} $
                          </span>
                        </div>

                        {opp.client_name && (
                          <div className="flex items-center gap-1 text-[11px] text-slate-500">
                            <User className="w-3 h-3 text-slate-400" />
                            <span>{opp.client_name}</span>
                          </div>
                        )}

                        {sIdx < activePipeline.stages.length - 1 && (
                          <div className="pt-2 border-t border-slate-100 dark:border-slate-700/60 flex justify-end">
                            <button
                              onClick={() => handleMoveStage(opp.id, sIdx)}
                              className="text-[10px] font-semibold text-[#0076FF] hover:underline flex items-center gap-0.5"
                            >
                              Étape suivante <ChevronRight className="w-3 h-3" />
                            </button>
                          </div>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* NEW OPPORTUNITY MODAL */}
      {isNewOppOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="w-full max-w-md bg-white dark:bg-[#0B0F19] rounded-2xl border border-slate-200 dark:border-slate-800 shadow-2xl p-6">
            <div className="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-slate-800 mb-4">
              <h3 className="text-base font-bold text-slate-900 dark:text-white">
                Ajouter une opportunité
              </h3>
              <button
                onClick={() => setIsNewOppOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateOpportunity} className="space-y-3 text-xs">
              <div>
                <label className="text-slate-600 dark:text-slate-400 block mb-1 font-medium">
                  Titre du contrat ou besoin *
                </label>
                <input
                  type="text"
                  required
                  value={oppTitle}
                  onChange={(e) => setOppTitle(e.target.value)}
                  placeholder="Ex: Contrat maintenance annuel flotte"
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                />
              </div>

              <div>
                <label className="text-slate-600 dark:text-slate-400 block mb-1 font-medium">
                  Montant estimé (CAD)
                </label>
                <input
                  type="number"
                  min="0"
                  value={oppAmount}
                  onChange={(e) => setOppAmount(parseFloat(e.target.value) || 0)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                />
              </div>

              <div>
                <label className="text-slate-600 dark:text-slate-400 block mb-1 font-medium">
                  Étape initiale
                </label>
                <select
                  value={oppStageId}
                  onChange={(e) => setOppStageId(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                >
                  {activePipeline?.stages?.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-200 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsNewOppOpen(false)}
                  className="px-4 py-2 text-slate-600 dark:text-slate-400 font-medium hover:text-slate-900 dark:hover:text-white"
                >
                  Annuler
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-5 py-2 rounded-xl bg-gradient-to-r from-[#0076FF] to-[#00D4FF] text-white font-medium shadow-md hover:opacity-90 disabled:opacity-50"
                >
                  {isSubmitting ? "Création..." : "Créer l'opportunité"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
