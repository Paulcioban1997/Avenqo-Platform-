"use client";

import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/shell/app-shell";
import { apiFetch, ApiRequestError } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";
import { useSession } from "@/lib/session-context";
import {
  Zap,
  Plus,
  Play,
  Trash2,
  CheckCircle,
  AlertCircle,
  History,
  X,
  Sparkles,
  RefreshCw,
  Clock,
  ArrowRight,
  Sliders,
  Check,
  Power,
  Lock,
} from "lucide-react";

type Workflow = {
  id: string;
  name: string;
  trigger_type: string;
  action_type: string;
  is_enabled: boolean;
  last_status: string | null;
};

type RunHistoryItem = {
  id: string;
  status: string;
  detail: string;
  created_at: string | null;
};

const TRIGGER_OPTIONS = [
  {
    id: "manual",
    labelFr: "Manuel / Sur demande",
    labelEn: "Manual / On Demand",
    descFr: "Déclenché manuellement ou par Central AI",
    descEn: "Triggered manually or via Central AI",
  },
  {
    id: "document_uploaded",
    labelFr: "Document téléversé (OCR)",
    labelEn: "Document Uploaded (OCR)",
    descFr: "Lorsqu'une facture ou un contrat est importé",
    descEn: "When an invoice or contract is uploaded",
  },
  {
    id: "voice_appointment",
    labelFr: "Rendez-vous Voice AI",
    labelEn: "Voice AI Appointment",
    descFr: "Lorsqu'un appel téléphonique confirme un créneau",
    descEn: "When a telephone call confirms a slot",
  },
  {
    id: "shopify_order",
    labelFr: "Commande Shopify",
    labelEn: "Shopify Order",
    descFr: "Lors d'une nouvelle vente ou mise à jour commande",
    descEn: "On new sale or order update",
  },
  {
    id: "task_overdue",
    labelFr: "Tâche d'équipe en retard",
    labelEn: "Overdue Team Task",
    descFr: "Dès qu'une échéance employé est dépassée",
    descEn: "Whenever an employee deadline is passed",
  },
];

const ACTION_OPTIONS = [
  {
    id: "create_task",
    labelFr: "Créer une tâche d'équipe",
    labelEn: "Create Team Task",
    descFr: "Génère une action assignée avec priorité dans Équipe",
    descEn: "Generates an assigned task in Team module",
  },
  {
    id: "notify_owner",
    labelFr: "Notifier le responsable",
    labelEn: "Notify Business Owner",
    descFr: "Envoie une notification interne prioritaire",
    descEn: "Sends a high-priority internal notification",
  },
];

