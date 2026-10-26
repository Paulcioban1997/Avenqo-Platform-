"use client";

import { useEffect, useState } from "react";
import {
  ShieldCheck,
  ShieldAlert,
  Play,
  Pause,
  KeyRound,
  PhoneCall,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  RotateCcw,
  Sparkles,
  Lock,
  UserCheck,
  Users,
} from "lucide-react";
import { useLocale } from "@/lib/i18n/locale-context";

interface Checklist {
  tenant_valid: boolean;
  subscription_active: boolean;
  phone_bound: boolean;
  phone_number: string | null;
  voice_selected: boolean;
  language_selected: boolean;
  identity_configured: boolean;
  ivr_configured: boolean;
  modules_configured: boolean;
  permissions_valid: boolean;
}

interface LifecycleStatus {
  status: "DRAFT" | "CONFIGURING" | "READY_FOR_TEST" | "ACTIVE" | "SUSPENDED";
  can_activate: boolean;
  checklist: Checklist;
  phone_number: string | null;
  call_policy: {
    ivr_enabled: boolean;
    ivr_greeting: string | null;
  };
  version: number;
  last_audit_action: string | null;
}

interface PinStatus {
  has_pin: boolean;
  phone_number: string | null;
  max_attempts: number;
}

interface VoiceLifecycleCardProps {
  tenantId?: string;
  canManage: boolean;
  businessName?: string;
}

