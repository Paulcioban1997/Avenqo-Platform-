"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  PhoneCall,
  Sparkles,
  Calendar,
  Clock,
  ShieldCheck,
  CheckCircle,
  HelpCircle,
  Volume2,
  Lock,
  ChevronDown,
  ChevronUp,
  Settings,
  ShieldAlert,
  Search,
  Check,
  Play,
  ArrowRight,
  RefreshCw,
  Sliders,
  Users,
  Store,
  Bot,
  KeyRound,
  Copy,
  Trash2,
  PhoneIncoming,
} from "lucide-react";
import { useSession } from "@/lib/session-context";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
import { getApplicationCatalog } from "@/lib/i18n/generated-app-catalogs";
import { VOICE_HEALTH_COPY } from "@/lib/i18n/voice-health-copy";
import { VOICE_NUMBER_COPY, VOICE_SELECTION_COPY, VOICE_NUMBER_TYPE_COPY } from "@/lib/i18n/voice-number-copy";
import { VOICE_AUTH_MESSAGES } from "@/lib/i18n/voice-auth-messages.generated";
import { VoiceCustomizationSection } from "@/components/voice/voice-customization-section";
import { VoiceBusinessOnboarding } from "@/components/voice/voice-business-onboarding";
import { VoiceProvisioningSection } from "@/components/voice/voice-provisioning-section";
import { VoiceCallPolicy } from "@/components/voice/voice-call-policy";
import { VoiceModulePermissionsSection } from "@/components/settings/voice-module-permissions";

interface Capabilities {
  tenant_id: string;
  subscription_plan: string;
  subscription_status: string;
  enabled_modules: string[];
  plan_compatible_modules: string[];
  available_agents: string[];
  permissions: string[];
  locale: string;
  timezone: string;
  authorized_sources: { sources?: { source_id: string; display_name?: string; name?: string }[] };
  language_matrix: {
    locale: string;
    UI_TRANSLATION_SUPPORTED: boolean;
    STT_SUPPORTED: boolean | null;
    LLM_LANGUAGE_SUPPORTED: boolean | null;
    TTS_SUPPORTED: boolean | null;
    LIVE_AUDIO_VALIDATED: boolean;
    FULLY_SUPPORTED: boolean;
  }[];
}

interface VoiceStatus {
  voice_status: string;
  number_id: string | null;
  configuration_status: string;
  business_number: string | null;
  country: string | null;
  region: string | null;
  locality: string | null;
  call_count: number;
  call_minutes: number;
  voice_ai_credits_charged: number;
  recent_calls?: { id: string; status: string; started_at: string | null }[];
  data_freshness?: { freshness_status: string };
  routing_nip?: string | null;
  dispatcher_number?: string | null;
}

interface Offer {
  phone_number: string;
  is_orderable: boolean;
  number_type: string;
  country_code: string | null;
  region: string | null;
  locality: string | null;
  capabilities: string[];
  cost_information: { upfront_cost?: string; monthly_cost?: string; currency?: string };
  regulatory_requirements: unknown[];
  regulatory_status: string;
}

interface NumberQuote {
  offer: Offer;
  quote_token: string;
  purchase_allowed: boolean;
  expires_in_seconds: number;
}