export default function AutomationsPage() {
  const { locale } = useLocale();
  const fr = locale.startsWith("fr");
  const { identity } = useSession();

  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [isInactive, setIsInactive] = useState(false);
  const [activating, setActivating] = useState(false);

  // Workflow Builder Modal State
  const [isBuilderOpen, setIsBuilderOpen] = useState(false);
  const [builderName, setBuilderName] = useState("");
  const [builderTrigger, setBuilderTrigger] = useState("manual");
  const [builderAction, setBuilderAction] = useState("create_task");
  const [taskTitle, setTaskTitle] = useState("");
  const [taskPriority, setTaskPriority] = useState("medium");
  const [saving, setSaving] = useState(false);

  // Run feedback
  const [runningId, setRunningId] = useState<string | null>(null);
  const [runNotice, setRunNotice] = useState<{ id: string; message: string; ok: boolean } | null>(null);

  // History Drawer State
  const [historyWorkflow, setHistoryWorkflow] = useState<Workflow | null>(null);
  const [historyRuns, setHistoryRuns] = useState<RunHistoryItem[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await apiFetch("/api/v1/automations");
      const data = await response.json();
      setWorkflows(Array.isArray(data) ? data : []);
      setError("");
      setIsInactive(false);
    } catch (err) {
      if (err instanceof ApiRequestError) {
        if (err.status === 403 || err.category === "unauthorized") {
          setIsInactive(true);
          setError("");
          return;
        }
        setError(err.publicMessage || (fr ? "Erreur de chargement." : "Load error."));
      } else {
        setError(fr ? "Erreur de connexion au serveur." : "Server connection error.");
      }
    } finally {
      setLoading(false);
    }
  }, [fr]);

  useEffect(() => {
    void load();
  }, [load]);

  const activateModule = async () => {
    setActivating(true);
    setError("");
    try {
      const response = await apiFetch("/api/v1/modules/workflow/activate", {
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
        setError(err.publicMessage || (fr ? "Impossible d'activer le module." : "Unable to activate module."));
      }
    } finally {
      setActivating(false);
    }
  };

  const handleCreateWorkflow = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!builderName.trim()) return;
    setSaving(true);
    setError("");

    const actionPayload =
      builderAction === "create_task"
        ? {
            title: taskTitle.trim() || builderName.trim(),
            priority: taskPriority,
            assignee_user_id: identity?.user?.id || undefined,
          }
        : {
            title: builderName.trim(),
          };

    try {
      const response = await apiFetch("/api/v1/automations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: builderName.trim(),
          trigger_type: builderTrigger,
          action_type: builderAction,
          condition: {},
          action: actionPayload,
        }),
      });
      if (response.ok) {
        setIsBuilderOpen(false);
        setBuilderName("");
        setTaskTitle("");
        await load();
      }
    } catch (err) {
      if (err instanceof ApiRequestError) {
        setError(err.publicMessage || (fr ? "Création refusée." : "Creation rejected."));
      } else {
        setError(fr ? "Erreur lors de la création." : "Error creating automation.");
      }
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = async (id: string) => {
    try {
      const response = await apiFetch(`/api/v1/automations/${id}/toggle`, {
        method: "PATCH",
      });
      if (response.ok) {
        const updated = await response.json();
        setWorkflows((prev) =>
          prev.map((w) => (w.id === id ? { ...w, is_enabled: updated.is_enabled } : w))
        );
      }
    } catch {
      setError(fr ? "Impossible de modifier l'état." : "Unable to toggle automation.");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm(fr ? "Supprimer cette automatisation ?" : "Delete this automation?")) return;
    try {
      const response = await apiFetch(`/api/v1/automations/${id}`, {
        method: "DELETE",
      });
      if (response.ok || response.status === 204) {
        setWorkflows((prev) => prev.filter((w) => w.id !== id));
      }
    } catch {
      setError(fr ? "Suppression impossible." : "Failed to delete.");
    }
  };

  const handleRun = async (workflow: Workflow) => {
    setRunningId(workflow.id);
    setRunNotice(null);
    try {
      const response = await apiFetch(`/api/v1/automations/${workflow.id}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          idempotency_key: `${workflow.id}-${Date.now()}`,
          payload: {},
        }),
      });
      if (response.ok) {
        const data = await response.json();
        setRunNotice({
          id: workflow.id,
          message: data.detail || (fr ? "Exécution réussie" : "Execution successful"),
          ok: true,
        });
        await load();
      }
    } catch (err) {
      setRunNotice({
        id: workflow.id,
        message:
          err instanceof ApiRequestError
            ? err.publicMessage || (fr ? "Échec d'exécution" : "Run failed")
            : fr
            ? "Erreur d'exécution"
            : "Execution error",
        ok: false,
      });
    } finally {
      setRunningId(null);
    }
  };

  const handleViewHistory = async (workflow: Workflow) => {
    setHistoryWorkflow(workflow);
    setLoadingHistory(true);
    try {
      const response = await apiFetch(`/api/v1/automations/${workflow.id}/history`);
      if (response.ok) {
        const data = await response.json();
        setHistoryRuns(Array.isArray(data) ? data : []);
      }
    } catch {
      setHistoryRuns([]);
    } finally {
      setLoadingHistory(false);
    }
  };

  return (
    <AppShell>
      <div className="mx-auto max-w-5xl space-y-6 animate-in fade-in duration-300">
        {/* HEADER */}
        <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-slate-200 dark:border-slate-800">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-widest text-[#0076FF] dark:text-[#00D4FF]">
                Avenqo Automations
              </span>
              <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300 font-medium">
                Workflow Engine
              </span>
            </div>
            <h1 className="mt-1 text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">
              {fr ? "Moteur d'Automatisations" : "Workflow Automations"}
            </h1>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              {fr
                ? "Connectez vos déclencheurs CRM, Retail, OCR et Voice à des actions réelles."
                : "Connect CRM, Retail, OCR, and Voice triggers to real business actions."}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => void load()}
              disabled={loading}
              className="p-2.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 hover:bg-slate-50 transition"
              title={fr ? "Actualiser" : "Refresh"}
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            </button>
            <button
              id="create-automation-button"
              onClick={() => setIsBuilderOpen(true)}
              disabled={isInactive}
              className="flex items-center gap-2 px-4 py-2.5 text-xs font-bold rounded-xl bg-gradient-to-r from-[#0076FF] to-[#00D4FF] text-white shadow-md hover:shadow-lg transition"
            >
              <Plus className="w-4 h-4" />
              <span>{fr ? "Créer une automatisation" : "Create Automation"}</span>
            </button>
          </div>
        </header>

        {/* INACTIVE CALLOUT */}
        {isInactive && (
          <div className="rounded-2xl border border-amber-300/80 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-700/60 p-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2 text-amber-900 dark:text-amber-200 font-bold">
                <Lock className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0" />
                <span>{fr ? "Module Workflow non activé" : "Workflow Module Inactive"}</span>
              </div>
              <p className="text-sm text-amber-800 dark:text-amber-300">
                {fr
                  ? "Activez le moteur d'automatisation pour créer des flux entre modules."
                  : "Activate the workflow automation engine to build cross-module flows."}
              </p>
            </div>
            <button
              onClick={() => void activateModule()}
              disabled={activating}
              className="shrink-0 flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-cyan-500 text-white font-bold text-xs shadow-md hover:shadow-lg transition"
            >
              {activating ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              <span>{fr ? "Activer Workflow maintenant" : "Activate Workflow Now"}</span>
            </button>
          </div>
        )}

        {error && (
          <div role="alert" className="flex items-center gap-2.5 p-4 rounded-xl border border-rose-200 bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 text-sm">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* WORKFLOWS LIST */}
        <div className="space-y-3">
          {workflows.length === 0 && !loading && !isInactive && (
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 p-12 text-center text-slate-500 dark:text-slate-400 bg-white dark:bg-[#0B132B]">
              <Zap className="w-10 h-10 mx-auto text-[#0076FF] mb-3 opacity-60" />
              <p className="text-sm font-semibold">{fr ? "Aucune automatisation configurée." : "No automations configured."}</p>
              <p className="text-xs mt-1 text-slate-400">
                {fr ? "Cliquez sur 'Créer une automatisation' pour automatiser vos tâches." : "Click 'Create Automation' to automate your tasks."}
              </p>
            </div>
          )}

          {workflows.map((wf) => {
            const triggerInfo = TRIGGER_OPTIONS.find((t) => t.id === wf.trigger_type);
            const actionInfo = ACTION_OPTIONS.find((a) => a.id === wf.action_type);

            return (
              <div
                key={wf.id}
                className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B132B] p-5 shadow-xs transition hover:border-slate-300 dark:hover:border-slate-700"
              >
                <div className="space-y-2 min-w-0 flex-1">
                  <div className="flex items-center gap-2.5">
                    <button
                      onClick={() => void handleToggle(wf.id)}
                      className={`p-1.5 rounded-lg border transition ${
                        wf.is_enabled
                          ? "bg-emerald-50 dark:bg-emerald-950/50 border-emerald-300 dark:border-emerald-700 text-emerald-600 dark:text-emerald-400"
                          : "bg-slate-100 dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-400"
                      }`}
                      title={wf.is_enabled ? (fr ? "Actif (cliquez pour désactiver)" : "Active (click to disable)") : (fr ? "Inactif (cliquez pour activer)" : "Inactive (click to enable)")}
                    >
                      <Power className="w-3.5 h-3.5" />
                    </button>
                    <h3 className="font-bold text-slate-900 dark:text-white text-base truncate">
                      {wf.name}
                    </h3>
                  </div>

                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <span className="px-2.5 py-1 rounded-lg bg-blue-50 dark:bg-blue-950/60 text-[#0076FF] dark:text-[#00D4FF] font-semibold border border-blue-200/50 dark:border-blue-900/50">
                      {fr ? triggerInfo?.labelFr || wf.trigger_type : triggerInfo?.labelEn || wf.trigger_type}
                    </span>
                    <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
                    <span className="px-2.5 py-1 rounded-lg bg-purple-50 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300 font-semibold border border-purple-200/50 dark:border-purple-900/50">
                      {fr ? actionInfo?.labelFr || wf.action_type : actionInfo?.labelEn || wf.action_type}
                    </span>

                    {wf.last_status && (
                      <span
                        className={`px-2 py-0.5 rounded-md font-mono text-[10px] ${
                          wf.last_status === "completed"
                            ? "bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300"
                            : wf.last_status === "skipped"
                            ? "bg-amber-100 dark:bg-amber-950 text-amber-700 dark:text-amber-300"
                            : "bg-rose-100 dark:bg-rose-950 text-rose-700 dark:text-rose-300"
                        }`}
                      >
                        {wf.last_status}
                      </span>
                    )}
                  </div>

                  {runNotice && runNotice.id === wf.id && (
                    <p className={`text-xs font-semibold ${runNotice.ok ? "text-emerald-600" : "text-rose-600"}`}>
                      {runNotice.message}
                    </p>
                  )}
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => void handleRun(wf)}
                    disabled={runningId === wf.id || !wf.is_enabled}
                    className="flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 hover:bg-slate-50 disabled:opacity-50 transition"
                    title={fr ? "Exécuter un test sécurisé" : "Run a safe test"}
                  >
                    <Play className={`w-3.5 h-3.5 ${runningId === wf.id ? "animate-spin" : ""}`} />
                    <span>{fr ? "Tester" : "Test"}</span>
                  </button>

                  <button
                    onClick={() => void handleViewHistory(wf)}
                    className="p-2 text-slate-500 hover:text-slate-900 dark:hover:text-white rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 transition"
                    title={fr ? "Historique d'exécution" : "Execution History"}
                  >
                    <History className="w-4 h-4" />
                  </button>

                  <button
                    onClick={() => void handleDelete(wf.id)}
                    className="p-2 text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/40 rounded-xl transition"
                    title={fr ? "Supprimer" : "Delete"}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>

        {/* WORKFLOW BUILDER MODAL */}
        {isBuilderOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-200">
            <div className="w-full max-w-xl rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B132B] shadow-2xl p-6 sm:p-7 space-y-6">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800">
                <div className="flex items-center gap-2.5">
                  <div className="p-2.5 rounded-xl bg-gradient-to-br from-[#0076FF] to-[#00D4FF] text-white">
                    <Zap className="w-5 h-5" />
                  </div>
                  <h2 className="text-xl font-extrabold text-slate-900 dark:text-white">
                    {fr ? "Créer une automatisation" : "Create Automation"}
                  </h2>
                </div>
                <button
                  onClick={() => setIsBuilderOpen(false)}
                  className="p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 transition"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <form onSubmit={handleCreateWorkflow} className="space-y-5">
                {/* NAME */}
                <div>
                  <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-2">
                    {fr ? "Nom de l'automatisation" : "Automation Name"}
                  </label>
                  <input
                    type="text"
                    required
                    value={builderName}
                    onChange={(e) => setBuilderName(e.target.value)}
                    placeholder={fr ? "ex: Créer une tâche lors d'un nouveau contrat OCR" : "e.g. Create task on new OCR contract"}
                    className="w-full px-4 py-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:outline-hidden focus:ring-2 focus:ring-[#0076FF]"
                  />
                </div>

                {/* TRIGGER SELECTOR */}
                <div>
                  <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-2">
                    {fr ? "1. Choisir le déclencheur (Trigger)" : "1. Choose Trigger"}
                  </label>
                  <div className="space-y-2">
                    {TRIGGER_OPTIONS.map((opt) => (
                      <div
                        key={opt.id}
                        onClick={() => setBuilderTrigger(opt.id)}
                        className={`p-3 rounded-xl border cursor-pointer transition flex items-center justify-between ${
                          builderTrigger === opt.id
                            ? "border-[#0076FF] bg-blue-50/50 dark:bg-blue-950/30"
                            : "border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700"
                        }`}
                      >
                        <div>
                          <p className="font-bold text-sm text-slate-900 dark:text-white">
                            {fr ? opt.labelFr : opt.labelEn}
                          </p>
                          <p className="text-xs text-slate-500 dark:text-slate-400">
                            {fr ? opt.descFr : opt.descEn}
                          </p>
                        </div>
                        {builderTrigger === opt.id && <Check className="w-4 h-4 text-[#0076FF]" />}
                      </div>
                    ))}
                  </div>
                </div>

                {/* ACTION SELECTOR */}
                <div>
                  <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-2">
                    {fr ? "2. Choisir l'action exécutée" : "2. Choose Action"}
                  </label>
                  <div className="space-y-2">
                    {ACTION_OPTIONS.map((opt) => (
                      <div
                        key={opt.id}
                        onClick={() => setBuilderAction(opt.id)}
                        className={`p-3 rounded-xl border cursor-pointer transition flex items-center justify-between ${
                          builderAction === opt.id
                            ? "border-purple-500 bg-purple-50/50 dark:bg-purple-950/30"
                            : "border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700"
                        }`}
                      >
                        <div>
                          <p className="font-bold text-sm text-slate-900 dark:text-white">
                            {fr ? opt.labelFr : opt.labelEn}
                          </p>
                          <p className="text-xs text-slate-500 dark:text-slate-400">
                            {fr ? opt.descFr : opt.descEn}
                          </p>
                        </div>
                        {builderAction === opt.id && <Check className="w-4 h-4 text-purple-600" />}
                      </div>
                    ))}
                  </div>
                </div>

                {/* PRIORITY IF TASK */}
                {builderAction === "create_task" && (
                  <div>
                    <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-2">
                      {fr ? "Priorité de la tâche générée" : "Task Priority"}
                    </label>
                    <select
                      value={taskPriority}
                      onChange={(e) => setTaskPriority(e.target.value)}
                      className="w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm"
                    >
                      <option value="low">{fr ? "Basse" : "Low"}</option>
                      <option value="medium">{fr ? "Moyenne" : "Medium"}</option>
                      <option value="high">{fr ? "Haute / Urgente" : "High / Urgent"}</option>
                    </select>
                  </div>
                )}

                <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-100 dark:border-slate-800">
                  <button
                    type="button"
                    onClick={() => setIsBuilderOpen(false)}
                    className="px-4 py-2.5 text-xs font-semibold rounded-xl text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
                  >
                    {fr ? "Annuler" : "Cancel"}
                  </button>
                  <button
                    type="submit"
                    disabled={saving}
                    className="flex items-center gap-2 px-6 py-2.5 text-xs font-bold rounded-xl bg-gradient-to-r from-[#0076FF] to-[#00D4FF] text-white shadow-md hover:shadow-lg transition"
                  >
                    {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
                    <span>{fr ? "Enregistrer l'automatisation" : "Save Automation"}</span>
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* HISTORY DRAWER / MODAL */}
        {historyWorkflow && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-200">
            <div className="w-full max-w-lg rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B132B] shadow-2xl p-6 space-y-4 max-h-[85vh] flex flex-col">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800">
                <div>
                  <h3 className="font-bold text-slate-900 dark:text-white text-base">
                    {fr ? "Historique d'exécution" : "Execution History"}
                  </h3>
                  <p className="text-xs text-slate-500">{historyWorkflow.name}</p>
                </div>
                <button
                  onClick={() => setHistoryWorkflow(null)}
                  className="p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="flex-1 overflow-auto space-y-3">
                {loadingHistory && (
                  <div className="p-8 text-center text-sm text-slate-400">
                    <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-[#0076FF]" />
                    {fr ? "Chargement des exécutions..." : "Loading executions..."}
                  </div>
                )}

                {!loadingHistory && historyRuns.length === 0 && (
                  <p className="p-8 text-center text-sm text-slate-400">
                    {fr ? "Aucune exécution enregistrée pour ce flux." : "No executions logged for this workflow."}
                  </p>
                )}

                {historyRuns.map((run) => (
                  <div
                    key={run.id}
                    className="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50 text-xs space-y-1"
                  >
                    <div className="flex items-center justify-between font-mono">
                      <span
                        className={`font-bold ${
                          run.status === "completed"
                            ? "text-emerald-600"
                            : run.status === "skipped"
                            ? "text-amber-600"
                            : "text-rose-600"
                        }`}
                      >
                        {run.status.toUpperCase()}
                      </span>
                      <span className="text-slate-400">
                        {run.created_at ? new Date(run.created_at).toLocaleString(fr ? "fr-CA" : "en-US") : ""}
                      </span>
                    </div>
                    <p className="text-slate-700 dark:text-slate-300 font-sans">{run.detail}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