export function VoiceLifecycleCard({
  tenantId,
  canManage,
  businessName = "Entreprise",
}: VoiceLifecycleCardProps) {
  const { locale } = useLocale();
  const fr = locale.startsWith("fr");

  const [lifecycle, setLifecycle] = useState<LifecycleStatus | null>(null);
  const [pinStatus, setPinStatus] = useState<PinStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [busy, setBusy] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // IVR Form state
  const [ivrEnabled, setIvrEnabled] = useState<boolean>(true);
  const [ivrGreeting, setIvrGreeting] = useState<string>("");

  // Personal PIN Form state
  const [employeePin, setEmployeePin] = useState<string>("");
  const [employeePhone, setEmployeePhone] = useState<string>("");

  async function loadStatus() {
    if (!tenantId) return;
    try {
      setLoading(true);
      setErrorMsg(null);
      const res = await fetch("/api/v1/voice/lifecycle/status", {
        cache: "no-store",
      });
      if (res.ok) {
        const data = (await res.json()) as LifecycleStatus;
        setLifecycle(data);
        setIvrEnabled(Boolean(data.call_policy?.ivr_enabled));
        setIvrGreeting(
          data.call_policy?.ivr_greeting ||
            `Bienvenue chez ${businessName}. Pour les employés, composez le 1. Pour le service clientèle, composez le 2.`
        );
      }

      const pinRes = await fetch("/api/v1/voice/auth/pin", {
        cache: "no-store",
      });
      if (pinRes.ok) {
        const pData = (await pinRes.json()) as PinStatus;
        setPinStatus(pData);
        if (pData.phone_number) setEmployeePhone(pData.phone_number);
      }
    } catch {
      setErrorMsg(
        fr
          ? "Impossible de charger le statut du cycle de vie Voice."
          : "Unable to load Voice lifecycle status."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadStatus();
  }, [tenantId]);

  async function handleActivate() {
    if (!canManage) return;
    setBusy(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const res = await fetch("/api/v1/voice/lifecycle/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reason: "Activation manuelle par administrateur",
          confirmed: true,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Activation failed");
      }
      setSuccessMsg(
        fr
          ? "Numéro vocal activé avec succès. Les appels publics sont désormais autorisés."
          : "Voice number activated successfully. Public inbound calls are now accepted."
      );
      await loadStatus();
    } catch (e: any) {
      setErrorMsg(
        e.message ||
          (fr
            ? "Erreur lors de l'activation du numéro."
            : "Error activating voice number.")
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleSuspend() {
    if (!canManage) return;
    setBusy(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const res = await fetch("/api/v1/voice/lifecycle/suspend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reason: "Suspension manuelle par administrateur",
          confirmed: true,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Suspension failed");
      }
      setSuccessMsg(
        fr
          ? "Numéro vocal suspendu en mode Fail-Closed. Aucun appel public ne sera traité."
          : "Voice number suspended in fail-closed mode. Public calls are refused."
      );
      await loadStatus();
    } catch (e: any) {
      setErrorMsg(
        e.message ||
          (fr
            ? "Erreur lors de la suspension."
            : "Error suspending voice number.")
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveIvr() {
    if (!canManage) return;
    setBusy(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const res = await fetch("/api/v1/voice/lifecycle/ivr", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ivr_enabled: ivrEnabled,
          ivr_greeting: ivrGreeting,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "IVR update failed");
      }
      setSuccessMsg(
        fr
          ? "Configuration du standard IVR enregistrée."
          : "IVR routing configuration saved."
      );
      await loadStatus();
    } catch (e: any) {
      setErrorMsg(
        e.message ||
          (fr
            ? "Erreur lors de la mise à jour du standard IVR."
            : "Error updating IVR settings.")
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleSavePin() {
    if (!employeePin || employeePin.length < 6) {
      setErrorMsg(
        fr
          ? "Le NIP personnel doit comporter entre 6 et 12 chiffres."
          : "Personal PIN must be between 6 and 12 digits."
      );
      return;
    }
    setBusy(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const res = await fetch("/api/v1/voice/auth/pin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pin: employeePin,
          phone_number: employeePhone || null,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "PIN update failed");
      }
      setSuccessMsg(
        fr
          ? "NIP personnel employé enregistré avec succès."
          : "Personal employee PIN saved successfully."
      );
      setEmployeePin("");
      await loadStatus();
    } catch (e: any) {
      setErrorMsg(
        e.message ||
          (fr
            ? "Erreur lors de la configuration du NIP."
            : "Error configuring employee PIN.")
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleRevokeSessions() {
    setBusy(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const res = await fetch("/api/v1/voice/auth/sessions/revoke", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ all_sessions: true }),
      });
      if (!res.ok) throw new Error("Revocation failed");
      setSuccessMsg(
        fr
          ? "Toutes les sessions vocales actives ont été révoquées."
          : "All active authenticated voice sessions revoked."
      );
    } catch {
      setErrorMsg(
        fr
          ? "Erreur lors de la révocation des sessions."
          : "Error revoking active sessions."
      );
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="p-6 rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B132B] animate-pulse flex items-center justify-center">
        <p className="text-xs text-slate-400 font-semibold">
          {fr
            ? "Chargement de la gouvernance vocale..."
            : "Loading Voice governance..."}
        </p>
      </div>
    );
  }

  const status = lifecycle?.status || "DRAFT";
  const statusBadge = {
    ACTIVE: {
      bg: "bg-emerald-50 dark:bg-emerald-950/70 border-emerald-300 dark:border-emerald-800",
      text: "text-emerald-700 dark:text-emerald-300",
      dot: "bg-emerald-500",
      label: fr ? "ACTIF — Appels publics autorisés" : "ACTIVE — Public calls enabled",
    },
    READY_FOR_TEST: {
      bg: "bg-amber-50 dark:bg-amber-950/70 border-amber-300 dark:border-amber-800",
      text: "text-amber-700 dark:text-amber-300",
      dot: "bg-amber-500",
      label: fr
        ? "PRÊT POUR TEST — Appels réservés aux administrateurs"
        : "READY FOR TEST — Restricted to admin test callers",
    },
    CONFIGURING: {
      bg: "bg-blue-50 dark:bg-blue-950/70 border-blue-300 dark:border-blue-800",
      text: "text-blue-700 dark:text-blue-300",
      dot: "bg-blue-500",
      label: fr ? "EN CONFIGURATION — Non activé" : "CONFIGURING — Not active",
    },
    SUSPENDED: {
      bg: "bg-rose-50 dark:bg-rose-950/70 border-rose-300 dark:border-rose-800",
      text: "text-rose-700 dark:text-rose-300",
      dot: "bg-rose-500",
      label: fr ? "SUSPENDU — Fail-closed" : "SUSPENDED — Fail-closed",
    },
    DRAFT: {
      bg: "bg-slate-50 dark:bg-slate-900 border-slate-300 dark:border-slate-800",
      text: "text-slate-700 dark:text-slate-300",
      dot: "bg-slate-400",
      label: fr ? "BROUILLON" : "DRAFT",
    },
  }[status];

  return (
    <div className="space-y-6">
      {/* 1. LIFECYCLE & ACTIVATION BANNER */}
      <div className="p-6 sm:p-7 rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B132B] shadow-sm space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-[#0076FF] dark:text-[#00D4FF]">
                {fr ? "Cycle de Vie & Sécurité Fail-Closed" : "Lifecycle & Fail-Closed Security"}
              </span>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500 font-mono font-bold">
                v{lifecycle?.version || 1}
              </span>
            </div>
            <h2 className="text-xl font-extrabold text-slate-900 dark:text-white mt-1">
              {fr ? "Activation & Statut du Numéro Dédié" : "Activation & Dedicated Number Status"}
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              {fr
                ? "Principe absolu : un numéro réservé ne répond JAMAIS aux appels publics tant qu'il n'est pas expressément activé par un administrateur."
                : "Fail-closed rule: a reserved phone number NEVER answers public calls until explicitly activated by a tenant administrator."}
            </p>
          </div>

          {/* STATUS PILL */}
          <div
            className={`px-4 py-2 rounded-2xl border flex items-center gap-2.5 ${statusBadge.bg} ${statusBadge.text}`}
          >
            <span className={`w-2.5 h-2.5 rounded-full ${statusBadge.dot} animate-pulse`} />
            <span className="text-xs font-black tracking-wide">{statusBadge.label}</span>
          </div>
        </div>

        {/* FEEDBACK NOTICES */}
        {errorMsg && (
          <div className="p-3.5 rounded-xl bg-red-50 dark:bg-red-950/60 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-xs flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 text-red-600" />
            <span>{errorMsg}</span>
          </div>
        )}
        {successMsg && (
          <div className="p-3.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 text-xs flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600" />
            <span>{successMsg}</span>
          </div>
        )}

        {/* PRE-FLIGHT READINESS CHECKLIST */}
        <div className="p-4 rounded-2xl bg-slate-50/70 dark:bg-slate-900/50 border border-slate-200/80 dark:border-slate-800 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider">
              {fr ? "Contrôles préalables à l'activation (Fail-Closed Checklist)" : "Pre-flight Activation Checklist"}
            </span>
            <span className="text-[11px] font-mono text-slate-500">
              {lifecycle?.phone_number ? lifecycle.phone_number : (fr ? "Aucun numéro lié" : "No number bound")}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2 text-xs">
            {[
              { key: "tenant_valid", label: fr ? "Tenant valide" : "Valid Tenant" },
              { key: "subscription_active", label: fr ? "Abonnement Voice actif" : "Active Subscription" },
              { key: "phone_bound", label: fr ? "Numéro Telnyx lié" : "Telnyx Number Bound" },
              { key: "identity_configured", label: fr ? "Identité & secteur définis" : "Identity Configured" },
              { key: "voice_selected", label: fr ? "Voix & timbre choisis" : "Voice Selected" },
              { key: "language_selected", label: fr ? "Langues configurées" : "Languages Selected" },
              { key: "ivr_configured", label: fr ? "Standard IVR configuré" : "IVR Configured" },
              { key: "modules_configured", label: fr ? "Modules autorisés" : "Modules Configured" },
              { key: "permissions_valid", label: fr ? "Permissions publiques/privées" : "Permissions Valid" },
            ].map((item) => {
              const ok = lifecycle?.checklist?.[item.key as keyof Checklist] ?? false;
              return (
                <div
                  key={item.key}
                  className={`p-2 rounded-xl border flex items-center gap-2 ${
                    ok
                      ? "bg-emerald-50/50 dark:bg-emerald-950/20 border-emerald-200/60 dark:border-emerald-900/40 text-emerald-800 dark:text-emerald-300"
                      : "bg-slate-100/50 dark:bg-slate-800/40 border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400"
                  }`}
                >
                  {ok ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                  ) : (
                    <XCircle className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                  )}
                  <span className="font-medium text-[11px] truncate">{item.label}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* ACTIVATION ACTION BUTTONS */}
        <div className="flex items-center justify-between gap-3 pt-2 border-t border-slate-100 dark:border-slate-800 flex-wrap">
          <div className="text-xs text-slate-500">
            {lifecycle?.can_activate
              ? fr
                ? "Toutes les vérifications sont validées. Vous pouvez activer les appels publics."
                : "All checks passed. You may activate public voice calls."
              : fr
              ? "Complétez la configuration requise pour débloquer l'activation publique."
              : "Complete required configuration to unlock public activation."}
          </div>

          <div className="flex items-center gap-2">
            {status === "ACTIVE" ? (
              <button
                onClick={handleSuspend}
                disabled={busy || !canManage}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-rose-50 hover:bg-rose-100 dark:bg-rose-950/60 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 font-bold text-xs transition disabled:opacity-50"
              >
                <Pause className="w-3.5 h-3.5" />
                <span>{fr ? "Suspendre l'agent vocal" : "Suspend Voice Agent"}</span>
              </button>
            ) : (
              <button
                onClick={handleActivate}
                disabled={busy || !lifecycle?.can_activate || !canManage}
                className="flex items-center gap-1.5 px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-extrabold text-xs shadow-md transition disabled:opacity-50"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>{fr ? "Activer l'agent vocal pour le public" : "Activate Voice Agent for Public"}</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* 2. IVR ROUTING CONFIGURATION (KEY 1 & KEY 2) */}
      <div className="p-6 sm:p-7 rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B132B] shadow-sm space-y-5">
        <div>
          <span className="text-[11px] font-bold uppercase tracking-wider text-[#0076FF] dark:text-[#00D4FF]">
            {fr ? "Routage Téléphonique & Menu Vocal" : "Telephony Routing & IVR Menu"}
          </span>
          <h3 className="text-lg font-extrabold text-slate-900 dark:text-white mt-1">
            {fr ? "Menu d'accueil interactif (1 Employés / 2 Clients)" : "Interactive IVR Menu (1 Staff / 2 Customers)"}
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            {fr
              ? "Sépare de façon hermétique les accès du service client public des requêtes internes de vos employés."
              : "Strictly isolates public customer queries from internal authenticated employee workflows."}
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* TOUCH 1 CARD */}
          <div className="p-4 rounded-2xl border border-purple-200/80 dark:border-purple-900/40 bg-purple-50/40 dark:bg-purple-950/20 space-y-2">
            <div className="flex items-center gap-2">
              <span className="w-6 h-6 rounded-lg bg-purple-600 text-white font-black text-xs flex items-center justify-center">
                1
              </span>
              <span className="font-bold text-sm text-purple-900 dark:text-purple-200">
                {fr ? "Touche 1 — Espace Employés" : "Key 1 — Employee Portal"}
              </span>
            </div>
            <ul className="text-xs text-purple-950/80 dark:text-purple-300/80 space-y-1 list-disc list-inside">
              <li>{fr ? "NIP personnel 6 chiffres requis" : "Requires personal 6-digit PIN"}</li>
              <li>{fr ? "Accès aux outils internes et CRM privé" : "Access to authorized internal CRM tools"}</li>
              <li>{fr ? "Protection anti brute-force côté serveur" : "Server-side brute-force lockout"}</li>
              <li>{fr ? "Révocation automatique en fin d'appel" : "Session auto-revoked on hangup"}</li>
            </ul>
          </div>

          {/* TOUCH 2 CARD */}
          <div className="p-4 rounded-2xl border border-blue-200/80 dark:border-blue-900/40 bg-blue-50/40 dark:bg-blue-950/20 space-y-2">
            <div className="flex items-center gap-2">
              <span className="w-6 h-6 rounded-lg bg-[#0076FF] text-white font-black text-xs flex items-center justify-center">
                2
              </span>
              <span className="font-bold text-sm text-blue-900 dark:text-blue-200">
                {fr ? "Touche 2 — Service Clientèle" : "Key 2 — Customer Reception"}
              </span>
            </div>
            <ul className="text-xs text-blue-950/80 dark:text-blue-300/80 space-y-1 list-disc list-inside">
              <li>{fr ? "Aucun NIP requis (accès direct)" : "Zero PIN required (direct access)"}</li>
              <li>{fr ? "Catalogue, disponibilités et réservations" : "Catalog, availability, bookings"}</li>
              <li>{fr ? "Isolation stricte : zéro donnée confidentielle" : "Zero access to confidential data"}</li>
              <li>{fr ? "Conversation naturelle sans vente forcée" : "Natural conversational grounding"}</li>
            </ul>
          </div>
        </div>

        {/* IVR GREETING TEXT INPUT */}
        <div className="space-y-2 pt-2">
          <label className="text-xs font-bold text-slate-700 dark:text-slate-300 flex items-center justify-between">
            <span>{fr ? "Message vocal d'accueil du standard :" : "IVR Welcome Spoken Greeting:"}</span>
            <span className="text-[10px] text-slate-400 font-normal">
              {fr ? "Prononcé avec la voix et langue choisies" : "Spoken with chosen voice & accent"}
            </span>
          </label>
          <textarea
            rows={2}
            value={ivrGreeting}
            onChange={(e) => setIvrGreeting(e.target.value)}
            disabled={!canManage}
            className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs font-medium text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-hidden focus:border-[#0076FF]"
          />
        </div>

        <div className="flex items-center justify-between pt-2 border-t border-slate-100 dark:border-slate-800">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={ivrEnabled}
              onChange={(e) => setIvrEnabled(e.target.checked)}
              disabled={!canManage}
              className="w-4 h-4 rounded text-[#0076FF] focus:ring-0"
            />
            <span className="text-xs font-bold text-slate-800 dark:text-slate-200">
              {fr ? "Activer le menu interactif (1 Employés / 2 Clients)" : "Enable interactive IVR menu"}
            </span>
          </label>

          <button
            onClick={handleSaveIvr}
            disabled={busy || !canManage}
            className="px-4 py-2 rounded-xl bg-slate-900 hover:bg-black dark:bg-white dark:hover:bg-slate-200 text-white dark:text-slate-900 font-bold text-xs transition disabled:opacity-50"
          >
            {fr ? "Enregistrer le menu IVR" : "Save IVR Settings"}
          </button>
        </div>
      </div>

      {/* 3. PERSONAL EMPLOYEE PIN CONFIGURATION */}
      <div className="p-6 sm:p-7 rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B132B] shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-[11px] font-bold uppercase tracking-wider text-purple-600 dark:text-purple-400">
              {fr ? "Sécurité Téléphonique des Collaborateurs" : "Employee Phone Security"}
            </span>
            <h3 className="text-lg font-extrabold text-slate-900 dark:text-white mt-0.5">
              {fr ? "Mon NIP Personnel Employé" : "My Personal Employee PIN"}
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              {fr
                ? "Chaque employé doit définir son propre NIP confidentiel (6 à 12 chiffres) pour déverrouiller ses outils par téléphone via la Touche 1."
                : "Each employee sets their own secret 6-12 digit PIN to unlock internal tools via Key 1."}
            </p>
          </div>

          <div className="px-3 py-1 rounded-xl bg-purple-50 dark:bg-purple-950/60 border border-purple-200 dark:border-purple-800 text-purple-700 dark:text-purple-300 text-xs font-bold flex items-center gap-1.5">
            <Lock className="w-3.5 h-3.5" />
            <span>{pinStatus?.has_pin ? (fr ? "NIP Configuré" : "PIN Set") : (fr ? "Aucun NIP" : "No PIN")}</span>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
          <div>
            <label className="text-xs font-bold text-slate-700 dark:text-slate-300 block mb-1">
              {fr ? "NIP personnel (6 à 12 chiffres) :" : "Personal PIN (6-12 digits):"}
            </label>
            <input
              type="password"
              inputMode="numeric"
              pattern="[0-9]*"
              maxLength={12}
              placeholder="Ex: 849201"
              value={employeePin}
              onChange={(e) => setEmployeePin(e.target.value.replace(/\D/g, ""))}
              className="w-full px-3.5 py-2 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs font-mono font-bold text-slate-900 dark:text-white focus:outline-hidden focus:border-purple-500"
            />
          </div>

          <div>
            <label className="text-xs font-bold text-slate-700 dark:text-slate-300 block mb-1">
              {fr ? "Numéro de mobile autorisé (E.164) :" : "Authorized Phone Number (E.164):"}
            </label>
            <input
              type="tel"
              placeholder="+15141234567"
              value={employeePhone}
              onChange={(e) => setEmployeePhone(e.target.value)}
              className="w-full px-3.5 py-2 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs font-mono font-bold text-slate-900 dark:text-white focus:outline-hidden focus:border-purple-500"
            />
          </div>
        </div>

        <div className="flex items-center justify-between pt-2 border-t border-slate-100 dark:border-slate-800 flex-wrap gap-2">
          <button
            onClick={handleRevokeSessions}
            disabled={busy}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 text-xs font-semibold transition"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>{fr ? "Révoquer mes sessions actives" : "Revoke Active Sessions"}</span>
          </button>

          <button
            onClick={handleSavePin}
            disabled={busy || employeePin.length < 6}
            className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-700 text-white font-bold text-xs shadow-md transition disabled:opacity-50"
          >
            {fr ? "Enregistrer mon NIP" : "Save My PIN"}
          </button>
        </div>
      </div>
    </div>
  );
}
