"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import {
  Settings,
  Building2,
  Shield,
  Layers,
  CheckCircle2,
  AlertTriangle,
  Lock,
  CreditCard,
  RefreshCw,
  ChevronRight,
  Search,
  KeyRound,
  PhoneCall,
  History,
  UserCheck,
  UserX,
  Check,
  X,
} from "lucide-react";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
import { getApplicationCatalog } from "@/lib/i18n/generated-app-catalogs";
import { VOICE_HEALTH_COPY } from "@/lib/i18n/voice-health-copy";
import { VOICE_NUMBER_COPY } from "@/lib/i18n/voice-number-copy";

interface VoicePinStatusData {
  has_pin: boolean;
  phone_access_enabled: boolean;
  phone_number: string | null;
  is_locked: boolean;
  failed_attempts: number;
  active_sessions_count: number;
}

interface VoiceAuditLogItem {
  id: string;
  timestamp: string | null;
  action: string;
  actor_user_id: string | null;
  success: boolean;
  metadata: Record<string, any>;
}

interface VoiceMemberItem {
  user_id: string;
  first_name: string;
  last_name: string;
  email: string;
  role: string;
  phone: string | null;
  has_pin: boolean;
  phone_access_enabled: boolean;
  is_locked: boolean;
  is_active: boolean;
}

interface ModuleItem {
  key: string;
  display_name: string;
  description: string;
  availability: string;
  active: boolean;
  state: string;
  premium: boolean;
  category: string;
  credit_multiplier: number;
}

interface EntitlementsData {
  company_id: string;
  plan_code: string;
  active_modules: string[];
  module_limit: number | null;
  remaining_module_slots: number | null;
  modules: ModuleItem[];
}

interface UserProfile {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: string;
  is_platform_admin?: boolean;
}

interface OrgInfo {
  name: string;
  id: string;
  slug?: string;
  subscription_plan?: string;
}

interface VoiceSettingsStatus {
  voice_status: string;
  module_entitled: boolean;
  number_status: string;
  business_number?: string | null;
  country?: string | null;
  region?: string | null;
  locality?: string | null;
  provider?: string | null;
  telnyx_status: string;
  retell_status: string;
  stt_status: string;
  tts_status: string;
  realtime_status: string;
  crm_status: string;
  calendar_status: string;
  call_count: number;
  call_minutes: number;
  voice_ai_credits_charged: number;
  retail_source_context?: { name?: string | null; provider?: string | null };
  data_freshness?: { freshness_status?: string; last_updated_at?: string | null };
}

interface VoiceNumberOffer {
  phone_number: string;
  country_code: string;
  region?: string | null;
  locality?: string | null;
  number_type: string;
  monthly_cost: number | null;
  monthly_cost_currency: string | null;
  regulatory_requirements: string[];
}