export function VoiceModuleView() {
  const { identity, sourceRevision, credits, creditError } = useSession();
  const { locale } = useLocale();
  const fr = locale.startsWith("fr");
  const t = getAppTranslations(locale);
  const company = getApplicationCatalog(locale).company;
  const billing = getApplicationCatalog(locale).phase4e.billing;
  const copy = VOICE_NUMBER_COPY[locale];
  const selectionCopy = VOICE_SELECTION_COPY[locale];
  const typeCopy = VOICE_NUMBER_TYPE_COPY[locale];
  const numberTypes = ["local", "mobile", "toll_free", "national", "shared_cost"];
  const numberTypeLabel = (type: string) =>
    numberTypes.includes(type)
      ? typeCopy[numberTypes.indexOf(type) + 1]
      : t.common.insufficientData;
  const health = VOICE_HEALTH_COPY[locale];
  const tenantId = identity?.company.id;

  const [context, setContext] = useState<Capabilities | null>(null);
  const [status, setStatus] = useState<{ tenant: string; data: VoiceStatus } | null>(null);
  const [result, setResult] = useState<{ tenant: string; offers: Offer[] } | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [quote, setQuote] = useState<NumberQuote | null>(null);
  const [ownedNumber, setOwnedNumber] = useState("");
  const [pinMessage, setPinMessage] = useState("");
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [filters, setFilters] = useState({
    country_code: "",
    region: "",
    locality: "",
    area_code: "",
    prefix: "",
    number_type: "local",
  });
  const [features, setFeatures] = useState(["voice"]);
  const searchAbort = useRef<AbortController | null>(null);

  // SIMPLIFIED WIZARD STATE
  const [activeStep, setActiveStep] = useState<number>(1);
  const [selectedUseCases, setSelectedUseCases] = useState<string[]>([
    "answer_calls",
    "book_appointments",
    "answer_questions",
  ]);
  const [languageMode, setLanguageMode] = useState<string>("auto");
  const [allowedModules, setAllowedModules] = useState<string[]>(["crm", "retail"]);
  const [testCallStatus, setTestCallStatus] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(true);

  // COMPANY TELEPHONE ROUTING NIP (DTMF) STATE
  const [routingNip, setRoutingNip] = useState<string | null>(null);
  const [dispatcherNumber, setDispatcherNumber] = useState<string>("+1 438-607-5438");
  const [customNipInput, setCustomNipInput] = useState<string>("");
  const [nipBusy, setNipBusy] = useState<boolean>(false);
  const [nipFeedback, setNipFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [copiedNip, setCopiedNip] = useState<boolean>(false);

  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(async () => {
      if (controller.signal.aborted) return;
      setContext(null);
      setResult(null);
      setSelected(null);
      setStatus(null);
      setError(false);
      setBusy(false);
      setQuote(null);
      setOwnedNumber("");
      setPinMessage("");
      setNipFeedback(null);
      if (!tenantId) return;
      try {
        const response = await fetch("/api/v1/voice/capabilities", {
          signal: controller.signal,
          cache: "no-store",
        });
        if (!response.ok) throw new Error("capabilities_unavailable");
        const data: Capabilities = await response.json();
        if (!controller.signal.aborted && data.tenant_id === tenantId) setContext(data);
        const state = await fetch("/api/v1/voice/status", {
          signal: controller.signal,
          cache: "no-store",
        });
        if (state.ok) {
          const payload: VoiceStatus = await state.json();
          if (!controller.signal.aborted) {
            setStatus({ tenant: tenantId, data: payload });
            if (payload.routing_nip) setRoutingNip(payload.routing_nip);
            if (payload.dispatcher_number) setDispatcherNumber(payload.dispatcher_number);
          }
        }
      } catch {
        if (!controller.signal.aborted) setError(true);
      }
    });
    return () => {
      controller.abort();
      searchAbort.current?.abort();
    };
  }, [tenantId, identity?.user.id, sourceRevision]);

  const active = context?.tenant_id === tenantId ? context : null;
  const currentStatus = status && status.tenant === tenantId ? status.data : null;
  const offers = result && result.tenant === tenantId ? result.offers : [];
  const enabled = active?.enabled_modules.includes("voice") ?? false;
  const canManageVoice = active?.permissions.includes("modules:manage") ?? false;
  const messages = VOICE_AUTH_MESSAGES[locale] ?? VOICE_AUTH_MESSAGES.en;

  async function refreshVoiceStatus() {
    const response = await fetch("/api/v1/voice/status", { cache: "no-store" });
    if (!response.ok) throw new Error("voice_status_unavailable");
    const payload: VoiceStatus = await response.json();
    setStatus({ tenant: tenantId ?? "", data: payload });
    if (payload.routing_nip !== undefined) setRoutingNip(payload.routing_nip);
    if (payload.dispatcher_number) setDispatcherNumber(payload.dispatcher_number);
  }

  async function generateRandomNip() {
    setNipBusy(true);
    setNipFeedback(null);
    try {
      const res = await fetch("/api/v1/voice/routing-nip", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ custom_code: null }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || (fr ? "Échec de génération du code NIP." : "Failed to generate routing PIN."));
      }
      const data = await res.json();
      setRoutingNip(data.routing_code);
      setNipFeedback({
        type: "success",
        message: fr ? `Nouveau code NIP d'entreprise généré : ${data.routing_code}` : `New company routing PIN generated: ${data.routing_code}`,
      });
      await refreshVoiceStatus();
    } catch (err) {
      setNipFeedback({
        type: "error",
        message: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setNipBusy(false);
    }
  }

  async function setCustomNip() {
    if (!customNipInput.trim()) return;
    setNipBusy(true);
    setNipFeedback(null);
    try {
      const res = await fetch("/api/v1/voice/routing-nip", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ custom_code: customNipInput.trim() }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || (fr ? "Échec de configuration du NIP." : "Failed to configure PIN."));
      }
      const data = await res.json();
      setRoutingNip(data.routing_code);
      setCustomNipInput("");
      setNipFeedback({
        type: "success",
        message: fr ? `Code NIP personnalisé configuré : ${data.routing_code}` : `Custom routing PIN configured: ${data.routing_code}`,
      });
      await refreshVoiceStatus();
    } catch (err) {
      setNipFeedback({
        type: "error",
        message: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setNipBusy(false);
    }
  }

  async function revokeNip() {
    if (!confirm(fr ? "Êtes-vous certain de vouloir révoquer ce code NIP d'acheminement ?" : "Are you sure you want to revoke this company routing PIN?")) return;
    setNipBusy(true);
    setNipFeedback(null);
    try {
      const res = await fetch("/api/v1/voice/routing-nip", { method: "DELETE" });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || (fr ? "Échec de révocation." : "Failed to revoke PIN."));
      }
      setRoutingNip(null);
      setNipFeedback({
        type: "success",
        message: fr ? "Code NIP révoqué avec succès." : "Routing PIN successfully revoked.",
      });
      await refreshVoiceStatus();
    } catch (err) {
      setNipFeedback({
        type: "error",
        message: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setNipBusy(false);
    }
  }

  function copyCallingInstructions() {
    const textToCopy = fr
      ? `Appelez au standard Avenqo au ${dispatcherNumber} et tapez le code NIP de notre entreprise : ${routingNip}# pour joindre notre réceptionniste IA.`
      : `Call Avenqo platform at ${dispatcherNumber} and enter our company routing PIN: ${routingNip}# to connect to our AI receptionist.`;
    navigator.clipboard.writeText(textToCopy);
    setCopiedNip(true);
    setTimeout(() => setCopiedNip(false), 3000);
  }

  async function saveVoicePin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const input = event.currentTarget.elements.namedItem("voice-pin") as HTMLInputElement;
    const pin = input.value;
    const passwordInput = event.currentTarget.elements.namedItem(
      "voice-account-password"
    ) as HTMLInputElement;
    setPinMessage("");
    try {
      const response = await fetch("/api/v1/voice/auth/pin", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin, confirm_pin: pin, current_password: passwordInput.value }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(
          payload?.error?.message ||
            (typeof payload?.detail === "string" ? payload.detail : company.connectionsGenericError)
        );
      }
      setPinMessage(messages[5]);
    } catch (error) {
      setPinMessage(error instanceof Error ? error.message : company.connectionsGenericError);
    } finally {
      input.value = "";
      passwordInput.value = "";
    }
  }

  const price = (offer: Offer, key: "upfront_cost" | "monthly_cost") => {
    const value = offer.cost_information[key];
    return value != null && offer.cost_information.currency && Number.isFinite(Number(value))
      ? new Intl.NumberFormat(locale, { style: "currency", currency: offer.cost_information.currency }).format(
          Number(value)
        )
      : t.common.insufficientData;
  };

  async function requestQuote() {
    const offer = offers.find((item) => item.phone_number === selected);
    if (!offer) return;
    setQuote(null);
    setBusy(true);
    setError(false);
    const params = new URLSearchParams({
      phone_number: offer.phone_number,
      country_code: offer.country_code ?? filters.country_code,
      number_type: offer.number_type,
      ...(offer.region ? { region: offer.region } : {}),
      ...(offer.locality ? { locality: offer.locality } : {}),
    });
    try {
      const response = await fetch(`/api/v1/voice/numbers/quote?${params}`, { cache: "no-store" });
      if (!response.ok) throw new Error("number_quote_unavailable");
      setQuote(await response.json());
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  async function search(event: React.FormEvent) {
    event.preventDefault();
    if (!tenantId || !enabled || !canManageVoice) return;
    searchAbort.current?.abort();
    const controller = new AbortController();
    searchAbort.current = controller;
    setBusy(true);
    setError(false);
    setSelected(null);
    setQuote(null);
    setResult(null);
    const params = new URLSearchParams({
      country_code: filters.country_code.toUpperCase(),
      number_type: filters.number_type,
      limit: "10",
    });
    for (const key of ["region", "locality", "area_code", "prefix"] as const) {
      if (filters[key].trim()) params.set(key, filters[key].trim());
    }
    for (const feature of features) params.append("capabilities", feature);
    try {
      const response = await fetch(`/api/v1/voice/numbers/search?${params}`, {
        signal: controller.signal,
        cache: "no-store",
      });
      if (!response.ok) throw new Error("number_search_unavailable");
      const payload = await response.json();
      if (!controller.signal.aborted) setResult({ tenant: tenantId, offers: payload.offers });
    } catch {
      if (!controller.signal.aborted) setError(true);
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  const toggleUseCase = (id: string) => {
    setSelectedUseCases((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const toggleModule = (id: string) => {
    setAllowedModules((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const handleSimulateTestCall = () => {
    setTestCallStatus("calling");
    setTimeout(() => {
      setTestCallStatus("connected");
      setTimeout(() => {
        setTestCallStatus("success");
      }, 3000);
    }, 2000);
  };

  return (
    <div className="space-y-7 animate-in fade-in duration-300">
      {/* HEADER */}
      <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-slate-200 dark:border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold uppercase tracking-widest text-[#0076FF] dark:text-[#00D4FF]">
              Avenqo Voice AI
            </span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300 font-medium">
              Standard Intelligent 24/7
            </span>
          </div>
          <h1 className="mt-1 text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">
            {fr ? "Voice AI — Votre réceptionniste intelligent" : "Voice AI — Your Intelligent Receptionist"}
          </h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            {fr
              ? "Prise en charge automatisée des appels, planification de rendez-vous et transfert d'urgences."
              : "Automated call answering, calendar scheduling, and intelligent routing."}
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {routingNip && (
            <div className="px-3.5 py-1.5 rounded-xl bg-purple-50 dark:bg-purple-950/60 border border-purple-200 dark:border-purple-800 text-purple-700 dark:text-purple-300 text-xs font-mono font-bold flex items-center gap-1.5 shadow-xs">
              <KeyRound className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400" />
              <span>NIP : {routingNip}#</span>
            </div>
          )}
          {currentStatus?.business_number ? (
            <div className="px-3.5 py-1.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 text-xs font-mono font-bold flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span>{currentStatus.business_number}</span>
            </div>
          ) : (
            <div className="px-3.5 py-1.5 rounded-xl bg-blue-50 dark:bg-blue-950/60 border border-blue-200 dark:border-blue-900 text-blue-700 dark:text-blue-300 text-xs font-semibold">
              {fr ? "Sandbox Telnyx Prête" : "Telnyx Sandbox Ready"}
            </div>
          )}
        </div>
      </header>

      {/* ERROR / BALANCE ALERTS */}
      {error && (
        <p role="alert" className="flex items-center gap-2 text-sm text-red-700 dark:text-red-300">
          <ShieldAlert size={16} />
          {company.connectionsGenericError}
        </p>
      )}

      {active && (credits.remaining === 0 || !["active", "trialing"].includes(active.subscription_status)) && (
        <div role="alert" className="rounded-2xl border border-amber-400 bg-amber-500/10 p-5 text-sm">
          <p className="font-bold text-amber-900 dark:text-amber-200">
            {fr
              ? "Accueil téléphonique bloqué : solde de crédits IA insuffisant."
              : "Phone assistant blocked: insufficient AI credits balance."}
          </p>
          <Link href="/billing" className="mt-2 inline-block text-xs font-bold text-[#0076FF] underline">
            {fr ? "Recharger mes crédits dans Facturation" : "Recharge credits in Billing"}
          </Link>
        </div>
      )}

      {/* 6-STEP SIMPLE GUIDED CONFIGURATION */}
      <div className="rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B132B] shadow-xs overflow-hidden">
        {/* STEP PROGRESS NAV */}
        <div className="flex items-center border-b border-slate-200 dark:border-slate-800 overflow-x-auto scrollbar-none bg-slate-50/50 dark:bg-slate-900/50 p-2 gap-1">
          {[
            { step: 1, labelFr: "1. Cas d'usage", labelEn: "1. Use Case" },
            { step: 2, labelFr: "2. Langues", labelEn: "2. Language" },
            { step: 3, labelFr: "3. Horaires", labelEn: "3. Business Hours" },
            { step: 4, labelFr: "4. Modules", labelEn: "4. Modules" },
            { step: 5, labelFr: "5. Numéro", labelEn: "5. Phone Number" },
            { step: 6, labelFr: "6. Test Vocal", labelEn: "6. Voice Test" },
          ].map((item) => (
            <button
              key={item.step}
              onClick={() => setActiveStep(item.step)}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold transition whitespace-nowrap ${
                activeStep === item.step
                  ? "bg-[#0076FF] text-white shadow-xs"
                  : "text-slate-600 dark:text-slate-400 hover:bg-slate-200/60 dark:hover:bg-slate-800"
              }`}
            >
              {fr ? item.labelFr : item.labelEn}
            </button>
          ))}
        </div>

        <div className="p-6 sm:p-7">
          {/* STEP 1: USE CASES */}
          {activeStep === 1 && (
            <div className="space-y-5 animate-in fade-in duration-200">
              <div>
                <h3 className="text-lg font-extrabold text-slate-900 dark:text-white">
                  {fr ? "Étape 1 : Choisissez le rôle de votre réceptionniste" : "Step 1: Choose the role of your voice receptionist"}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  {fr ? "Sélectionnez toutes les tâches que Voice AI doit exécuter au téléphone." : "Select all tasks Voice AI should handle during incoming calls."}
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                {[
                  { id: "answer_calls", titleFr: "Répondre aux appels clients 24/7", titleEn: "Answer customer calls 24/7", descFr: "Accueille poliment vos clients à tout moment sans sonnerie dans le vide.", descEn: "Politely answers your callers anytime without missed calls." },
                  { id: "book_appointments", titleFr: "Prendre et reporter des rendez-vous", titleEn: "Book and reschedule appointments", descFr: "Vérifie les disponibilités CRM en direct et valide les créneaux autorisés.", descEn: "Live verifies CRM availability and books permitted slots." },
                  { id: "answer_questions", titleFr: "Répondre aux questions sur l'entreprise", titleEn: "Answer business questions", descFr: "Fournit vos adresses, horaires, tarifs et services à partir de la mémoire Mem0.", descEn: "Provides address, hours, rates, and services from Mem0 memory." },
                  { id: "sales_info", titleFr: "Fournir des informations de vente", titleEn: "Provide sales & catalog information", descFr: "Consulte le stock et les prix du module Retail pour conseiller l'appelant.", descEn: "Queries stock and pricing from Retail module to guide callers." },
                  { id: "route_calls", titleFr: "Transférer les urgences aux employés", titleEn: "Route urgent calls to employees", descFr: "Transfère l'appel vers la bonne ligne en cas de demande spécifique.", descEn: "Transfers calls to the right employee extension for urgent needs." },
                ].map((uc) => {
                  const isChecked = selectedUseCases.includes(uc.id);
                  return (
                    <div
                      key={uc.id}
                      onClick={() => toggleUseCase(uc.id)}
                      className={`p-4 rounded-2xl border cursor-pointer transition flex items-start justify-between gap-3 ${
                        isChecked
                          ? "border-[#0076FF] bg-blue-50/50 dark:bg-blue-950/30"
                          : "border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700"
                      }`}
                    >
                      <div className="space-y-1">
                        <p className="font-bold text-sm text-slate-900 dark:text-white">
                          {fr ? uc.titleFr : uc.titleEn}
                        </p>
                        <p className="text-xs text-slate-500 dark:text-slate-400">
                          {fr ? uc.descFr : uc.descEn}
                        </p>
                      </div>
                      <div className={`w-5 h-5 rounded-md border flex items-center justify-center shrink-0 mt-0.5 ${
                        isChecked ? "bg-[#0076FF] border-[#0076FF] text-white" : "border-slate-300 dark:border-slate-700"
                      }`}>
                        {isChecked && <Check className="w-3.5 h-3.5" />}
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="flex justify-end pt-3">
                <button
                  onClick={() => setActiveStep(2)}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#0076FF] text-white font-bold text-xs shadow-md hover:bg-blue-600 transition"
                >
                  <span>{fr ? "Continuer vers les langues" : "Continue to Languages"}</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}

          {/* STEP 2: LANGUAGES */}
          {activeStep === 2 && (
            <div className="space-y-5 animate-in fade-in duration-200">
              <div>
                <h3 className="text-lg font-extrabold text-slate-900 dark:text-white">
                  {fr ? "Étape 2 : Préférences linguistiques" : "Step 2: Language Preferences"}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  {fr ? "Voice AI bascule automatiquement dans la langue de votre client." : "Voice AI automatically adapts to your caller's language."}
                </p>
              </div>

              <div className="space-y-3">
                <div
                  onClick={() => setLanguageMode("auto")}
                  className={`p-4 rounded-2xl border cursor-pointer transition flex items-center justify-between ${
                    languageMode === "auto"
                      ? "border-[#0076FF] bg-blue-50/50 dark:bg-blue-950/30"
                      : "border-slate-200 dark:border-slate-800"
                  }`}
                >
                  <div>
                    <p className="font-bold text-sm text-slate-900 dark:text-white">
                      {fr ? "Détection automatique de la langue (Recommandé)" : "Automatic Language Detection (Recommended)"}
                    </p>
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                      {fr ? "Reconnaît immédiatement le français canadien, l'anglais ou 40+ autres langues." : "Recognizes Canadian French, English, or 40+ other languages automatically."}
                    </p>
                  </div>
                  {languageMode === "auto" && <CheckCircle className="w-5 h-5 text-[#0076FF]" />}
                </div>

                <div
                  onClick={() => setLanguageMode("fr_only")}
                  className={`p-4 rounded-2xl border cursor-pointer transition flex items-center justify-between ${
                    languageMode === "fr_only"
                      ? "border-[#0076FF] bg-blue-50/50 dark:bg-blue-950/30"
                      : "border-slate-200 dark:border-slate-800"
                  }`}
                >
                  <div>
                    <p className="font-bold text-sm text-slate-900 dark:text-white">
                      {fr ? "Français uniquement" : "French only"}
                    </p>
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                      {fr ? "Accueil strict et échanges exclusivement en français." : "Strict French conversation only."}
                    </p>
                  </div>
                  {languageMode === "fr_only" && <CheckCircle className="w-5 h-5 text-[#0076FF]" />}
                </div>
              </div>

              <div className="flex justify-between pt-3">
                <button
                  onClick={() => setActiveStep(1)}
                  className="px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-800 text-xs font-semibold"
                >
                  {fr ? "Précédent" : "Back"}
                </button>
                <button
                  onClick={() => setActiveStep(3)}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#0076FF] text-white font-bold text-xs shadow-md"
                >
                  <span>{fr ? "Continuer vers les horaires" : "Continue to Hours"}</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}

          {/* STEP 3: BUSINESS HOURS */}
          {activeStep === 3 && (
            <div className="space-y-5 animate-in fade-in duration-200">
              <div>
                <h3 className="text-lg font-extrabold text-slate-900 dark:text-white">
                  {fr ? "Étape 3 : Horaires d'ouverture de l'entreprise" : "Step 3: Company Business Hours"}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  {fr ? "Voice AI respecte strictement vos horaires d'ouverture et ne propose aucun créneau hors-période." : "Voice AI strictly enforces your business hours and never proposes closed slots."}
                </p>
              </div>

              <div className="p-5 rounded-2xl border border-blue-100 dark:border-blue-900/40 bg-blue-50/40 dark:bg-blue-950/20 space-y-3">
                <div className="flex items-center gap-2 text-blue-900 dark:text-blue-200 font-bold text-sm">
                  <Clock className="w-4 h-4 text-[#0076FF]" />
                  <span>{fr ? "Synchronisation avec le CRM Avenqo" : "Synced with Avenqo CRM"}</span>
                </div>
                <p className="text-xs text-slate-600 dark:text-slate-300">
                  {fr
                    ? "Les horaires hebdomadaires, pauses repas, durées de services et congés configurés dans votre CRM sont appliqués en temps réel au téléphone."
                    : "Weekly schedules, lunch breaks, service durations, and closures configured in your CRM are applied in real time to phone calls."}
                </p>
                <Link
                  href="/crm"
                  className="inline-flex items-center gap-1.5 text-xs font-bold text-[#0076FF] hover:underline"
                >
                  <span>{fr ? "Ajuster les horaires dans le CRM" : "Adjust hours in CRM"}</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>

              <div className="flex justify-between pt-3">
                <button
                  onClick={() => setActiveStep(2)}
                  className="px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-800 text-xs font-semibold"
                >
                  {fr ? "Précédent" : "Back"}
                </button>
                <button
                  onClick={() => setActiveStep(4)}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#0076FF] text-white font-bold text-xs shadow-md"
                >
                  <span>{fr ? "Continuer vers les modules" : "Continue to Modules"}</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}

          {/* STEP 4: AUTHORIZED MODULES */}
          {activeStep === 4 && (
            <div className="space-y-5 animate-in fade-in duration-200">
              <div>
                <h3 className="text-lg font-extrabold text-slate-900 dark:text-white">
                  {fr ? "Étape 4 : Modules autorisés pour Voice AI" : "Step 4: Authorized Modules for Voice AI"}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  {fr ? "Contrôlez les outils que le réceptionniste peut interroger en direct." : "Control which business tools the voice assistant can query live."}
                </p>
              </div>

              <div className="space-y-3">
                {[
                  { id: "crm", icon: Calendar, titleFr: "CRM AI (Calendrier & Prise de rendez-vous)", titleEn: "CRM AI (Calendar & Booking)", descFr: "Permet de vérifier les créneaux réels et d'inscrire le rendez-vous immédiatement.", descEn: "Allows live slot verification and immediate booking." },
                  { id: "retail", icon: Store, titleFr: "Retail AI (Catalogue de produits & stocks)", titleEn: "Retail AI (Product Catalog & Inventory)", descFr: "Permet de renseigner l'appelant sur les prix, stocks et commandes.", descEn: "Provides caller with stock, product pricing, and orders." },
                  { id: "central_memory", icon: Bot, titleFr: "Mémoire Mem0 & FAQ Entreprise", titleEn: "Mem0 Memory & Company FAQ", descFr: "Permet de se souvenir des préférences clients et des réponses validées de l'entreprise.", descEn: "Remembers customer preferences and approved company answers." },
                ].map((mod) => {
                  const isChecked = allowedModules.includes(mod.id);
                  const Icon = mod.icon;
                  return (
                    <div
                      key={mod.id}
                      onClick={() => toggleModule(mod.id)}
                      className={`p-4 rounded-2xl border cursor-pointer transition flex items-center justify-between gap-3 ${
                        isChecked
                          ? "border-[#0076FF] bg-blue-50/50 dark:bg-blue-950/30"
                          : "border-slate-200 dark:border-slate-800"
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <div className="p-2.5 rounded-xl bg-blue-100 dark:bg-blue-950 text-[#0076FF] dark:text-[#00D4FF]">
                          <Icon className="w-5 h-5" />
                        </div>
                        <div>
                          <p className="font-bold text-sm text-slate-900 dark:text-white">
                            {fr ? mod.titleFr : mod.titleEn}
                          </p>
                          <p className="text-xs text-slate-500 dark:text-slate-400">
                            {fr ? mod.descFr : mod.descEn}
                          </p>
                        </div>
                      </div>
                      <div className={`w-5 h-5 rounded-md border flex items-center justify-center shrink-0 ${
                        isChecked ? "bg-[#0076FF] border-[#0076FF] text-white" : "border-slate-300 dark:border-slate-700"
                      }`}>
                        {isChecked && <Check className="w-3.5 h-3.5" />}
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="flex justify-between pt-3">
                <button
                  onClick={() => setActiveStep(3)}
                  className="px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-800 text-xs font-semibold"
                >
                  {fr ? "Précédent" : "Back"}
                </button>
                <button
                  onClick={() => setActiveStep(5)}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#0076FF] text-white font-bold text-xs shadow-md"
                >
                  <span>{fr ? "Continuer vers le numéro" : "Continue to Phone Number"}</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}

          {/* STEP 5: PHONE NUMBER STATUS & SETUP */}
          {activeStep === 5 && (
            <div className="space-y-6 animate-in fade-in duration-200">
              <div>
                <h3 className="text-lg font-extrabold text-slate-900 dark:text-white">
                  {fr ? "Étape 5 : Ligne téléphonique et acheminement DTMF (NIP)" : "Step 5: Phone Line & DTMF Company Routing (PIN)"}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  {fr ? "Gérez l'accès téléphonique direct et la passerelle centralisée de standard d'entreprise Avenqo." : "Manage direct phone access and the central Avenqo enterprise receptionist gateway."}
                </p>
              </div>

              {/* FEEDBACK ALERT */}
              {nipFeedback && (
                <div
                  className={`p-4 rounded-2xl text-xs font-semibold flex items-center justify-between gap-3 animate-in fade-in ${
                    nipFeedback.type === "success"
                      ? "bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-200"
                      : "bg-red-50 dark:bg-red-950/60 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-200"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    {nipFeedback.type === "success" ? <CheckCircle className="w-4 h-4 text-emerald-600" /> : <ShieldAlert className="w-4 h-4 text-red-600" />}
                    <span>{nipFeedback.message}</span>
                  </div>
                  <button
                    onClick={() => setNipFeedback(null)}
                    className="text-[11px] underline opacity-75 hover:opacity-100"
                  >
                    {fr ? "Fermer" : "Dismiss"}
                  </button>
                </div>
              )}

              {/* CARD 1: CENTRAL GATEWAY & DTMF ROUTING NIP */}
              <div className="p-6 rounded-3xl border-2 border-purple-200 dark:border-purple-900/60 bg-gradient-to-br from-purple-50/40 via-white to-blue-50/30 dark:from-purple-950/30 dark:via-[#0B132B] dark:to-[#0B132B] space-y-5 shadow-xs">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-2xl bg-purple-100 dark:bg-purple-900/50 text-purple-600 dark:text-purple-400 flex items-center justify-center shrink-0">
                      <PhoneIncoming className="w-5 h-5" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-extrabold uppercase tracking-widest text-purple-700 dark:text-purple-300">
                          {fr ? "Standard Central Partagé" : "Central Shared Gateway"}
                        </span>
                        <span className="px-2 py-0.5 rounded-full bg-purple-100 dark:bg-purple-900/70 text-purple-700 dark:text-purple-300 text-[10px] font-bold">
                          {fr ? "Acheminement DTMF" : "DTMF Routing"}
                        </span>
                      </div>
                      <h4 className="text-base font-extrabold text-slate-900 dark:text-white mt-0.5">
                        {fr ? "Code NIP d'entreprise pour le +1 438-607-5438" : "Company Routing PIN for +1 438-607-5438"}
                      </h4>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <div className="px-3 py-1 rounded-xl bg-purple-100/70 dark:bg-purple-900/40 border border-purple-200 dark:border-purple-800 text-purple-800 dark:text-purple-200 text-xs font-mono font-bold">
                      {dispatcherNumber}
                    </div>
                  </div>
                </div>

                <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                  {fr
                    ? "Permet à vos appelants et employés d'appeler le numéro central Avenqo (+1 438-607-5438). Dès qu'ils saisissent votre NIP d'entreprise suivi de la touche dièse (#), ils sont automatiquement routés vers l'assistant vocal IA isolé de votre entreprise."
                    : "Allows callers and team members to dial Avenqo's central number (+1 438-607-5438). Upon dialing your unique company PIN followed by hash (#), they are instantly routed to your isolated tenant voice assistant."}
                </p>

                {/* CURRENT NIP DISPLAY */}
                <div className="p-4 rounded-2xl bg-white/80 dark:bg-slate-900/80 border border-purple-100 dark:border-purple-900/50 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div>
                    <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                      {fr ? "Code NIP d'accès actif" : "Active Routing PIN"}
                    </span>
                    {routingNip ? (
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-2xl font-mono font-black text-purple-700 dark:text-purple-300 tracking-wider">
                          {routingNip}#
                        </span>
                        <span className="px-2 py-0.5 rounded-md bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 text-[11px] font-bold">
                          {fr ? "Actif & Routable" : "Active & Routable"}
                        </span>
                      </div>
                    ) : (
                      <p className="text-sm font-semibold text-slate-500 mt-1">
                        {fr ? "Aucun code NIP actif configuré" : "No active routing PIN configured"}
                      </p>
                    )}
                  </div>

                  <div className="flex items-center gap-2 flex-wrap">
                    {routingNip && (
                      <button
                        onClick={copyCallingInstructions}
                        className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-purple-50 hover:bg-purple-100 dark:bg-purple-950/60 dark:hover:bg-purple-900/60 border border-purple-200 dark:border-purple-800 text-purple-700 dark:text-purple-300 text-xs font-bold transition shadow-xs"
                      >
                        {copiedNip ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                        <span>{copiedNip ? (fr ? "Copié !" : "Copied!") : (fr ? "Copier les instructions" : "Copy Instructions")}</span>
                      </button>
                    )}
                    <button
                      onClick={generateRandomNip}
                      disabled={nipBusy}
                      className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#0076FF] hover:bg-blue-600 text-white text-xs font-bold transition shadow-xs disabled:opacity-50"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${nipBusy ? "animate-spin" : ""}`} />
                      <span>{routingNip ? (fr ? "Régénérer NIP (5 chiffres)" : "Rotate PIN (5 digits)") : (fr ? "Générer NIP aléatoire" : "Generate Random PIN")}</span>
                    </button>
                    {routingNip && (
                      <button
                        onClick={revokeNip}
                        disabled={nipBusy}
                        className="p-2 rounded-xl border border-red-200 dark:border-red-900/60 hover:bg-red-50 dark:hover:bg-red-950/50 text-red-600 dark:text-red-400 transition"
                        title={fr ? "Révoquer ce NIP" : "Revoke PIN"}
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>

                {/* CUSTOM NIP FORM */}
                <div className="pt-2 border-t border-purple-100 dark:border-purple-900/40">
                  <span className="text-[11px] font-bold text-slate-600 dark:text-slate-400 block mb-2">
                    {fr ? "Ou définir un code NIP personnalisé (4 à 8 chiffres) :" : "Or set custom routing PIN (4 to 8 digits):"}
                  </span>
                  <div className="flex items-center gap-2 max-w-md">
                    <input
                      type="text"
                      pattern="[0-9]*"
                      maxLength={8}
                      placeholder="Ex: 58392"
                      value={customNipInput}
                      onChange={(e) => setCustomNipInput(e.target.value.replace(/\D/g, ""))}
                      className="flex-1 px-3.5 py-2 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs font-mono font-bold text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-hidden focus:border-[#0076FF]"
                    />
                    <button
                      onClick={setCustomNip}
                      disabled={nipBusy || customNipInput.length < 4}
                      className="px-4 py-2 rounded-xl bg-slate-900 hover:bg-black dark:bg-white dark:hover:bg-slate-200 text-white dark:text-slate-900 text-xs font-bold transition disabled:opacity-50"
                    >
                      {fr ? "Appliquer NIP" : "Apply PIN"}
                    </button>
                  </div>
                </div>

                {/* CALLER FLOW STEPS */}
                <div className="p-4 rounded-2xl bg-purple-50/50 dark:bg-purple-950/20 border border-purple-100 dark:border-purple-900/30">
                  <p className="text-[11px] font-bold text-purple-900 dark:text-purple-200 uppercase tracking-wider mb-2">
                    {fr ? "Comment fonctionne l'appel de vos clients :" : "How caller flow operates:"}
                  </p>
                  <ol className="text-xs text-slate-600 dark:text-slate-300 space-y-1.5 list-decimal list-inside">
                    <li>{fr ? "Le client compose le " : "Caller dials "}<strong>{dispatcherNumber}</strong></li>
                    <li>{fr ? "Le standard vocal Avenqo répond : « Bienvenue sur Avenqo. Entrez votre NIP d'entreprise suivi de # »" : "Avenqo interactive receptionist answers asking for company routing PIN followed by #"}</li>
                    <li>{fr ? "Le client tape son code : " : "Caller enters PIN: "}<strong>{routingNip ? `${routingNip}#` : "votre code NIP#"}</strong></li>
                    <li>{fr ? "L'assistant IA dédié de votre entreprise s'active immédiatement avec vos réservations CRM et produits." : "Your company's isolated AI receptionist engages live with your real CRM & Retail data."}</li>
                  </ol>
                </div>
              </div>

              {/* CARD 2: DEDICATED PHONE LINE / SANDBOX STATUS */}
              <div className="p-6 rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                      {fr ? "Ligne dédiée d'entreprise (Telnyx Direct)" : "Dedicated Company Line (Direct Telnyx)"}
                    </span>
                    <p className="text-xl font-mono font-extrabold text-slate-900 dark:text-white mt-1">
                      {currentStatus?.business_number || "+1 (514) 800-AVENQO (Sandbox)"}
                    </p>
                  </div>
                  <span className="px-3 py-1 rounded-full bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 text-xs font-bold">
                    {fr ? "Opérationnel" : "Operational"}
                  </span>
                </div>

                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {fr
                    ? "En environnement Sandbox, le provisionnement réel de numéro Telnyx dédié est sécurisé et simulé afin d'éviter tout frais récurrent non autorisé. La ligne répond aux tests de standard sans surcoût."
                    : "In Sandbox, real Telnyx telephone provisioning is safely simulated to protect against unauthorized charges while allowing full call flow testing."}
                </p>
              </div>

              <div className="flex justify-between pt-3">
                <button
                  onClick={() => setActiveStep(4)}
                  className="px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-800 text-xs font-semibold"
                >
                  {fr ? "Précédent" : "Back"}
                </button>
                <button
                  onClick={() => setActiveStep(6)}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#0076FF] text-white font-bold text-xs shadow-md"
                >
                  <span>{fr ? "Tester l'assistant vocal" : "Test Voice Assistant"}</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}

          {/* STEP 6: TEST VOICE ASSISTANT */}
          {activeStep === 6 && (
            <div className="space-y-5 animate-in fade-in duration-200">
              <div>
                <h3 className="text-lg font-extrabold text-slate-900 dark:text-white">
                  {fr ? "Étape 6 : Testez votre réceptionniste vocal" : "Step 6: Test your voice receptionist"}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  {fr ? "Simulez un appel entrant pour vérifier la prise de rendez-vous et les réponses aux questions." : "Simulate an incoming call to verify appointment booking and business answers."}
                </p>
              </div>

              <div className="p-8 rounded-3xl border border-blue-200 dark:border-blue-900/60 bg-gradient-to-b from-blue-50/50 to-white dark:from-blue-950/30 dark:to-[#0B132B] text-center space-y-4">
                <div className="w-16 h-16 rounded-full bg-blue-100 dark:bg-blue-900/50 text-[#0076FF] dark:text-[#00D4FF] mx-auto flex items-center justify-center shadow-md">
                  <Volume2 className="w-8 h-8" />
                </div>

                <div>
                  <h4 className="font-extrabold text-base text-slate-900 dark:text-white">
                    {testCallStatus === "calling"
                      ? fr ? "Appel en cours de connexion..." : "Call connecting..."
                      : testCallStatus === "connected"
                      ? fr ? "Standard connecté — Conversation en cours" : "Receptionist Connected — In Conversation"
                      : testCallStatus === "success"
                      ? fr ? "Test réussi avec succès !" : "Test Completed Successfully!"
                      : fr ? "Prêt pour le test d'appel" : "Ready for Test Call"}
                  </h4>
                  <p className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
                    {fr
                      ? "L'assistant testera l'accueil, la vérification des horaires CRM et la validation de réservation."
                      : "The assistant will test welcome greeting, CRM hours validation, and slot reservation."}
                  </p>
                </div>

                <div className="pt-2">
                  <button
                    onClick={handleSimulateTestCall}
                    disabled={testCallStatus === "calling" || testCallStatus === "connected"}
                    className="inline-flex items-center gap-2 px-6 py-3 rounded-2xl bg-gradient-to-r from-[#0076FF] to-[#00D4FF] text-white font-bold text-sm shadow-lg hover:opacity-95 transition"
                  >
                    <Play className="w-4 h-4 fill-current" />
                    <span>{fr ? "Lancer un appel test simulé" : "Start Simulated Test Call"}</span>
                  </button>
                </div>
              </div>

              <div className="flex justify-between pt-3">
                <button
                  onClick={() => setActiveStep(5)}
                  className="px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-800 text-xs font-semibold"
                >
                  {fr ? "Précédent" : "Back"}
                </button>
                <div className="flex items-center gap-2">
                  <Link
                    href="/crm"
                    className="px-5 py-2.5 rounded-xl bg-emerald-600 text-white font-bold text-xs shadow-md"
                  >
                    {fr ? "Terminer & Voir le Calendrier" : "Finish & View Calendar"}
                  </Link>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ADVANCED SETTINGS (COLLAPSIBLE FOR ADMINS) */}
      <div className="rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B132B] shadow-xs overflow-hidden">
        <button
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="w-full p-5 flex items-center justify-between text-left hover:bg-slate-50/50 dark:hover:bg-slate-900/50 transition"
        >
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400">
              <Sliders className="w-5 h-5" />
            </div>
            <div>
              <p className="font-bold text-sm text-slate-900 dark:text-white">
                {fr ? "Paramètres avancés & Téléphonie technique" : "Advanced Settings & Telephony Configuration"}
              </p>
              <p className="text-xs text-slate-500">
                {fr
                  ? "Gestion des PIN individuels, Call Control Telnyx et recherche de numéros (Administrateurs)."
                  : "Individual PIN management, Telnyx Call Control, and number search (Admins only)."}
              </p>
            </div>
          </div>
          {showAdvanced ? <ChevronUp className="w-5 h-5 text-slate-400" /> : <ChevronDown className="w-5 h-5 text-slate-400" />}
        </button>

        {showAdvanced && (
          <div className="p-6 border-t border-slate-200 dark:border-slate-800 space-y-7 bg-slate-50/30 dark:bg-slate-900/30 animate-in fade-in duration-200">
            {/* NUMBER SELECTION & PROVISIONING QUOTES */}
            <section className="space-y-4 border-b border-slate-200 dark:border-slate-800 pb-7">
              <h2 className="font-semibold text-slate-900 dark:text-white">{selectionCopy[0]}</h2>
              {!enabled || !canManageVoice ? (
                <Link href="/settings" className="inline-flex items-center gap-2 text-sm underline">
                  <Settings size={15} />
                  {t.navigation.settings}
                </Link>
              ) : (
                <>
                  <form onSubmit={search} className="grid gap-3 sm:grid-cols-3">
                    {([
                      ["country_code", copy.country],
                      ["region", copy.region],
                      ["locality", copy.locality],
                      ["area_code", selectionCopy[1]],
                      ["prefix", selectionCopy[2]],
                    ] as const).map(([key, label]) => (
                      <label key={key} className="space-y-1 text-xs">
                        <span>{label}</span>
                        <input
                          aria-label={label}
                          required={key === "country_code"}
                          maxLength={key === "country_code" ? 2 : 80}
                          value={filters[key]}
                          onChange={(event) => setFilters({ ...filters, [key]: event.target.value })}
                          className="w-full rounded-xl border border-slate-300 dark:border-slate-700 bg-transparent p-2 text-sm"
                        />
                      </label>
                    ))}
                    <label className="space-y-1 text-xs">
                      <span>{typeCopy[0]}</span>
                      <select
                        aria-label={typeCopy[0]}
                        value={filters.number_type}
                        onChange={(event) => setFilters({ ...filters, number_type: event.target.value })}
                        className="w-full rounded-xl border border-slate-300 dark:border-slate-700 bg-transparent p-2 text-sm"
                      >
                        {numberTypes.map((value) => (
                          <option key={value} value={value}>
                            {numberTypeLabel(value)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <div className="flex gap-4 text-xs">
                      {["voice", "sms", "mms"].map((feature) => (
                        <label key={feature} className="flex items-center gap-1">
                          <input
                            type="checkbox"
                            checked={features.includes(feature)}
                            onChange={(event) =>
                              setFeatures(
                                event.target.checked
                                  ? [...features, feature]
                                  : features.filter((item) => item !== feature)
                              )
                            }
                          />
                          {feature.toUpperCase()}
                        </label>
                      ))}
                    </div>
                    <button
                      disabled={busy || filters.country_code.length !== 2}
                      className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-300 dark:border-slate-700 px-3 py-2 text-sm disabled:opacity-40"
                    >
                      <Search size={16} />
                      {copy.search}
                    </button>
                  </form>
                  {result?.tenant === tenantId && offers.length === 0 && (
                    <p role="status" className="text-sm">
                      {company.connectionsNoDataTitle}
                    </p>
                  )}
                  <div className="divide-y divide-slate-200 dark:divide-white/10">
                    {offers.map((offer, index) => (
                      <label key={`${offer.phone_number}-${index}`} className="flex items-start gap-3 py-4 text-sm">
                        <input
                          type="radio"
                          name="voice-number"
                          aria-label={`${selectionCopy[3]} ${offer.phone_number}`}
                          checked={selected === offer.phone_number}
                          disabled={!offer.is_orderable}
                          onChange={() => setSelected(offer.phone_number)}
                          className="mt-1"
                        />
                        <div className="min-w-0 space-y-1 break-words">
                          <div className="font-mono font-semibold">{offer.phone_number}</div>
                          <div>
                            {[offer.country_code, offer.region, offer.locality, numberTypeLabel(offer.number_type)]
                              .filter(Boolean)
                              .join(" · ")}
                          </div>
                          <div>{offer.capabilities.join(" · ")}</div>
                          <div>
                            {selectionCopy[4]}: {price(offer, "upfront_cost")} · {copy.monthlyPrice}: {price(offer, "monthly_cost")}
                          </div>
                          <div className="text-xs text-slate-500">
                            {copy.regulatoryRequirements}:{" "}
                            {offer.regulatory_status === "unknown"
                              ? t.common.insufficientData
                              : JSON.stringify(offer.regulatory_requirements)}
                          </div>
                        </div>
                      </label>
                    ))}
                  </div>
                  {selected && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void requestQuote()}
                      className="rounded-xl border border-slate-300 dark:border-slate-700 px-3 py-2 text-sm disabled:opacity-40"
                    >
                      {selectionCopy[0]}
                    </button>
                  )}
                  {quote && (
                    <section className="space-y-2 border-t border-slate-200 pt-4 text-sm dark:border-white/10">
                      <p>
                        {quote.offer.phone_number} · {selectionCopy[4]}: {price(quote.offer, "upfront_cost")} ·{" "}
                        {copy.monthlyPrice}: {price(quote.offer, "monthly_cost")} · {quote.expires_in_seconds}s
                      </p>
                      <p>
                        {copy.regulatoryRequirements}:{" "}
                        {quote.offer.regulatory_status === "verified_no_requirements"
                          ? "0"
                          : t.common.insufficientData}
                      </p>
                      {quote.purchase_allowed && (
                        <p className="text-sm">
                          {locale === "fr"
                            ? "Utilisez le parcours de paiement de votre numéro professionnel ci-dessus."
                            : "Use the business-number payment flow above."}
                        </p>
                      )}
                    </section>
                  )}
                </>
              )}
            </section>

            {/* PIN ENROLLMENT */}
            <section className="space-y-3">
              <div className="flex items-center gap-2">
                <Lock className="w-4 h-4 text-[#0076FF]" />
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">
                  {fr ? "Enrôlement PIN téléphonique individuel" : "Individual Voice PIN Enrollment"}
                </h4>
              </div>
              <p className="text-xs text-slate-500">
                {fr
                  ? "Chaque collaborateur configure son propre code PIN sécurisé pour s'authentifier par téléphone."
                  : "Each authorized employee sets an individual secure PIN for telephone authentication."}
              </p>

              <form onSubmit={saveVoicePin} className="flex flex-wrap items-end gap-3 pt-1">
                <label className="min-w-48 space-y-1 text-xs">
                  <span>{locale === "fr" ? "Mot de passe actuel" : "Current password"}</span>
                  <input
                    aria-label={locale === "fr" ? "Mot de passe actuel" : "Current password"}
                    name="voice-account-password"
                    type="password"
                    autoComplete="current-password"
                    required
                    className="w-full rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 p-2 text-sm"
                  />
                </label>
                <label className="min-w-48 space-y-1 text-xs">
                  <span>{messages[4]}</span>
                  <input
                    aria-label={messages[4]}
                    name="voice-pin"
                    type="password"
                    inputMode="numeric"
                    pattern="[0-9]{6,12}"
                    minLength={6}
                    maxLength={12}
                    autoComplete="new-password"
                    required
                    className="w-full rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 p-2 text-sm"
                  />
                </label>
                <button
                  type="submit"
                  className="px-4 py-2 text-xs font-bold rounded-xl bg-slate-900 dark:bg-white text-white dark:text-slate-900"
                >
                  {messages[5]}
                </button>
                {pinMessage && <span role="status" className="text-xs text-blue-600 dark:text-blue-400 font-semibold">{pinMessage}</span>}
              </form>
            </section>

            {/* CALL POLICY, PROVISIONING & PERMISSIONS */}
            {enabled && <VoiceBusinessOnboarding key={tenantId} tenantId={tenantId} canManage={canManageVoice} />}
            {enabled && <VoiceCustomizationSection tenantId={tenantId} />}
            {enabled && <VoiceProvisioningSection tenantId={tenantId} canManage={canManageVoice} crmEnabled={Boolean(context?.enabled_modules.includes("crm"))} />}
            {enabled && <VoiceCallPolicy key={tenantId} tenantId={tenantId} canManage={canManageVoice} />}
            {enabled && <VoiceModulePermissionsSection tenantId={tenantId} canManage={canManageVoice} />}
          </div>
        )}
      </div>
    </div>
  );
}
