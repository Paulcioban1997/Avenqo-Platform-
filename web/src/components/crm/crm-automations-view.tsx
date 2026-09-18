"use client";

import React, { useState, useEffect } from "react";
import {
  Zap,
  CheckCircle2,
  Clock,
  Mail,
  MessageSquare,
  Bell,
  Sparkles,
  ToggleLeft,
  ToggleRight,
  Plus,
  AlertCircle,
  X,
} from "lucide-react";
import type { AppTranslations } from "@/lib/i18n/app-dictionary";
import { getAuthHeaders } from "@/lib/api-headers";

interface AutomationItem {
  id: string;
  name: string;
  trigger_event: string;
  action_type: string;
  is_active: boolean;
  action_config?: Record<string, any>;
  last_triggered_at?: string | null;
  executions_count?: number;
}

interface CRMAutomationsViewProps {
  t: AppTranslations;
}

export function CRMAutomationsView({ t }: CRMAutomationsViewProps) {
  const [automations, setAutomations] = useState<AutomationItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isNewModalOpen, setIsNewModalOpen] = useState(false);
  const [name, setName] = useState("");
  const [triggerEvent, setTriggerEvent] = useState("appointment_created");
  const [actionType, setActionType] = useState("send_email");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    fetchAutomations();
  }, []);

  const fetchAutomations = async () => {
    setIsLoading(true);
    try {
      const headers = getAuthHeaders();

      const res = await fetch("/api/v1/crm/automations", { headers });
      if (res.ok) {
        const data = await res.json();
        setAutomations(data || []);
      }
    } catch {
      // keep empty
    } finally {
      setIsLoading(false);
    }
  };

  const handleToggle = async (auto: AutomationItem) => {
    try {
      await fetch(`/api/v1/crm/automations/${auto.id}/toggle`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify({ is_active: !auto.is_active }),
      });
      setAutomations((prev) =>
        prev.map((a) => (a.id === auto.id ? { ...a, is_active: !a.is_active } : a))
      );
    } catch {
      // ignore
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name) return;

    setIsSubmitting(true);
    try {
      const res = await fetch("/api/v1/crm/automations", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          name,
          trigger_event: triggerEvent,
          action_type: actionType,
          is_active: true,
        }),
      });

      if (res.ok) {
        setIsNewModalOpen(false);
        setName("");
        fetchAutomations();
      }
    } catch {
      // ignore
    } finally {
      setIsSubmitting(false);
    }
  };

  const getTriggerLabel = (event: string) => {
    switch (event) {
      case "appointment_created":
        return "Rendez-vous créé";
      case "appointment_approaching":
        return "Rendez-vous dans 24h";
      case "appointment_cancelled":
        return "Rendez-vous annulé";
      case "client_inactive_30d":
        return "Client inactif depuis 30 jours";
      case "new_lead":
        return "Nouveau prospect / lead";
      case "pipeline_stage_changed":
        return "Étape de vente franchie";
      default:
        return event;
    }
  };

  const getActionLabel = (act: string) => {
    switch (act) {
      case "send_email":
        return "Envoyer un courriel de confirmation";
      case "send_sms":
        return "Envoyer un rappel par SMS";
      case "create_reminder":
        return "Créer un rappel tâche employé";
      case "generate_ai_task":
        return "Générer une synthèse IA";
      default:
        return act;
    }
  };

  const getActionIcon = (act: string) => {
    switch (act) {
      case "send_email":
        return <Mail className="w-4 h-4 text-[#0076FF]" />;
      case "send_sms":
        return <MessageSquare className="w-4 h-4 text-emerald-500" />;
      case "create_reminder":
        return <Bell className="w-4 h-4 text-amber-500" />;
      case "generate_ai_task":
        return <Sparkles className="w-4 h-4 text-violet-500" />;
      default:
        return <Zap className="w-4 h-4 text-slate-400" />;
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between bg-white dark:bg-[#0B0F19] p-4 rounded-2xl border border-slate-200 dark:border-slate-800">
        <div>
          <h3 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <Zap className="w-4 h-4 text-amber-500" />
            {t.crm.tabs.automations || "Automations & Scénarios CRM"}
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Rappels automatiques, alertes SMS, notifications client et synchronisation d'actions.
          </p>
        </div>

        <button
          onClick={() => setIsNewModalOpen(true)}
          className="px-4 py-2 text-xs font-semibold rounded-xl bg-gradient-to-r from-[#0076FF] to-[#00D4FF] text-white shadow-md hover:opacity-90 transition flex items-center gap-1.5"
        >
          <Plus className="w-4 h-4" />
          <span>Nouvelle règle</span>
        </button>
      </div>

      {isLoading ? (
        <div className="py-16 text-center text-slate-400 text-xs">
          Chargement des automations actives...
        </div>
      ) : automations.length === 0 ? (
        <div className="p-8 text-center bg-white dark:bg-[#0B0F19] rounded-2xl border border-slate-200 dark:border-slate-800">
          <Zap className="w-8 h-8 mx-auto text-slate-300 dark:text-slate-600 mb-2" />
          <p className="text-xs text-slate-500">Aucun scénario d'automatisation actif.</p>
          <button
            onClick={() => setIsNewModalOpen(true)}
            className="mt-3 px-3 py-1.5 text-xs font-semibold rounded-lg bg-[#0076FF] text-white"
          >
            Créer la première règle
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {automations.map((auto) => (
            <div
              key={auto.id}
              className={`p-4 rounded-2xl border transition ${
                auto.is_active
                  ? "bg-white dark:bg-[#0B0F19] border-slate-200 dark:border-slate-800 shadow-sm"
                  : "bg-slate-50/60 dark:bg-slate-900/30 border-slate-200 dark:border-slate-800/60 opacity-60"
              }`}
            >
              <div className="flex items-start justify-between gap-3 mb-3">
                <div className="flex items-center gap-2">
                  <div className="p-2 rounded-xl bg-slate-100 dark:bg-slate-800">
                    {getActionIcon(auto.action_type)}
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-slate-900 dark:text-white">{auto.name}</h4>
                    <span className="text-[10px] text-slate-400">
                      Déclenché {auto.executions_count || 0} fois
                    </span>
                  </div>
                </div>

                <button
                  onClick={() => handleToggle(auto)}
                  className="text-slate-400 hover:text-[#0076FF] transition"
                  title={auto.is_active ? "Désactiver" : "Activer"}
                >
                  {auto.is_active ? (
                    <ToggleRight className="w-7 h-7 text-[#0076FF]" />
                  ) : (
                    <ToggleLeft className="w-7 h-7 text-slate-400" />
                  )}
                </button>
              </div>

              <div className="p-3 rounded-xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-800 space-y-1.5 text-xs">
                <div className="flex items-center gap-1.5 text-slate-600 dark:text-slate-300">
                  <span className="text-[10px] font-bold text-slate-400 uppercase">QUAND:</span>
                  <span className="font-medium">{getTriggerLabel(auto.trigger_event)}</span>
                </div>
                <div className="flex items-center gap-1.5 text-slate-600 dark:text-slate-300">
                  <span className="text-[10px] font-bold text-slate-400 uppercase">ALORS:</span>
                  <span className="font-medium">{getActionLabel(auto.action_type)}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* NEW AUTOMATION MODAL */}
      {isNewModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="w-full max-w-md bg-white dark:bg-[#0B0F19] rounded-2xl border border-slate-200 dark:border-slate-800 shadow-2xl p-6">
            <div className="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-slate-800 mb-4">
              <h3 className="text-base font-bold text-slate-900 dark:text-white">
                Nouvelle règle d'automatisation
              </h3>
              <button
                onClick={() => setIsNewModalOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreate} className="space-y-3.5 text-xs">
              <div>
                <label className="text-slate-600 dark:text-slate-400 block mb-1 font-medium">
                  Nom du scénario *
                </label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Ex: Confirmation de RDV par courriel"
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                />
              </div>

              <div>
                <label className="text-slate-600 dark:text-slate-400 block mb-1 font-medium">
                  Événement déclencheur (QUAND)
                </label>
                <select
                  value={triggerEvent}
                  onChange={(e) => setTriggerEvent(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                >
                  <option value="appointment_created">Nouveau rendez-vous planifié</option>
                  <option value="appointment_approaching">24h avant le rendez-vous</option>
                  <option value="appointment_cancelled">Rendez-vous annulé</option>
                  <option value="client_inactive_30d">Client inactif (30 jours sans RDV)</option>
                  <option value="new_lead">Nouveau prospect entrant</option>
                  <option value="pipeline_stage_changed">Opportunité change de phase</option>
                </select>
              </div>

              <div>
                <label className="text-slate-600 dark:text-slate-400 block mb-1 font-medium">
                  Action exécutée (ALORS)
                </label>
                <select
                  value={actionType}
                  onChange={(e) => setActionType(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                >
                  <option value="send_email">Envoyer un courriel de confirmation</option>
                  <option value="send_sms">Envoyer un SMS automatique</option>
                  <option value="create_reminder">Créer une tâche / rappel pour l'employé</option>
                  <option value="generate_ai_task">Créer une analyse de préparation IA</option>
                </select>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-200 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsNewModalOpen(false)}
                  className="px-4 py-2 text-slate-600 dark:text-slate-400 font-medium hover:text-slate-900 dark:hover:text-white"
                >
                  Annuler
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-5 py-2 rounded-xl bg-gradient-to-r from-[#0076FF] to-[#00D4FF] text-white font-medium shadow-md hover:opacity-90 disabled:opacity-50"
                >
                  {isSubmitting ? "Création..." : "Enregistrer la règle"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