export function SettingsView() {
  const { locale } = useLocale();
  const t = getAppTranslations(locale);
  const companyTranslations = getApplicationCatalog(locale).company;
  const connectorTranslations = companyTranslations.connectorHub;
  const voiceHealthCopy = VOICE_HEALTH_COPY[locale as keyof typeof VOICE_HEALTH_COPY] ?? VOICE_HEALTH_COPY.en;
  const voiceNumberCopy = VOICE_NUMBER_COPY[locale as keyof typeof VOICE_NUMBER_COPY] ?? VOICE_NUMBER_COPY.en;

  const [loading, setLoading] = useState(true);
  const [entitlements, setEntitlements] = useState<EntitlementsData | null>(null);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [company, setCompany] = useState<OrgInfo | null>(null);
  const [updatingKey, setUpdatingKey] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [voiceStatus, setVoiceStatus] = useState<VoiceSettingsStatus | null>(null);
  const [voiceOffers, setVoiceOffers] = useState<VoiceNumberOffer[]>([]);
  const [voiceSearch, setVoiceSearch] = useState({ countryCode: "", region: "", locality: "" });
  const [voiceNumberBusy, setVoiceNumberBusy] = useState(false);
  const [voiceNumberNeedsAction, setVoiceNumberNeedsAction] = useState(false);

  // Voice AI Security State (NIP & Access Control)
  const [pinStatus, setPinStatus] = useState<VoicePinStatusData | null>(null);
  const [pinModalOpen, setPinModalOpen] = useState(false);
  const [pinForm, setPinForm] = useState({ pin: "", confirmPin: "", currentPassword: "", phone: "" });
  const [pinFormBusy, setPinFormBusy] = useState(false);
  const [pinFormError, setPinFormError] = useState<string | null>(null);
  const [pinFormSuccess, setPinFormSuccess] = useState<string | null>(null);
  const [voiceAuditLogs, setVoiceAuditLogs] = useState<VoiceAuditLogItem[]>([]);
  const [voiceMembers, setVoiceMembers] = useState<VoiceMemberItem[]>([]);
  const [accessToggling, setAccessToggling] = useState(false);
  const [revokingSessions, setRevokingSessions] = useState(false);

  const getHeaders = useCallback(() => {
    return {
      "Content-Type": "application/json",
    };
  }, []);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const headers = getHeaders();
      const [userRes, entRes, pinRes, auditRes] = await Promise.all([
        fetch("/api/v1/auth/me", { headers }),
        fetch("/api/v1/modules/entitlements", { headers }),
        fetch("/api/v1/voice/auth/pin/status", { headers, cache: "no-store" }),
        fetch("/api/v1/voice/auth/audit", { headers, cache: "no-store" }),
      ]);

      if (userRes.ok) {
        const userData = await userRes.json();
        setUser(userData.user);
        setCompany(userData.company);
        const role = String(userData.user?.role || "").toLowerCase();
        if (role === "owner" || role === "admin") {
          const [voiceRes, membersRes] = await Promise.all([
            fetch("/api/v1/voice/status", { headers, cache: "no-store" }),
            fetch("/api/v1/voice/auth/members", { headers, cache: "no-store" }),
          ]);
          if (voiceRes.ok) setVoiceStatus(await voiceRes.json());
          else setVoiceStatus(null);
          if (membersRes.ok) {
            const memData = await membersRes.json();
            setVoiceMembers(memData.members || []);
          }
        }
      }

      if (pinRes.ok) {
        setPinStatus(await pinRes.json());
      }
      if (auditRes.ok) {
        const auditData = await auditRes.json();
        setVoiceAuditLogs(auditData.events || []);
      }

      if (entRes.ok) {
        const entData = await entRes.json();
        setEntitlements(entData);
      }
    } catch {
      setStatusMsg({
        type: "error",
        text: companyTranslations.connectionsGenericError,
      });
    } finally {
      setLoading(false);
    }
  }, [getHeaders, companyTranslations.connectionsGenericError]);

  useEffect(() => {
    let disposed = false;
    queueMicrotask(() => { if (!disposed) void fetchData(); });
    return () => { disposed = true; };
  }, [fetchData]);

  const handleToggleModule = async (mod: ModuleItem) => {
    setUpdatingKey(mod.key);
    setStatusMsg(null);
    try {
      const headers = getHeaders();
      const action = mod.active ? "deactivate" : "activate";
      const res = await fetch(`/api/v1/modules/${mod.key}/${action}`, {
        method: "POST",
        headers,
      });

      if (res.ok) {
        const updated = await res.json();
        setEntitlements(updated);
        setStatusMsg({
          type: "success",
          text: `${mod.display_name} ${mod.active ? connectorTranslations.connected : connectorTranslations.disconnected}`,
        });
      } else {
        const err = await res.json().catch(() => ({ detail: "Action impossible" }));
        setStatusMsg({
          type: "error",
          text: err.detail || companyTranslations.connectionsProcessingError,
        });
      }
    } catch {
      setStatusMsg({
        type: "error",
        text: companyTranslations.connectionsGenericError,
      });
    } finally {
      setUpdatingKey(null);
    }
  };

  const searchVoiceNumbers = async () => {
    setVoiceNumberBusy(true);
    setVoiceNumberNeedsAction(false);
    setVoiceOffers([]);
    try {
      const query = new URLSearchParams({ country_code: voiceSearch.countryCode.trim() });
      if (voiceSearch.region.trim()) query.set("region", voiceSearch.region.trim());
      if (voiceSearch.locality.trim()) query.set("locality", voiceSearch.locality.trim());
      const response = await fetch(`/api/v1/voice/numbers/search?${query}`, { headers: getHeaders(), cache: "no-store" });
      if (!response.ok) throw new Error("number_search_unavailable");
      const result = await response.json();
      setVoiceOffers(Array.isArray(result.offers) ? result.offers : []);
      setVoiceNumberNeedsAction(result.status === "READY_FOR_OWNER_ACTION");
    } catch {
      setVoiceNumberNeedsAction(true);
    } finally {
      setVoiceNumberBusy(false);
    }
  };

  const handleSavePin = async (e: React.FormEvent) => {
    e.preventDefault();
    setPinFormError(null);
    setPinFormSuccess(null);

    if (!/^\d{6}$/.test(pinForm.pin)) {
      setPinFormError("Le NIP doit contenir exactement 6 chiffres.");
      return;
    }
    if (pinForm.pin !== pinForm.confirmPin) {
      setPinFormError("Les deux saisies de NIP ne correspondent pas.");
      return;
    }
    if (pinStatus?.has_pin && !pinForm.currentPassword) {
      setPinFormError("Votre mot de passe de compte actuel est requis pour modifier votre NIP.");
      return;
    }

    setPinFormBusy(true);
    try {
      const payload: Record<string, string> = {
        pin: pinForm.pin,
        confirm_pin: pinForm.confirmPin,
      };
      if (pinForm.currentPassword) {
        payload.current_password = pinForm.currentPassword;
      }
      if (pinForm.phone) {
        payload.phone_number = pinForm.phone;
      }

      const res = await fetch("/api/v1/voice/auth/pin", {
        method: "PUT",
        headers: getHeaders(),
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Échec de configuration du NIP");
      }

      setPinFormSuccess("NIP vocal configuré et sécurisé avec succès.");
      setPinForm({ pin: "", confirmPin: "", currentPassword: "", phone: "" });
      await fetchData();
      setTimeout(() => {
        setPinModalOpen(false);
        setPinFormSuccess(null);
      }, 1500);
    } catch (err: any) {
      setPinFormError(err.message || "Erreur lors de l'enregistrement");
    } finally {
      setPinFormBusy(false);
    }
  };

  const handleTogglePhoneAccess = async () => {
    if (!pinStatus || accessToggling) return;
    setAccessToggling(true);
    try {
      const newEnabled = !pinStatus.phone_access_enabled;
      const res = await fetch("/api/v1/voice/auth/phone-access", {
        method: "PUT",
        headers: getHeaders(),
        body: JSON.stringify({ enabled: newEnabled }),
      });
      if (res.ok) {
        setPinStatus((prev) => prev ? { ...prev, phone_access_enabled: newEnabled } : null);
        setStatusMsg({
          type: "success",
          text: newEnabled ? "Accès téléphonique privé activé" : "Accès téléphonique privé désactivé",
        });
        await fetchData();
      }
    } catch {
      setStatusMsg({ type: "error", text: "Impossible de modifier la politique d'accès" });
    } finally {
      setAccessToggling(false);
    }
  };

  const handleRevokeSessions = async () => {
    if (revokingSessions) return;
    setRevokingSessions(true);
    try {
      const res = await fetch("/api/v1/voice/auth/sessions/revoke", {
        method: "POST",
        headers: getHeaders(),
      });
      if (res.ok) {
        const data = await res.json();
        setStatusMsg({
          type: "success",
          text: `${data.revoked_count} session(s) téléphonique(s) révoquée(s) immédiatement.`,
        });
        await fetchData();
      }
    } catch {
      setStatusMsg({ type: "error", text: "Erreur lors de la révocation des sessions" });
    } finally {
      setRevokingSessions(false);
    }
  };

  const handleToggleMemberAccess = async (targetUserId: string, currentEnabled: boolean) => {
    try {
      const res = await fetch(`/api/v1/voice/auth/members/${targetUserId}/access`, {
        method: "PUT",
        headers: getHeaders(),
        body: JSON.stringify({ enabled: !currentEnabled }),
      });
      if (res.ok) {
        setVoiceMembers((prev) =>
          prev.map((m) => (m.user_id === targetUserId ? { ...m, phone_access_enabled: !currentEnabled } : m))
        );
        setStatusMsg({ type: "success", text: "Droits d'accès vocal du collaborateur mis à jour." });
      }
    } catch {
      setStatusMsg({ type: "error", text: "Erreur de mise à jour des droits" });
    }
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200/80 dark:border-white/[0.08] pb-6">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <div className="p-2.5 rounded-xl bg-blue-50 dark:bg-[#111D3D] text-[#0076FF] border border-blue-200/40 dark:border-white/[0.08]">
              <Settings className="w-6 h-6" />
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
              {companyTranslations.settingsTitle}
            </h1>
          </div>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {companyTranslations.settingsSubtitle}
          </p>
        </div>

        <button
          onClick={fetchData}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-xl border border-slate-200 dark:border-white/[0.1] bg-white dark:bg-[#0B132B] hover:bg-slate-50 dark:hover:bg-white/[0.04] transition-colors shadow-xs"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin text-[#0076FF]" : ""}`} />
          {companyTranslations.connectionsRetry}
        </button>
      </div>

      {/* Status banner */}
      {statusMsg && (
        <div
          className={`p-4 rounded-xl text-sm flex items-center gap-3 border ${
            statusMsg.type === "success"
              ? "bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800/40 text-emerald-800 dark:text-emerald-300"
              : "bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-800/40 text-red-800 dark:text-red-300"
          }`}
        >
          {statusMsg.type === "success" ? <CheckCircle2 className="w-5 h-5 shrink-0" /> : <AlertTriangle className="w-5 h-5 shrink-0" />}
          <span>{statusMsg.text}</span>
        </div>
      )}

      {/* Organization and Subscription Overview Card */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white dark:bg-[#0B132B] rounded-2xl p-6 border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              {companyTranslations.settingsCompanySection}
            </span>
            <Building2 className="w-4 h-4 text-[#0076FF]" />
          </div>
          <div>
            <div className="text-lg font-bold text-slate-900 dark:text-white truncate">
              {company?.name || companyTranslations.connectionsLoading}
            </div>
            <div className="text-xs text-slate-400 font-mono mt-1 truncate">
              {companyTranslations.connectionsUploadedSource}: {company?.id || entitlements?.company_id || "—"}
            </div>
          </div>
          <div className="pt-2 border-t border-slate-100 dark:border-white/[0.04] text-xs text-slate-500">
            {companyTranslations.settingsNameLabel}: <span className="font-medium text-slate-700 dark:text-slate-300">{user?.first_name} {user?.last_name} ({user?.role})</span>
          </div>
        </div>

        <div className="bg-white dark:bg-[#0B132B] rounded-2xl p-6 border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              {companyTranslations.settingsPlanLabel}
            </span>
            <CreditCard className="w-4 h-4 text-emerald-500" />
          </div>
          <div>
            <div className="text-lg font-bold text-slate-900 dark:text-white uppercase tracking-wide">
              {entitlements?.plan_code || company?.subscription_plan || "STANDARD"}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              {companyTranslations.settingsManageSubscription}
            </div>
          </div>
          <div className="pt-2 border-t border-slate-100 dark:border-white/[0.04]">
            <Link
              href="/billing"
              className="text-xs font-medium text-[#0076FF] hover:underline flex items-center gap-1"
            >
              {companyTranslations.settingsManageSubscription}
              <ChevronRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>

        <div className="bg-white dark:bg-[#0B132B] rounded-2xl p-6 border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              {companyTranslations.settingsPlanLabel}
            </span>
            <Layers className="w-4 h-4 text-purple-500" />
          </div>
          <div>
            <div className="text-lg font-bold text-slate-900 dark:text-white">
              {entitlements?.active_modules?.length || 0}
              {entitlements?.module_limit ? ` / ${entitlements.module_limit}` : ` ${connectorTranslations.available}`}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              {entitlements?.remaining_module_slots !== null && entitlements?.remaining_module_slots !== undefined
                ? `${entitlements.remaining_module_slots} ${connectorTranslations.available}`
                : companyTranslations.settingsSubtitle}
            </div>
          </div>
          <div className="pt-2 border-t border-slate-100 dark:border-white/[0.04] text-xs text-slate-500">
            {companyTranslations.settingsSessionSection}
          </div>
        </div>
      </div>

      {(user?.role?.toLowerCase() === "owner" || user?.role?.toLowerCase() === "admin") && (
        <section className="space-y-5 border-y border-slate-200/80 py-6 dark:border-white/[0.08]" aria-label={t.navigation.voiceAi}>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-base font-bold text-slate-900 dark:text-white">{t.navigation.voiceAi}</h2>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{voiceHealthCopy.freshness}</p>
            </div>
            {voiceStatus && (
              <div className="flex flex-wrap gap-2 text-[10px] font-mono text-slate-500">
                <span>{t.integrations.title}: {voiceStatus.telnyx_status}</span>
                <span>Retell: {voiceStatus.retell_status}</span>
                <span>STT: {voiceStatus.stt_status}</span>
                <span>TTS: {voiceStatus.tts_status}</span>
                <span>Realtime: {voiceStatus.realtime_status}</span>
              </div>
            )}
          </div>

          {!voiceStatus ? (
            <div role="status" className="text-xs text-slate-500">{companyTranslations.connectionsGenericError}</div>
          ) : (
            <>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <div className="border-l-2 border-slate-300 pl-3 dark:border-white/20">
                  <div className="text-[10px] uppercase text-slate-500">{voiceHealthCopy.phone}</div>
                  <div className="mt-1 font-mono text-sm text-slate-900 dark:text-white">{voiceStatus.business_number || t.integrations.statusDisconnected}</div>
                  <div className="mt-1 text-[10px] text-slate-500">{voiceStatus.country || "—"}{voiceStatus.region ? ` · ${voiceStatus.region}` : ""}{voiceStatus.locality ? ` · ${voiceStatus.locality}` : ""}</div>
                </div>
                <div className="border-l-2 border-slate-300 pl-3 dark:border-white/20">
                  <div className="text-[10px] uppercase text-slate-500">{t.integrations.statusConnected}</div>
                  <div className="mt-1 text-sm font-semibold text-slate-900 dark:text-white">{voiceStatus.voice_status === "ENABLED" ? t.integrations.statusConnected : voiceStatus.voice_status === "NOT_CONFIGURED" ? t.integrations.statusDisconnected : t.integrations.statusNeedsAttention}</div>
                  <div className="mt-1 text-[10px] text-slate-500">CRM: {voiceStatus.crm_status} · {t.integrations.googleCalendar}: {voiceStatus.calendar_status}</div>
                </div>
                <div className="border-l-2 border-slate-300 pl-3 dark:border-white/20">
                  <div className="text-[10px] uppercase text-slate-500">{t.navigation.retailAi}</div>
                  <div className="mt-1 text-sm font-semibold text-slate-900 dark:text-white">{voiceStatus.retail_source_context?.name || t.common.insufficientData}</div>
                  <div className="mt-1 font-mono text-[10px] text-slate-500">{voiceStatus.retail_source_context?.provider || voiceStatus.data_freshness?.freshness_status || "UNAVAILABLE"}</div>
                </div>
                <div className="border-l-2 border-slate-300 pl-3 dark:border-white/20">
                  <div className="text-[10px] uppercase text-slate-500">{voiceHealthCopy.freshness}</div>
                  <div className="mt-1 font-mono text-sm text-slate-900 dark:text-white">{voiceStatus.data_freshness?.freshness_status || "UNAVAILABLE"}</div>
                  <div className="mt-1 text-[10px] text-slate-500">{voiceStatus.data_freshness?.last_updated_at ? new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "short" }).format(new Date(voiceStatus.data_freshness.last_updated_at)) : "—"}</div>
                </div>
                <div className="border-l-2 border-slate-300 pl-3 dark:border-white/20">
                  <div className="text-[10px] uppercase text-slate-500">{voiceHealthCopy.calls} · {voiceHealthCopy.minutes}</div>
                  <div className="mt-1 font-mono text-sm text-slate-900 dark:text-white">{voiceStatus.call_count} · {voiceStatus.call_minutes}</div>
                  <div className="mt-1 text-[10px] text-slate-500">{voiceHealthCopy.credits}: {voiceStatus.voice_ai_credits_charged}</div>
                </div>
              </div>

              {voiceStatus.telnyx_status === "CONFIGURED" && !voiceStatus.module_entitled && (
                <p role="status" className="text-xs text-amber-700 dark:text-amber-300">{t.integrations.statusNeedsAttention}</p>
              )}
              {voiceStatus.telnyx_status === "CONFIGURED" && voiceStatus.module_entitled && !voiceStatus.business_number && (
                <div className="space-y-3 border-t border-slate-200 pt-4 dark:border-white/10">
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-[120px_1fr_1fr_auto]">
                    <label className="space-y-1 text-[10px] text-slate-500">
                      <span>{voiceNumberCopy.country}</span>
                      <input value={voiceSearch.countryCode} onChange={(event) => setVoiceSearch({ ...voiceSearch, countryCode: event.target.value.toUpperCase() })} maxLength={2} placeholder="CA" className="w-full rounded border border-slate-300 bg-transparent px-2 py-2 text-xs text-slate-900 dark:border-white/10 dark:text-white" />
                    </label>
                    <label className="space-y-1 text-[10px] text-slate-500">
                      <span>{voiceNumberCopy.region}</span>
                      <input value={voiceSearch.region} onChange={(event) => setVoiceSearch({ ...voiceSearch, region: event.target.value })} className="w-full rounded border border-slate-300 bg-transparent px-2 py-2 text-xs text-slate-900 dark:border-white/10 dark:text-white" />
                    </label>
                    <label className="space-y-1 text-[10px] text-slate-500">
                      <span>{voiceNumberCopy.locality}</span>
                      <input value={voiceSearch.locality} onChange={(event) => setVoiceSearch({ ...voiceSearch, locality: event.target.value })} className="w-full rounded border border-slate-300 bg-transparent px-2 py-2 text-xs text-slate-900 dark:border-white/10 dark:text-white" />
                    </label>
                    <button type="button" onClick={() => void searchVoiceNumbers()} disabled={voiceNumberBusy || voiceSearch.countryCode.length !== 2} className="inline-flex items-center justify-center gap-2 self-end rounded border border-slate-300 px-3 py-2 text-xs font-semibold disabled:opacity-50 dark:border-white/10">
                      <Search className="h-3.5 w-3.5" />{voiceNumberCopy.search}
                    </button>
                  </div>
                  {voiceNumberNeedsAction && <p role="status" className="text-xs text-amber-700 dark:text-amber-300">{t.integrations.statusNeedsAttention}</p>}
                  {voiceOffers.map((offer) => {
                    const price = offer.monthly_cost == null ? t.common.insufficientData : new Intl.NumberFormat(locale, { style: "currency", currency: offer.monthly_cost_currency || "USD" }).format(offer.monthly_cost);
                    return <div key={offer.phone_number} className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 py-3 dark:border-white/[0.06]">
                      <div>
                        <div className="font-mono text-sm font-semibold text-slate-900 dark:text-white">{offer.phone_number}</div>
                        <div className="text-[10px] text-slate-500">{voiceNumberCopy.monthlyPrice}: {price}</div>
                        {!!offer.regulatory_requirements?.length && <div className="mt-1 text-[10px] text-amber-700 dark:text-amber-300">{voiceNumberCopy.regulatoryRequirements}: {offer.regulatory_requirements.join(", ")}</div>}
                      </div>
                      <Link href="/voice" className="rounded border border-slate-300 px-3 py-2 text-xs font-semibold dark:border-white/10">{t.navigation.voiceAi}</Link>
                    </div>;
                  })}
                </div>
              )}
            </>
          )}
        </section>
      )}

      {/* Voice AI Security Section (NIP, Identités, Sessions & Accès) */}
      <section className="bg-white dark:bg-[#0B132B] rounded-2xl border border-slate-200/80 dark:border-white/[0.08] p-6 shadow-xs space-y-6" aria-label="Sécurité Voice AI">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 dark:border-white/[0.06] pb-4">
          <div>
            <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <Shield className="w-5 h-5 text-[#0076FF]" />
              {locale.startsWith("fr") ? "Sécurité Voice AI" : "Voice AI Security"}
            </h2>
            <p className="text-xs text-slate-500 mt-1">
              {locale.startsWith("fr")
                ? "Gestion des NIP vocaux à 6 chiffres, contrôle d'accès téléphonique et révocation des sessions actives."
                : "Manage 6-digit voice PINs, telephone access policies, and active session revocations."}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`text-xs px-2.5 py-1 rounded-full font-medium border ${
                pinStatus?.has_pin
                  ? "bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800"
                  : "bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800"
              }`}
            >
              {pinStatus?.has_pin
                ? (locale.startsWith("fr") ? "NIP Actif & Protégé" : "PIN Active & Protected")
                : (locale.startsWith("fr") ? "NIP Non Configuré" : "PIN Not Configured")}
            </span>
          </div>
        </div>

        {/* User's PIN Overview */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          <div className="rounded-xl border border-slate-200/60 dark:border-white/[0.06] bg-slate-50/50 dark:bg-white/[0.02] p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                {locale.startsWith("fr") ? "Votre NIP Vocal" : "Your Voice PIN"}
              </span>
              <KeyRound className="w-4 h-4 text-[#0076FF]" />
            </div>
            <div className="text-xl font-bold font-mono tracking-widest text-slate-900 dark:text-white">
              {pinStatus?.has_pin ? "••••••" : "— — — — — —"}
            </div>
            <div className="text-xs text-slate-500 flex items-center gap-1.5 pt-1">
              {pinStatus?.is_locked ? (
                <span className="text-red-600 dark:text-red-400 font-semibold flex items-center gap-1">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  {locale.startsWith("fr") ? "Compte temporairement verrouillé (tentatives max)" : "Temporarily locked (max attempts)"}
                </span>
              ) : pinStatus?.has_pin ? (
                <span className="text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  {locale.startsWith("fr") ? "Prêt pour les appels vocaux" : "Ready for voice calls"}
                </span>
              ) : (
                <span className="text-amber-600 dark:text-amber-400">
                  {locale.startsWith("fr") ? "Configurez votre NIP pour accéder à Retail/Accounting" : "Configure PIN for private tools"}
                </span>
              )}
            </div>
          </div>

          <div className="rounded-xl border border-slate-200/60 dark:border-white/[0.06] bg-slate-50/50 dark:bg-white/[0.02] p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                {locale.startsWith("fr") ? "Numéro Associé" : "Linked Phone"}
              </span>
              <PhoneCall className="w-4 h-4 text-emerald-500" />
            </div>
            <div className="text-base font-bold font-mono text-slate-900 dark:text-white">
              {pinStatus?.phone_number || "—"}
            </div>
            <div className="text-xs text-slate-500 pt-1">
              {locale.startsWith("fr") ? "Reconnaissance d'appel sécurisée" : "Secure caller identity match"}
            </div>
          </div>

          <div className="rounded-xl border border-slate-200/60 dark:border-white/[0.06] bg-slate-50/50 dark:bg-white/[0.02] p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                {locale.startsWith("fr") ? "Sessions Téléphoniques" : "Active Phone Sessions"}
              </span>
              <Lock className="w-4 h-4 text-purple-500" />
            </div>
            <div className="text-xl font-bold text-slate-900 dark:text-white">
              {pinStatus?.active_sessions_count || 0}
            </div>
            <div className="text-xs text-slate-500 pt-1">
              {locale.startsWith("fr") ? "Invalidées après chaque raccrochage" : "Invalidated after each hangup"}
            </div>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex flex-wrap items-center justify-between gap-4 pt-2 border-t border-slate-100 dark:border-white/[0.04]">
          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                setPinForm({ pin: "", confirmPin: "", currentPassword: "", phone: pinStatus?.phone_number || "" });
                setPinFormError(null);
                setPinFormSuccess(null);
                setPinModalOpen(true);
              }}
              className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-xl bg-[#0076FF] text-white hover:bg-blue-600 transition-colors shadow-xs"
            >
              <KeyRound className="w-3.5 h-3.5" />
              {pinStatus?.has_pin
                ? (locale.startsWith("fr") ? "Modifier mon NIP" : "Change my PIN")
                : (locale.startsWith("fr") ? "Créer mon NIP" : "Create my PIN")}
            </button>

            <button
              onClick={handleRevokeSessions}
              disabled={revokingSessions || !pinStatus?.active_sessions_count}
              className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-xl border border-slate-200 dark:border-white/[0.1] bg-white dark:bg-[#0B132B] text-slate-700 dark:text-white hover:bg-slate-50 dark:hover:bg-white/[0.04] transition-colors disabled:opacity-50"
            >
              <Lock className="w-3.5 h-3.5" />
              {revokingSessions
                ? (locale.startsWith("fr") ? "Révocation..." : "Revoking...")
                : (locale.startsWith("fr") ? "Révoquer les sessions actives" : "Revoke active sessions")}
            </button>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-xs font-medium text-slate-700 dark:text-slate-300">
              {locale.startsWith("fr") ? "Accès aux fonctions privées par téléphone" : "Private phone access"}
            </span>
            <button
              onClick={handleTogglePhoneAccess}
              disabled={accessToggling || !pinStatus?.has_pin}
              className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-hidden ${
                pinStatus?.phone_access_enabled ? "bg-[#0076FF]" : "bg-slate-300 dark:bg-slate-700"
              } ${accessToggling || !pinStatus?.has_pin ? "opacity-50 cursor-not-allowed" : ""}`}
            >
              <span
                className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ease-in-out ${
                  pinStatus?.phone_access_enabled ? "translate-x-5" : "translate-x-0"
                }`}
              />
            </button>
          </div>
        </div>

        {/* Team Voice Access (for Owner/Admin) */}
        {(user?.role?.toLowerCase() === "owner" || user?.role?.toLowerCase() === "admin") && voiceMembers.length > 0 && (
          <div className="space-y-3 pt-4 border-t border-slate-100 dark:border-white/[0.06]">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                {locale.startsWith("fr") ? "Accès vocal des collaborateurs" : "Team Voice Access"}
              </h3>
              <span className="text-[11px] text-slate-400">
                {locale.startsWith("fr") ? "Chaque membre possède son propre NIP individuel" : "Each member has their individual PIN"}
              </span>
            </div>
            <div className="overflow-x-auto rounded-xl border border-slate-200/60 dark:border-white/[0.06]">
              <table className="w-full text-left text-xs text-slate-700 dark:text-slate-300">
                <thead className="bg-slate-50 dark:bg-white/[0.02] text-slate-500 font-semibold border-b border-slate-200/60 dark:border-white/[0.06]">
                  <tr>
                    <th className="py-2.5 px-4">{locale.startsWith("fr") ? "Collaborateur" : "Member"}</th>
                    <th className="py-2.5 px-4">{locale.startsWith("fr") ? "Rôle" : "Role"}</th>
                    <th className="py-2.5 px-4">{locale.startsWith("fr") ? "Numéro lié" : "Linked Phone"}</th>
                    <th className="py-2.5 px-4">{locale.startsWith("fr") ? "NIP" : "PIN"}</th>
                    <th className="py-2.5 px-4 text-right">{locale.startsWith("fr") ? "Accès téléphonique" : "Voice Access"}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-white/[0.04]">
                  {voiceMembers.map((m) => (
                    <tr key={m.user_id} className="hover:bg-slate-50/50 dark:hover:bg-white/[0.01]">
                      <td className="py-2.5 px-4 font-medium text-slate-900 dark:text-white">
                        {m.first_name} {m.last_name} ({m.email})
                      </td>
                      <td className="py-2.5 px-4 uppercase text-[10px] font-mono text-slate-500">{m.role}</td>
                      <td className="py-2.5 px-4 font-mono text-[11px]">{m.phone || "—"}</td>
                      <td className="py-2.5 px-4">
                        {m.has_pin ? (
                          <span className="text-emerald-600 dark:text-emerald-400 font-medium flex items-center gap-1">
                            <Check className="w-3 h-3" /> {locale.startsWith("fr") ? "Configuré" : "Configured"}
                          </span>
                        ) : (
                          <span className="text-slate-400">{locale.startsWith("fr") ? "Non configuré" : "Not set"}</span>
                        )}
                      </td>
                      <td className="py-2.5 px-4 text-right">
                        <button
                          onClick={() => handleToggleMemberAccess(m.user_id, m.phone_access_enabled)}
                          disabled={!m.has_pin}
                          className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-hidden ${
                            m.phone_access_enabled ? "bg-[#0076FF]" : "bg-slate-300 dark:bg-slate-700"
                          } ${!m.has_pin ? "opacity-40 cursor-not-allowed" : ""}`}
                        >
                          <span
                            className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ease-in-out ${
                              m.phone_access_enabled ? "translate-x-4" : "translate-x-0"
                            }`}
                          />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Audit Log / Dernières authentifications */}
        {voiceAuditLogs.length > 0 && (
          <div className="space-y-3 pt-4 border-t border-slate-100 dark:border-white/[0.06]">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                <History className="w-3.5 h-3.5" />
                {locale.startsWith("fr") ? "Dernières authentifications et événements" : "Recent Authentications & Events"}
              </h3>
              <span className="text-[11px] text-slate-400">
                {locale.startsWith("fr") ? "Secret NIP strictement masqué et non conservé" : "PIN secret strictly redacted"}
              </span>
            </div>
            <div className="divide-y divide-slate-100 dark:divide-white/[0.04] text-xs">
              {voiceAuditLogs.slice(0, 5).map((log) => (
                <div key={log.id} className="py-2 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <span
                      className={`w-2 h-2 rounded-full ${
                        log.success ? "bg-emerald-500" : "bg-red-500"
                      }`}
                    />
                    <span className="font-mono text-slate-800 dark:text-slate-200">
                      {log.action.replace(/_/g, " ")}
                    </span>
                  </div>
                  <span className="text-slate-400 font-mono text-[11px]">
                    {log.timestamp ? new Date(log.timestamp).toLocaleString(locale) : "—"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* Modal de configuration / modification du NIP */}
      {pinModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
          <div className="w-full max-w-md rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200 dark:border-white/10 p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-white/[0.06] pb-3">
              <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <Shield className="w-5 h-5 text-[#0076FF]" />
                {pinStatus?.has_pin
                  ? (locale.startsWith("fr") ? "Modifier votre NIP Vocal" : "Change your Voice PIN")
                  : (locale.startsWith("fr") ? "Créer votre NIP Vocal" : "Create your Voice PIN")}
              </h3>
              <button
                onClick={() => setPinModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-500">
              {locale.startsWith("fr")
                ? "Le NIP vocal à 6 chiffres protège vos données confidentielles (Retail, Accounting, CRM interne). Une réauthentification web forte est exigée."
                : "The 6-digit Voice PIN protects confidential company data. Strong web re-authentication is required."}
            </p>

            {pinFormError && (
              <div className="flex items-center gap-2 rounded-lg bg-red-50 dark:bg-red-950/40 p-3 text-xs text-red-700 dark:text-red-300">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span>{pinFormError}</span>
              </div>
            )}
            {pinFormSuccess && (
              <div className="flex items-center gap-2 rounded-lg bg-emerald-50 dark:bg-emerald-950/40 p-3 text-xs text-emerald-700 dark:text-emerald-300">
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                <span>{pinFormSuccess}</span>
              </div>
            )}

            <form onSubmit={handleSavePin} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                  {locale.startsWith("fr") ? "Nouveau NIP Vocal (6 chiffres)" : "New Voice PIN (6 digits)"}
                </label>
                <input
                  type="password"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={6}
                  placeholder="••••••"
                  value={pinForm.pin}
                  onChange={(e) => setPinForm({ ...pinForm, pin: e.target.value.replace(/\D/g, "") })}
                  required
                  className="mt-1 w-full rounded-xl border border-slate-300 bg-white dark:bg-slate-900 px-4 py-2.5 text-center text-lg font-mono tracking-widest text-slate-900 dark:text-white shadow-xs focus:border-[#0076FF] focus:outline-hidden dark:border-white/20"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                  {locale.startsWith("fr") ? "Confirmer le NIP" : "Confirm PIN"}
                </label>
                <input
                  type="password"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={6}
                  placeholder="••••••"
                  value={pinForm.confirmPin}
                  onChange={(e) => setPinForm({ ...pinForm, confirmPin: e.target.value.replace(/\D/g, "") })}
                  required
                  className="mt-1 w-full rounded-xl border border-slate-300 bg-white dark:bg-slate-900 px-4 py-2.5 text-center text-lg font-mono tracking-widest text-slate-900 dark:text-white shadow-xs focus:border-[#0076FF] focus:outline-hidden dark:border-white/20"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                  {locale.startsWith("fr") ? "Mot de passe actuel du compte (Réauthentification forte)" : "Current account password (Strong re-auth)"}
                </label>
                <input
                  type="password"
                  placeholder="••••••••••••"
                  value={pinForm.currentPassword}
                  onChange={(e) => setPinForm({ ...pinForm, currentPassword: e.target.value })}
                  required={pinStatus?.has_pin}
                  className="mt-1 w-full rounded-xl border border-slate-300 bg-white dark:bg-slate-900 px-4 py-2 text-sm text-slate-900 dark:text-white shadow-xs focus:border-[#0076FF] focus:outline-hidden dark:border-white/20"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                  {locale.startsWith("fr") ? "Numéro de téléphone de liaison (+1...)" : "Telephone number (+1...)"}
                </label>
                <input
                  type="tel"
                  placeholder="+15145550199"
                  value={pinForm.phone}
                  onChange={(e) => setPinForm({ ...pinForm, phone: e.target.value })}
                  className="mt-1 w-full rounded-xl border border-slate-300 bg-white dark:bg-slate-900 px-4 py-2 text-sm text-slate-900 dark:text-white shadow-xs focus:border-[#0076FF] focus:outline-hidden dark:border-white/20"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-3">
                <button
                  type="button"
                  onClick={() => setPinModalOpen(false)}
                  className="px-4 py-2 text-xs font-medium rounded-xl border border-slate-300 dark:border-white/20 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800"
                >
                  {locale.startsWith("fr") ? "Annuler" : "Cancel"}
                </button>
                <button
                  type="submit"
                  disabled={pinFormBusy || pinForm.pin.length !== 6 || pinForm.confirmPin.length !== 6}
                  className="inline-flex items-center gap-2 px-5 py-2 text-xs font-semibold rounded-xl bg-[#0076FF] text-white hover:bg-blue-600 disabled:opacity-50 shadow-sm"
                >
                  <Lock className="w-3.5 h-3.5" />
                  {pinFormBusy
                    ? (locale.startsWith("fr") ? "Enregistrement..." : "Saving...")
                    : (locale.startsWith("fr") ? "Confirmer et Sécuriser" : "Confirm and Secure")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Module Entitlements Section */}
      <div className="bg-white dark:bg-[#0B132B] rounded-2xl border border-slate-200/80 dark:border-white/[0.08] p-6 shadow-xs space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 dark:border-white/[0.06] pb-4">
          <div>
            <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <Layers className="w-5 h-5 text-[#0076FF]" />
              {companyTranslations.settingsTitle}
            </h2>
            <p className="text-xs text-slate-500 mt-1">
              {companyTranslations.settingsSubtitle}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs px-2.5 py-1 rounded-full bg-blue-50 dark:bg-blue-900/30 text-[#0076FF] font-medium border border-blue-200/60 dark:border-blue-700/40">
              {entitlements?.active_modules?.length || 0} {connectorTranslations.connected}
            </span>
          </div>
        </div>

        {loading ? (
          <div className="py-12 flex flex-col items-center justify-center text-slate-400 gap-3">
            <RefreshCw className="w-8 h-8 animate-spin text-[#0076FF]" />
            <span className="text-sm">{companyTranslations.connectionsLoading}</span>
          </div>
        ) : !entitlements?.modules || entitlements.modules.length === 0 ? (
          <div className="py-12 text-center text-slate-400">
            {companyTranslations.connectionsNoDataTitle}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {entitlements.modules.map((mod) => {
              const isUpdating = updatingKey === mod.key;
              const isLocked = mod.state === "upgrade_required";

              return (
                <div
                  key={mod.key}
                  className={`p-4 rounded-xl border transition-all flex flex-col justify-between gap-4 ${
                    mod.active
                      ? "bg-blue-50/30 dark:bg-[#111D3D]/30 border-blue-200/80 dark:border-blue-900/50"
                      : "bg-slate-50/50 dark:bg-white/[0.02] border-slate-200/60 dark:border-white/[0.06]"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-sm text-slate-900 dark:text-white">
                          {mod.display_name}
                        </span>
                        {mod.premium && (
                          <span className="text-[10px] px-2 py-0.5 rounded-md bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300 font-semibold uppercase">
                            {companyTranslations.businessDefaultTitle}
                          </span>
                        )}
                        <span
                          className={`text-[10px] px-2 py-0.5 rounded-md font-medium uppercase ${
                            mod.active
                              ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300"
                              : "bg-slate-100 text-slate-600 dark:bg-white/[0.06] dark:text-slate-400"
                          }`}
                        >
                          {mod.active ? connectorTranslations.ready : connectorTranslations.disconnected}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-2">
                        {mod.description}
                      </p>
                    </div>

                    {isLocked ? (
                      <div className="p-2 rounded-lg bg-amber-50 dark:bg-amber-950/40 text-amber-600 dark:text-amber-400" title={connectorTranslations.reauthorizeWooCommerce}>
                        <Lock className="w-4 h-4" />
                      </div>
                    ) : (
                      <button
                        onClick={() => handleToggleModule(mod)}
                        disabled={isUpdating}
                        className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-hidden ${
                          mod.active ? "bg-[#0076FF]" : "bg-slate-300 dark:bg-slate-700"
                        } ${isUpdating ? "opacity-50 cursor-not-allowed" : ""}`}
                      >
                        <span
                          className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ease-in-out ${
                            mod.active ? "translate-x-5" : "translate-x-0"
                          }`}
                        />
                      </button>
                    )}
                  </div>

                  <div className="flex items-center justify-between text-[11px] text-slate-400 border-t border-slate-100 dark:border-white/[0.04] pt-2">
                    <span>{companyTranslations.businessDefaultTitle}: {mod.category}</span>
                    {mod.active && (
                      <Link
                        href={
                          mod.key === "accounting" ? "/accounting" :
                          mod.key === "marketing" ? "/marketing" :
                          mod.key === "retail" ? "/retail" :
                          mod.key === "crm" ? "/crm" :
                          "/dashboard"
                        }
                        className="text-[#0076FF] hover:underline flex items-center gap-1 font-medium"
                      >
                        {companyTranslations.connectionsGoDashboard}
                        <ChevronRight className="w-3 h-3" />
                      </Link>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Security & Multi-Tenant Notice */}
      <div className="bg-slate-50 dark:bg-[#060B13] rounded-2xl p-6 border border-slate-200 dark:border-white/[0.08] flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="flex items-start gap-4">
          <div className="p-3 rounded-xl bg-blue-100 dark:bg-[#111D3D] text-[#0076FF] shrink-0">
            <Shield className="w-6 h-6" />
          </div>
          <div className="space-y-1">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">
              {companyTranslations.settingsSubtitle}
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 max-w-2xl">
              {companyTranslations.settingsSubtitle}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <Link
            href="/connections"
            className="px-4 py-2 text-xs font-semibold rounded-xl bg-[#0076FF] text-white hover:bg-blue-600 transition-colors shadow-xs"
          >
            {companyTranslations.navConnectionsLabel}
          </Link>
          <Link
            href="/billing"
            className="px-4 py-2 text-xs font-semibold rounded-xl border border-slate-200 dark:border-white/[0.1] bg-white dark:bg-[#0B132B] text-slate-700 dark:text-white hover:bg-slate-50 dark:hover:bg-white/[0.04] transition-colors shadow-xs"
          >
            {companyTranslations.navBillingLabel}
          </Link>
        </div>
      </div>
    </div>
  );
}
