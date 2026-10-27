"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import Link from "next/link";
import {
  Building2,
  Bot,
  Layers,
  PhoneCall,
  CheckCircle2,
  AlertCircle,
  Play,
  Pause,
  ArrowRight,
  ArrowLeft,
  Sparkles,
  RefreshCw,
  ShieldCheck,
  ShieldAlert,
  Users,
  Store,
  Calendar,
  Lock,
  ChevronDown,
  ChevronUp,
  Radio,
  Check,
  Volume2,
  Copy,
  Sliders,
  ExternalLink,
  Clock,
} from "lucide-react";
import { useLocale } from "@/lib/i18n/locale-context";
import { apiFetch } from "@/lib/api-request";
import { VoiceLifecycleCard } from "@/components/voice/voice-lifecycle-card";

interface WizardProps {
  tenantId?: string;
  canManage: boolean;
  businessName?: string;
  onRefreshStatus?: () => void;
}

interface BusinessProfile {
  business_name: string;
  industry: string;
  description: string;
  activities: string[];
  locations: string[];
  timezone: string;
  opening_hours: Record<string, any>;
  primary_locale: string;
  secondary_locales: string[];
  contact_phone: string | null;
  website: string;
  bookable_service_ids: string[];
  allowed_actions: string[];
  communication_style: string;
}

interface CustomizationConfig {
  voice_id: string;
  speech_speed: number;
  personality_tone: string;
  greeting_message?: string;
  farewell_message?: string;
  custom_pronunciation?: Record<string, string>;
}

interface VoiceItem {
  id: string;
  name: string;
  provider: string;
  gender: string;
  sample_url?: string | null;
  description?: string;
}

export function VoiceOnboardingWizard({
  tenantId,
  canManage,
  businessName = "Entreprise",
  onRefreshStatus,
}: WizardProps) {
  const { locale } = useLocale();
  const fr = locale.startsWith("fr");

  const [currentStep, setCurrentStep] = useState<number>(1);
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [saveFeedback, setSaveFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  // Step 1: Business Profile State
  const [profile, setProfile] = useState<BusinessProfile>({
    business_name: businessName,
    industry: "Commerce & Équipement sportif",
    description: "Vente d'équipements de sport, snowboards, fixations et entretien technique.",
    activities: ["Vente au détail", "Conseil équipement", "Entretien et réparation"],
    locations: ["Montréal"],
    timezone: "America/Montreal",
    opening_hours: {},
    primary_locale: "fr-CA",
    secondary_locales: ["en-US"],
    contact_phone: "+1 438-607-5438",
    website: "",
    bookable_service_ids: [],
    allowed_actions: ["crm.appointments.view", "crm.appointments.create", "retail.products.query"],
    communication_style: "professionnel",
  });

  // Step 1: Real Business Hours Schedule State (Not pre-selected!)
  const [openingHours, setOpeningHours] = useState<Record<string, { open: string; close: string } | null>>({});

  // Step 2: Receptionist Customization State
  const [voices, setVoices] = useState<VoiceItem[]>([]);
  const [customization, setCustomization] = useState<CustomizationConfig>({
    voice_id: "shimmer",
    speech_speed: 1.0,
    personality_tone: "professionnel",
    greeting_message: "Bonjour et bienvenue chez Produits Ero ! Comment puis-je vous aider aujourd'hui ?",
    farewell_message: "Merci pour votre appel et à très bientôt chez Produits Ero.",
  });
  const [playingVoice, setPlayingVoice] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Step 3: 4 Business Capabilities State (Zero Technical Clutter)
  const [retailEnabled, setRetailEnabled] = useState<boolean>(true);
  const [crmEnabled, setCrmEnabled] = useState<boolean>(true);
  const [customerServiceEnabled, setCustomerServiceEnabled] = useState<boolean>(true);
  const [internalInsightsEnabled, setInternalInsightsEnabled] = useState<boolean>(false);

  // Step 4: Telephony & Employees (Canonical Architecture)
  const [assignedNumber, setAssignedNumber] = useState<string>("+1 438-607-5438");
  const [employeePin, setEmployeePin] = useState<string>("");
  const [employeePinSaving, setEmployeePinSaving] = useState<boolean>(false);
  const [employeePinFeedback, setEmployeePinFeedback] = useState<string | null>(null);

  // Advanced Section toggle (Shared Dispatcher & DTMF fallback)
  const [showAdvancedAccordion, setShowAdvancedAccordion] = useState<boolean>(false);
  const [routingNip, setRoutingNip] = useState<string | null>(null);
  const [dispatcherNumber, setDispatcherNumber] = useState<string>("+1 438-607-5438");

  // Load initial configuration from server APIs
  const loadConfiguration = useCallback(async () => {
    if (!tenantId) return;
    setLoading(true);
    try {
      const [profileRes, customRes, voicesRes, statusRes] = await Promise.all([
        apiFetch("/api/v1/voice/business-profile").catch(() => null),
        apiFetch("/api/v1/voice/customization").catch(() => null),
        apiFetch("/api/v1/voice/voices").catch(() => null),
        apiFetch("/api/v1/voice/status").catch(() => null),
      ]);

      if (profileRes && profileRes.ok) {
        const data = await profileRes.json();
        if (data.profile) {
          setProfile((prev) => ({
            ...prev,
            ...data.profile,
            business_name: data.profile.business_name || businessName,
          }));
          if (data.profile.opening_hours && typeof data.profile.opening_hours === "object") {
            setOpeningHours(data.profile.opening_hours);
          }
          if (Array.isArray(data.profile.allowed_actions)) {
            const acts = data.profile.allowed_actions;
            setRetailEnabled(acts.some((a: string) => a.startsWith("retail") || a.includes("product")));
            setCrmEnabled(acts.some((a: string) => a.startsWith("crm") || a.includes("appointment")));
            setCustomerServiceEnabled(acts.length === 0 || acts.some((a: string) => a.includes("client") || a.includes("business.info")));
            setInternalInsightsEnabled(acts.some((a: string) => a.includes("sales_summary") || a.includes("cashflow") || a.includes("business_health")));
          }
        }
      }

      if (customRes && customRes.ok) {
        const data = await customRes.json();
        if (data) {
          setCustomization((prev) => ({
            ...prev,
            voice_id: data.voice_id || prev.voice_id,
            speech_speed: data.speech_speed || prev.speech_speed,
            personality_tone: data.personality_tone || prev.personality_tone,
            greeting_message: data.greeting_message || prev.greeting_message,
            farewell_message: data.farewell_message || prev.farewell_message,
          }));
        }
      }

      if (voicesRes && voicesRes.ok) {
        const data = await voicesRes.json();
        if (Array.isArray(data)) {
          setVoices(data);
        }
      }

      if (statusRes && statusRes.ok) {
        const statusData = await statusRes.json();
        if (statusData.business_number) setAssignedNumber(statusData.business_number);
        if (statusData.routing_nip) setRoutingNip(statusData.routing_nip);
        if (statusData.dispatcher_number) setDispatcherNumber(statusData.dispatcher_number);
      }
    } catch {
      // Graceful fallback
    } finally {
      setLoading(false);
    }
  }, [tenantId, businessName]);

  useEffect(() => {
    void loadConfiguration();
  }, [loadConfiguration]);

  // Audio preview playback
  const togglePlayVoice = (voiceId: string) => {
    if (playingVoice === voiceId) {
      if (audioRef.current) {
        audioRef.current.pause();
      }
      setPlayingVoice(null);
      return;
    }

    const voice = voices.find((v) => v.id === voiceId);
    if (!voice?.sample_url) {
      // Browser SpeechSynthesis fallback preview
      if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(
          customization.greeting_message || (fr ? "Bonjour, comment puis-je vous aider ?" : "Hello, how can I help you?")
        );
        utterance.lang = profile.primary_locale || "fr-CA";
        utterance.rate = customization.speech_speed;
        utterance.onend = () => setPlayingVoice(null);
        window.speechSynthesis.speak(utterance);
        setPlayingVoice(voiceId);
      }
      return;
    }

    if (audioRef.current) {
      audioRef.current.pause();
    }
    const audio = new Audio(voice.sample_url);
    audioRef.current = audio;
    audio.onended = () => setPlayingVoice(null);
    audio.play().catch(() => setPlayingVoice(null));
    setPlayingVoice(voiceId);
  };

  // Save Step 1 & 3: Business Profile
  const saveBusinessProfile = async () => {
    setSaving(true);
    setSaveFeedback(null);
    try {
      const allowedActions: string[] = [];
      if (retailEnabled) {
        allowedActions.push("retail.products.query");
      }
      if (crmEnabled) {
        allowedActions.push("crm.appointments.view", "crm.appointments.create");
      }
      if (customerServiceEnabled) {
        allowedActions.push("read_client_self", "business.info.query");
      }
      if (internalInsightsEnabled) {
        allowedActions.push("read_sales_summary", "read_cashflow", "read_business_health");
      }

      // Clean and validate real business hours
      const cleanOpeningHours: Record<string, { open: string; close: string }> = {};
      const validDays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
      for (const day of validDays) {
        const period = openingHours[day];
        if (period && period.open && period.close) {
          cleanOpeningHours[day] = {
            open: period.open.trim(),
            close: period.close.trim(),
          };
        }
      }

      const payload = {
        ...profile,
        opening_hours: cleanOpeningHours,
        allowed_actions: allowedActions,
      };

      const res = await apiFetch("/api/v1/voice/business-profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || (fr ? "Erreur de sauvegarde de l'entreprise." : "Failed to save business profile."));
      }

      setSaveFeedback({
        type: "success",
        message: fr ? "Profil d'entreprise et horaires réels sauvegardés." : "Business profile and hours saved.",
      });
      onRefreshStatus?.();
      return true;
    } catch (err) {
      setSaveFeedback({
        type: "error",
        message: err instanceof Error ? err.message : String(err),
      });
      return false;
    } finally {
      setSaving(false);
    }
  };

  // Save Step 2: Customization
  const saveReceptionistCustomization = async () => {
    setSaving(true);
    setSaveFeedback(null);
    try {
      const payload = {
        voice_id: customization.voice_id,
        voice_provider: "openai",
        speech_speed: customization.speech_speed,
        personality_tone: customization.personality_tone,
        greeting_message: customization.greeting_message,
        farewell_message: customization.farewell_message,
        custom_pronunciation: customization.custom_pronunciation || {},
      };

      const res = await apiFetch("/api/v1/voice/customization", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || (fr ? "Erreur de sauvegarde de la voix." : "Failed to save voice customization."));
      }

      setSaveFeedback({
        type: "success",
        message: fr ? "Configuration vocale enregistrée." : "Voice configuration saved.",
      });
      onRefreshStatus?.();
      return true;
    } catch (err) {
      setSaveFeedback({
        type: "error",
        message: err instanceof Error ? err.message : String(err),
      });
      return false;
    } finally {
      setSaving(false);
    }
  };

  // Configure Personal Employee PIN (Step 4)
  const savePersonalPin = async () => {
    if (!employeePin || employeePin.length < 4 || employeePin.length > 8) {
      setEmployeePinFeedback(
        fr ? "Le code NIP doit comporter de 4 à 8 chiffres." : "PIN must be between 4 and 8 digits."
      );
      return;
    }
    setEmployeePinSaving(true);
    setEmployeePinFeedback(null);
    try {
      const res = await apiFetch("/api/v1/voice/auth/pin", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pin: employeePin,
          confirm_pin: employeePin,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || (fr ? "Impossible d'enregistrer le NIP." : "Could not save employee PIN."));
      }
      setEmployeePinFeedback(
        fr
          ? "NIP personnel configuré avec succès ! Haché de manière sécurisée (Argon2)."
          : "Personal PIN successfully set! Securely hashed with Argon2."
      );
      setEmployeePin("");
      onRefreshStatus?.();
    } catch (err) {
      setEmployeePinFeedback(err instanceof Error ? err.message : String(err));
    } finally {
      setEmployeePinSaving(false);
    }
  };

  const steps = [
    { id: 1, title: fr ? "1. Mon entreprise" : "1. My Business", icon: Building2, desc: fr ? "Identité & coordonnées" : "Identity & details" },
    { id: 2, title: fr ? "2. Ma réceptionniste" : "2. My Receptionist", icon: Bot, desc: fr ? "Voix, timbre & accueil" : "Voice, tone & greeting" },
    { id: 3, title: fr ? "3. Connaissances & modules" : "3. Knowledge & Modules", icon: Layers, desc: fr ? "Retail, CRM & règles" : "Retail, CRM & bounds" },
    { id: 4, title: fr ? "4. Téléphone & employés" : "4. Phone & Employees", icon: PhoneCall, desc: fr ? "Routage IVR & NIP privé" : "IVR routing & private PIN" },
    { id: 5, title: fr ? "5. Tester et activer" : "5. Test & Activate", icon: CheckCircle2, desc: fr ? "Checklist & mise en ligne" : "Checklist & activation" },
  ];

  return (
    <div className="space-y-6">
      {/* 5-STEP NAVIGATION HEADER */}
      <div className="rounded-3xl border border-slate-200/80 dark:border-white/[0.08] bg-white dark:bg-[#0B132B] shadow-sm overflow-hidden">
        <div className="p-6 border-b border-slate-100 dark:border-white/[0.06] flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-extrabold uppercase tracking-wider bg-blue-50 text-[#0076FF] dark:bg-blue-950/60 dark:text-blue-300 border border-blue-200/60 dark:border-blue-800/40">
                {fr ? "Assistant Vocal Avenqo" : "Avenqo Voice Assistant"}
              </span>
              <span className="text-xs font-mono font-bold text-slate-400">
                {businessName}
              </span>
            </div>
            <h2 className="text-xl font-extrabold text-slate-900 dark:text-white mt-1">
              {fr ? "Configuration simple de votre réceptionniste" : "Simple Receptionist Setup"}
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              {fr
                ? "Configurez votre ligne téléphonique en 5 étapes claires. Vos réglages sont validés côté serveur."
                : "Set up your phone line in 5 clear steps. Every setting is server-verified."}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-slate-500">
              {fr ? `Étape ${currentStep} sur 5` : `Step ${currentStep} of 5`}
            </span>
          </div>
        </div>

        {/* STEP TABS */}
        <div className="flex border-b border-slate-100 dark:border-white/[0.06] overflow-x-auto scrollbar-none bg-slate-50/50 dark:bg-slate-900/40 p-2 gap-1.5">
          {steps.map((st) => {
            const Icon = st.icon;
            const isActive = currentStep === st.id;
            const isCompleted = currentStep > st.id;
            return (
              <button
                key={st.id}
                onClick={() => {
                  setSaveFeedback(null);
                  setCurrentStep(st.id);
                }}
                className={`flex-1 min-w-[140px] px-3.5 py-2.5 rounded-2xl text-left transition flex items-center gap-2.5 ${
                  isActive
                    ? "bg-[#0076FF] text-white shadow-md shadow-blue-500/20"
                    : isCompleted
                    ? "bg-blue-50/60 dark:bg-blue-950/30 text-blue-800 dark:text-blue-300 hover:bg-blue-100/60"
                    : "text-slate-600 dark:text-slate-400 hover:bg-slate-200/50 dark:hover:bg-slate-800"
                }`}
              >
                <div
                  className={`w-7 h-7 rounded-xl flex items-center justify-center shrink-0 ${
                    isActive
                      ? "bg-white/20 text-white"
                      : isCompleted
                      ? "bg-blue-200/60 dark:bg-blue-900/60 text-blue-700 dark:text-blue-300"
                      : "bg-slate-200 dark:bg-slate-800 text-slate-500"
                  }`}
                >
                  {isCompleted ? <Check className="w-3.5 h-3.5" /> : <Icon className="w-3.5 h-3.5" />}
                </div>
                <div className="min-w-0">
                  <div className="text-xs font-bold truncate leading-tight">{st.title}</div>
                  <div
                    className={`text-[10px] truncate leading-tight mt-0.5 ${
                      isActive ? "text-blue-100" : "text-slate-400 dark:text-slate-500"
                    }`}
                  >
                    {st.desc}
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        {/* FEEDBACK BANNER */}
        {saveFeedback && (
          <div
            className={`mx-6 mt-4 p-3.5 rounded-2xl text-xs font-semibold flex items-center gap-2.5 animate-in fade-in ${
              saveFeedback.type === "success"
                ? "bg-emerald-50 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800/60"
                : "bg-rose-50 text-rose-800 dark:bg-rose-950/50 dark:text-rose-300 border border-rose-200 dark:border-rose-800/60"
            }`}
          >
            {saveFeedback.type === "success" ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            ) : (
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            )}
            <span>{saveFeedback.message}</span>
          </div>
        )}

        {/* STEP CONTENT BODY */}
        <div className="p-6 sm:p-7">
          {/* ========================================================
              STEP 1: MON ENTREPRISE
              ======================================================== */}
          {currentStep === 1 && (
            <div className="space-y-6 animate-in fade-in duration-200">
              <div className="border-b border-slate-100 dark:border-white/[0.06] pb-4">
                <h3 className="text-lg font-extrabold text-slate-900 dark:text-white">
                  {fr ? "Étape 1 : Identité et informations de l'entreprise" : "Step 1: Business Identity & Details"}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  {fr
                    ? "La réceptionniste utilise ces informations pour présenter votre entreprise avec exactitude."
                    : "The voice assistant relies on this identity to introduce your company accurately."}
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">
                    {fr ? "Nom commercial de l'entreprise *" : "Business Name *"}
                  </label>
                  <input
                    type="text"
                    value={profile.business_name}
                    onChange={(e) => setProfile((p) => ({ ...p, business_name: e.target.value }))}
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs font-semibold text-slate-900 dark:text-white focus:outline-hidden focus:border-[#0076FF]"
                    placeholder="Ex: Produits Ero"
                  />
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">
                    {fr ? "Secteur d'activité *" : "Industry / Domain *"}
                  </label>
                  <input
                    type="text"
                    value={profile.industry}
                    onChange={(e) => setProfile((p) => ({ ...p, industry: e.target.value }))}
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs font-semibold text-slate-900 dark:text-white focus:outline-hidden focus:border-[#0076FF]"
                    placeholder="Ex: Commerce d'équipement sportif"
                  />
                </div>

                <div className="sm:col-span-2">
                  <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">
                    {fr ? "Description de l'activité" : "Business Description"}
                  </label>
                  <textarea
                    rows={3}
                    value={profile.description}
                    onChange={(e) => setProfile((p) => ({ ...p, description: e.target.value }))}
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs text-slate-900 dark:text-white focus:outline-hidden focus:border-[#0076FF]"
                    placeholder="Décrivez les produits et services proposés aux appelants..."
                  />
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">
                    {fr ? "Fuseau horaire" : "Timezone"}
                  </label>
                  <input
                    type="text"
                    value={profile.timezone}
                    onChange={(e) => setProfile((p) => ({ ...p, timezone: e.target.value }))}
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs font-mono font-semibold text-slate-900 dark:text-white focus:outline-hidden focus:border-[#0076FF]"
                  />
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">
                    {fr ? "Langue principale de l'accueil" : "Primary Spoken Language"}
                  </label>
                  <select
                    value={profile.primary_locale}
                    onChange={(e) => setProfile((p) => ({ ...p, primary_locale: e.target.value }))}
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs font-semibold text-slate-900 dark:text-white focus:outline-hidden focus:border-[#0076FF]"
                  >
                    <option value="fr-CA">Français (Canada) 🇨🇦</option>
                    <option value="fr">Français (France) 🇫🇷</option>
                    <option value="en-US">English (US) 🇺🇸</option>
                    <option value="en-CA">English (Canada) 🇨🇦</option>
                    <option value="ro">Română 🇷🇴</option>
                  </select>
                </div>
              </div>

              {/* REAL BUSINESS HOURS SCHEDULE (CUSTOMIZABLE PER BUSINESS) */}
              <div className="pt-4 border-t border-slate-100 dark:border-white/[0.06] space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <Clock className="w-4 h-4 text-[#0076FF]" />
                      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200">
                        {fr ? "Horaires d'ouverture réels de vos locaux / boutique" : "Actual Physical Business Opening Hours"}
                      </h4>
                    </div>
                    <p className="text-xs text-slate-500 mt-0.5">
                      {fr
                        ? "Définissez les heures réelles où vos portes sont ouvertes pour recevoir vos clients ou exécuter vos services."
                        : "Set the actual hours when your doors are open to greet customers or perform services."}
                    </p>
                  </div>

                  {/* QUICK PRESETS */}
                  <div className="flex items-center gap-2 flex-wrap">
                    <button
                      type="button"
                      onClick={() => {
                        const standard: Record<string, { open: string; close: string }> = {
                          monday: { open: "09:00", close: "17:00" },
                          tuesday: { open: "09:00", close: "17:00" },
                          wednesday: { open: "09:00", close: "17:00" },
                          thursday: { open: "09:00", close: "17:00" },
                          friday: { open: "09:00", close: "17:00" },
                        };
                        setOpeningHours(standard);
                      }}
                      className="px-2.5 py-1 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-[11px] font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-50 transition"
                    >
                      {fr ? "Lun – Ven (9h – 17h)" : "Mon – Fri (9am – 5pm)"}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        const allDays: Record<string, { open: string; close: string }> = {
                          monday: { open: "08:00", close: "18:00" },
                          tuesday: { open: "08:00", close: "18:00" },
                          wednesday: { open: "08:00", close: "18:00" },
                          thursday: { open: "08:00", close: "18:00" },
                          friday: { open: "08:00", close: "18:00" },
                          saturday: { open: "09:00", close: "17:00" },
                          sunday: { open: "10:00", close: "16:00" },
                        };
                        setOpeningHours(allDays);
                      }}
                      className="px-2.5 py-1 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-[11px] font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-50 transition"
                    >
                      {fr ? "7 jours sur 7" : "7 days a week"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setOpeningHours({})}
                      className="px-2.5 py-1 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-[11px] font-semibold text-slate-500 hover:text-slate-800 transition"
                    >
                      {fr ? "Sur rendez-vous uniquement" : "Appointment only"}
                    </button>
                  </div>
                </div>

                {/* 7-DAY SCHEDULE TABLE */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-7 gap-2.5 pt-2">
                  {[
                    { key: "monday", label: fr ? "Lundi" : "Monday" },
                    { key: "tuesday", label: fr ? "Mardi" : "Tuesday" },
                    { key: "wednesday", label: fr ? "Mercredi" : "Wednesday" },
                    { key: "thursday", label: fr ? "Jeudi" : "Thursday" },
                    { key: "friday", label: fr ? "Vendredi" : "Friday" },
                    { key: "saturday", label: fr ? "Samedi" : "Saturday" },
                    { key: "sunday", label: fr ? "Dimanche" : "Sunday" },
                  ].map((day) => {
                    const isOpen = Boolean(openingHours[day.key]);
                    const currentOpen = openingHours[day.key]?.open || "09:00";
                    const currentClose = openingHours[day.key]?.close || "17:00";

                    return (
                      <div
                        key={day.key}
                        className={`p-3 rounded-2xl border transition-all flex flex-col justify-between ${
                          isOpen
                            ? "border-emerald-300 dark:border-emerald-800/80 bg-emerald-50/40 dark:bg-emerald-950/20"
                            : "border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-1 mb-2">
                          <span className="text-xs font-bold text-slate-800 dark:text-slate-200">
                            {day.label}
                          </span>
                          <button
                            type="button"
                            onClick={() => {
                              setOpeningHours((prev) => {
                                const next = { ...prev };
                                if (isOpen) {
                                  delete next[day.key];
                                } else {
                                  next[day.key] = { open: "09:00", close: "17:00" };
                                }
                                return next;
                              });
                            }}
                            className={`px-2 py-0.5 rounded-full text-[10px] font-extrabold transition cursor-pointer ${
                              isOpen
                                ? "bg-emerald-500 text-white"
                                : "bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-400"
                            }`}
                          >
                            {isOpen ? (fr ? "Ouvert" : "Open") : (fr ? "Fermé" : "Closed")}
                          </button>
                        </div>

                        {isOpen ? (
                          <div className="space-y-1.5 pt-1">
                            <div>
                              <span className="text-[9px] uppercase font-bold text-slate-400 block">
                                {fr ? "Ouvre à" : "Opens at"}
                              </span>
                              <input
                                type="time"
                                value={currentOpen}
                                onChange={(e) => {
                                  const val = e.target.value;
                                  setOpeningHours((prev) => ({
                                    ...prev,
                                    [day.key]: {
                                      open: val,
                                      close: prev[day.key]?.close || "17:00",
                                    },
                                  }));
                                }}
                                className="w-full px-2 py-1 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs font-mono font-bold text-slate-900 dark:text-white"
                              />
                            </div>
                            <div>
                              <span className="text-[9px] uppercase font-bold text-slate-400 block">
                                {fr ? "Ferme à" : "Closes at"}
                              </span>
                              <input
                                type="time"
                                value={currentClose}
                                onChange={(e) => {
                                  const val = e.target.value;
                                  setOpeningHours((prev) => ({
                                    ...prev,
                                    [day.key]: {
                                      open: prev[day.key]?.open || "09:00",
                                      close: val,
                                    },
                                  }));
                                }}
                                className="w-full px-2 py-1 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs font-mono font-bold text-slate-900 dark:text-white"
                              />
                            </div>
                          </div>
                        ) : (
                          <div className="py-4 text-center">
                            <span className="text-[11px] font-semibold text-slate-400 italic">
                              {fr ? "Portes fermées" : "Closed"}
                            </span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* 24/7 AI RECEPTIONIST REASSURANCE CARD */}
                <div className="p-4 rounded-2xl bg-gradient-to-r from-blue-50 via-indigo-50/50 to-blue-50/30 dark:from-blue-950/40 dark:via-indigo-950/20 dark:to-blue-950/30 border border-blue-200/80 dark:border-blue-800/60 shadow-xs">
                  <div className="flex items-start gap-3.5">
                    <div className="w-9 h-9 rounded-xl bg-[#0076FF] text-white flex items-center justify-center shrink-0 mt-0.5 shadow-sm shadow-blue-500/20">
                      <PhoneCall className="w-4 h-4" />
                    </div>
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h5 className="text-xs font-extrabold text-blue-950 dark:text-blue-100">
                          {fr
                            ? "Disponibilité de votre réceptionniste IA : 24h/24 et 7j/7"
                            : "AI Receptionist Availability: 24/7 Non-Stop"}
                        </h5>
                        <span className="px-2 py-0.5 rounded-full text-[9px] font-extrabold uppercase tracking-wider bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800">
                          {fr ? "Répond en continu" : "Always on"}
                        </span>
                      </div>
                      <p className="text-xs text-blue-900/80 dark:text-blue-200/80 leading-relaxed">
                        {fr
                          ? "Sous réserve d'une ligne téléphonique active et d'un solde de crédits suffisant, votre réceptionniste IA répond au téléphone en tout temps (24h/24, nuits et fins de semaine). Elle renseigne les appelants sur votre entreprise, vos tarifs et produits, tout en calant les rendez-vous exclusivement sur vos plages d'ouverture physique définies ci-dessus."
                          : "Subject to an active telephone line and sufficient credit balance, your AI receptionist answers calls 24/7 (including nights and weekends). It answers inquiries about your business, pricing, and catalog, while scheduling appointments strictly during your physical opening hours configured above."}
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-100 dark:border-white/[0.06]">
                <button
                  type="button"
                  disabled={saving}
                  onClick={async () => {
                    const ok = await saveBusinessProfile();
                    if (ok) setCurrentStep(2);
                  }}
                  className="px-5 py-2.5 rounded-xl bg-[#0076FF] hover:bg-blue-600 text-white font-bold text-xs shadow-md transition flex items-center gap-2 disabled:opacity-50"
                >
                  {saving && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                  <span>{fr ? "Enregistrer et continuer" : "Save & Continue"}</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}

          {/* ========================================================
              STEP 2: MA RÉCEPTIONNISTE
              ======================================================== */}
          {currentStep === 2 && (
            <div className="space-y-6 animate-in fade-in duration-200">
              <div className="border-b border-slate-100 dark:border-white/[0.06] pb-4">
                <h3 className="text-lg font-extrabold text-slate-900 dark:text-white">
                  {fr ? "Étape 2 : Voix, timbre et message d'accueil" : "Step 2: Voice, Tone & Greeting"}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  {fr
                    ? "Choisissez le timbre de voix naturel de votre réceptionniste et personnalisez la phrase d'introduction."
                    : "Choose your receptionist's natural voice timbre and customize the opening greeting."}
                </p>
              </div>

              {/* VOICE TIMBRE CARDS */}
              <div>
                <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-3">
                  {fr ? "Sélectionnez une voix :" : "Select a voice:"}
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
                  {[
                    { id: "shimmer", name: "Shimmer", desc: fr ? "Chaleureuse, claire et accueillante (Féminin)" : "Warm, clear and welcoming (Female)" },
                    { id: "alloy", name: "Alloy", desc: fr ? "Équilibrée, neutre et directe" : "Balanced, neutral and direct" },
                    { id: "nova", name: "Nova", desc: fr ? "Énergique, souriante et moderne (Féminin)" : "Energetic, upbeat and modern (Female)" },
                    { id: "echo", name: "Echo", desc: fr ? "Calme, rassurante et posée (Masculin)" : "Calm, reassuring and smooth (Male)" },
                    { id: "onyx", name: "Onyx", desc: fr ? "Profonde, formelle et assurée (Masculin)" : "Deep, authoritative and formal (Male)" },
                    { id: "fable", name: "Fable", desc: fr ? "Expressive, conviviale et engageante" : "Expressive, friendly and engaging" },
                  ].map((voice) => {
                    const isSelected = customization.voice_id === voice.id;
                    const isPlaying = playingVoice === voice.id;
                    return (
                      <div
                        key={voice.id}
                        onClick={() => setCustomization((c) => ({ ...c, voice_id: voice.id }))}
                        className={`p-4 rounded-2xl border cursor-pointer transition flex flex-col justify-between gap-3 ${
                          isSelected
                            ? "border-[#0076FF] bg-blue-50/50 dark:bg-blue-950/30 shadow-xs"
                            : "border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700"
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-extrabold text-sm text-slate-900 dark:text-white">
                            {voice.name}
                          </span>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              togglePlayVoice(voice.id);
                            }}
                            className="p-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-[#0076FF] hover:bg-blue-50 transition"
                            title={fr ? "Écouter un extrait" : "Preview voice"}
                          >
                            {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                          </button>
                        </div>
                        <p className="text-[11px] text-slate-500 dark:text-slate-400">
                          {voice.desc}
                        </p>
                        <div className="flex items-center justify-between pt-1">
                          <span className={`text-[10px] font-bold ${isSelected ? "text-[#0076FF]" : "text-slate-400"}`}>
                            {isSelected ? (fr ? "✓ Voix sélectionnée" : "✓ Selected") : (fr ? "Cliquer pour choisir" : "Click to select")}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* GREETING & FAREWELL MESSAGES */}
              <div className="space-y-4 pt-2">
                <div>
                  <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">
                    {fr ? "Message d'accueil téléphonique (Introduction) *" : "Phone Greeting Message *"}
                  </label>
                  <textarea
                    rows={2}
                    value={customization.greeting_message}
                    onChange={(e) => setCustomization((c) => ({ ...c, greeting_message: e.target.value }))}
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs text-slate-900 dark:text-white focus:outline-hidden focus:border-[#0076FF]"
                    placeholder="Ex: Bonjour et bienvenue chez Produits Ero ! En quoi puis-je vous renseigner ?"
                  />
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">
                    {fr ? "Message de fin d'appel" : "Farewell Message"}
                  </label>
                  <input
                    type="text"
                    value={customization.farewell_message}
                    onChange={(e) => setCustomization((c) => ({ ...c, farewell_message: e.target.value }))}
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs text-slate-900 dark:text-white focus:outline-hidden focus:border-[#0076FF]"
                  />
                </div>
              </div>

              <div className="flex items-center justify-between pt-4 border-t border-slate-100 dark:border-white/[0.06]">
                <button
                  type="button"
                  onClick={() => setCurrentStep(1)}
                  className="px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-50 transition flex items-center gap-1.5"
                >
                  <ArrowLeft className="w-3.5 h-3.5" />
                  <span>{fr ? "Précédent" : "Previous"}</span>
                </button>
                <button
                  type="button"
                  disabled={saving}
                  onClick={async () => {
                    const ok = await saveReceptionistCustomization();
                    if (ok) setCurrentStep(3);
                  }}
                  className="px-5 py-2.5 rounded-xl bg-[#0076FF] hover:bg-blue-600 text-white font-bold text-xs shadow-md transition flex items-center gap-2 disabled:opacity-50"
                >
                  {saving && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                  <span>{fr ? "Enregistrer et continuer" : "Save & Continue"}</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}

          {/* ========================================================
              STEP 3: SES CONNAISSANCES ET SES MODULES
              ======================================================== */}
          {currentStep === 3 && (
            <div className="space-y-6 animate-in fade-in duration-200">
              <div className="border-b border-slate-100 dark:border-white/[0.06] pb-4">
                <h3 className="text-lg font-extrabold text-slate-900 dark:text-white">
                  {fr ? "Étape 3 : Connaissances et modules autorisés" : "Step 3: Knowledge & Allowed Modules"}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  {fr
                    ? "Déterminez les modules et informations d'entreprise auxquels la réceptionniste a accès lors d'un appel."
                    : "Specify which business modules and data your receptionist is authorized to access."}
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {/* 1. RETAIL & STOCKS */}
                <div
                  onClick={() => setRetailEnabled(!retailEnabled)}
                  className={`p-5 rounded-2xl border cursor-pointer transition-all flex flex-col justify-between ${
                    retailEnabled
                      ? "border-[#0076FF] bg-blue-50/40 dark:bg-blue-950/20 shadow-xs"
                      : "border-slate-200 dark:border-slate-800 hover:border-slate-300"
                  }`}
                >
                  <div>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <div className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${retailEnabled ? "bg-[#0076FF] text-white" : "bg-slate-200 dark:bg-slate-800 text-slate-500"}`}>
                          <Store className="w-4 h-4" />
                        </div>
                        <div>
                          <h4 className="text-xs font-bold text-slate-900 dark:text-white">
                            {fr ? "Produits et stocks" : "Products and inventory"}
                          </h4>
                          <span className="text-[10px] text-slate-400 font-semibold">
                            {fr ? "Catalogue & Disponibilités" : "Catalog & Stock"}
                          </span>
                        </div>
                      </div>
                      <div
                        className={`w-5 h-5 rounded-md border flex items-center justify-center shrink-0 ${
                          retailEnabled ? "bg-[#0076FF] border-[#0076FF] text-white" : "border-slate-300 dark:border-slate-700"
                        }`}
                      >
                        {retailEnabled && <Check className="w-3.5 h-3.5" />}
                      </div>
                    </div>

                    <p className="text-xs font-semibold text-slate-800 dark:text-slate-200 mt-3 leading-snug">
                      {fr
                        ? "« Votre IA peut renseigner les clients sur votre catalogue et les disponibilités. »"
                        : "“Your AI can answer customer questions about your catalog and stock availability.”"}
                    </p>
                    <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-1 leading-relaxed">
                      {fr
                        ? "Vérifie les fiches produits, prix et stocks pour renseigner l'appelant en direct."
                        : "Checks product listings, prices, and stock levels to answer callers live."}
                    </p>
                  </div>

                  <div className="mt-3 pt-2.5 border-t border-slate-100 dark:border-white/[0.04] text-[10px] font-bold text-slate-400">
                    {retailEnabled ? (fr ? "✓ Capacité activée" : "✓ Active") : (fr ? "Désactivé" : "Disabled")}
                  </div>
                </div>

                {/* 2. CRM & APPOINTMENTS */}
                <div
                  onClick={() => setCrmEnabled(!crmEnabled)}
                  className={`p-5 rounded-2xl border cursor-pointer transition-all flex flex-col justify-between ${
                    crmEnabled
                      ? "border-[#0076FF] bg-blue-50/40 dark:bg-blue-950/20 shadow-xs"
                      : "border-slate-200 dark:border-slate-800 hover:border-slate-300"
                  }`}
                >
                  <div>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <div className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${crmEnabled ? "bg-[#0076FF] text-white" : "bg-slate-200 dark:bg-slate-800 text-slate-500"}`}>
                          <Calendar className="w-4 h-4" />
                        </div>
                        <div>
                          <h4 className="text-xs font-bold text-slate-900 dark:text-white">
                            {fr ? "Rendez-vous et réservations" : "Appointments and bookings"}
                          </h4>
                          <span className="text-[10px] text-slate-400 font-semibold">
                            {fr ? "Calendrier connecté" : "Connected calendar"}
                          </span>
                        </div>
                      </div>
                      <div
                        className={`w-5 h-5 rounded-md border flex items-center justify-center shrink-0 ${
                          crmEnabled ? "bg-[#0076FF] border-[#0076FF] text-white" : "border-slate-300 dark:border-slate-700"
                        }`}
                      >
                        {crmEnabled && <Check className="w-3.5 h-3.5" />}
                      </div>
                    </div>

                    <p className="text-xs font-semibold text-slate-800 dark:text-slate-200 mt-3 leading-snug">
                      {fr
                        ? "« Votre IA peut trouver des créneaux et gérer des réservations. »"
                        : "“Your AI can find available slots and manage bookings.”"}
                    </p>
                    <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-1 leading-relaxed">
                      {fr
                        ? "Consulte les créneaux disponibles et enregistre les rendez-vous selon vos horaires d'ouverture réels."
                        : "Checks available slots and schedules bookings according to your actual business hours."}
                    </p>
                  </div>

                  <div className="mt-3 pt-2.5 border-t border-slate-100 dark:border-white/[0.04] text-[10px] font-bold text-slate-400">
                    {crmEnabled ? (fr ? "✓ Capacité activée" : "✓ Active") : (fr ? "Désactivé" : "Disabled")}
                  </div>
                </div>

                {/* 3. CUSTOMER SERVICE & IDENTITY */}
                <div
                  onClick={() => setCustomerServiceEnabled(!customerServiceEnabled)}
                  className={`p-5 rounded-2xl border cursor-pointer transition-all flex flex-col justify-between ${
                    customerServiceEnabled
                      ? "border-[#0076FF] bg-blue-50/40 dark:bg-blue-950/20 shadow-xs"
                      : "border-slate-200 dark:border-slate-800 hover:border-slate-300"
                  }`}
                >
                  <div>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <div className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${customerServiceEnabled ? "bg-[#0076FF] text-white" : "bg-slate-200 dark:bg-slate-800 text-slate-500"}`}>
                          <Users className="w-4 h-4" />
                        </div>
                        <div>
                          <h4 className="text-xs font-bold text-slate-900 dark:text-white">
                            {fr ? "Service clientèle" : "Customer service"}
                          </h4>
                          <span className="text-[10px] text-slate-400 font-semibold">
                            {fr ? "Accueil & Renseignements" : "Front Desk & Inquiries"}
                          </span>
                        </div>
                      </div>
                      <div
                        className={`w-5 h-5 rounded-md border flex items-center justify-center shrink-0 ${
                          customerServiceEnabled ? "bg-[#0076FF] border-[#0076FF] text-white" : "border-slate-300 dark:border-slate-700"
                        }`}
                      >
                        {customerServiceEnabled && <Check className="w-3.5 h-3.5" />}
                      </div>
                    </div>

                    <p className="text-xs font-semibold text-slate-800 dark:text-slate-200 mt-3 leading-snug">
                      {fr
                        ? "« Votre IA répond aux questions sur votre entreprise. »"
                        : "“Your AI answers questions about your business.”"}
                    </p>
                    <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-1 leading-relaxed">
                      {fr
                        ? "Renseigne les appelants sur vos activités, votre adresse, vos politiques et vos horaires physiques."
                        : "Informs callers about your business activities, address, policies, and store hours."}
                    </p>
                  </div>

                  <div className="mt-3 pt-2.5 border-t border-slate-100 dark:border-white/[0.04] text-[10px] font-bold text-slate-400">
                    {customerServiceEnabled ? (fr ? "✓ Capacité activée" : "✓ Active") : (fr ? "Désactivé" : "Disabled")}
                  </div>
                </div>

                {/* 4. INTERNAL INSIGHTS (PIN PROTECTED) */}
                <div
                  onClick={() => setInternalInsightsEnabled(!internalInsightsEnabled)}
                  className={`p-5 rounded-2xl border cursor-pointer transition-all flex flex-col justify-between ${
                    internalInsightsEnabled
                      ? "border-[#0076FF] bg-blue-50/40 dark:bg-blue-950/20 shadow-xs"
                      : "border-slate-200 dark:border-slate-800 hover:border-slate-300"
                  }`}
                >
                  <div>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <div className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${internalInsightsEnabled ? "bg-[#0076FF] text-white" : "bg-slate-200 dark:bg-slate-800 text-slate-500"}`}>
                          <Lock className="w-4 h-4" />
                        </div>
                        <div>
                          <h4 className="text-xs font-bold text-slate-900 dark:text-white">
                            {fr ? "Informations internes" : "Internal business insights"}
                          </h4>
                          <span className="text-[10px] text-amber-600 dark:text-amber-400 font-bold">
                            {fr ? "Sécurisé par NIP individuel" : "Individual PIN secured"}
                          </span>
                        </div>
                      </div>
                      <div
                        className={`w-5 h-5 rounded-md border flex items-center justify-center shrink-0 ${
                          internalInsightsEnabled ? "bg-[#0076FF] border-[#0076FF] text-white" : "border-slate-300 dark:border-slate-700"
                        }`}
                      >
                        {internalInsightsEnabled && <Check className="w-3.5 h-3.5" />}
                      </div>
                    </div>

                    <p className="text-xs font-semibold text-slate-800 dark:text-slate-200 mt-3 leading-snug">
                      {fr
                        ? "« Vos employés autorisés peuvent consulter certaines informations privées. »"
                        : "“Your authorized staff can consult select private summaries.”"}
                    </p>
                    <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-1 leading-relaxed">
                      {fr
                        ? "Permet au gérant ou aux employés de consulter les ventes et la trésorerie après saisie de leur NIP. Les clients externes n'y ont jamais accès."
                        : "Allows managers or staff to consult sales and cashflow after entering their personal PIN. External callers never have access."}
                    </p>
                  </div>

                  <div className="mt-3 pt-2.5 border-t border-slate-100 dark:border-white/[0.04] text-[10px] font-bold text-slate-400">
                    {internalInsightsEnabled ? (fr ? "✓ NIP requis activé" : "✓ PIN required active") : (fr ? "Désactivé" : "Disabled")}
                  </div>
                </div>
              </div>

              <div className="p-4 rounded-2xl bg-amber-50/70 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 text-xs text-amber-800 dark:text-amber-200 flex items-start gap-3">
                <ShieldCheck className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                <div className="leading-relaxed">
                  <strong>{fr ? "Garantie anti-hallucination :" : "Anti-hallucination guarantee:"}</strong>{" "}
                  {fr
                    ? "La réceptionniste répond uniquement sur la base de vos données vérifiées. Si un appelant pose une question hors sujet (ex: commander de la nourriture), l'assistant répond poliment qu'il s'agit d'une boutique d'équipements sportifs sans inventer de services inexistants."
                    : "The assistant only speaks from verified business knowledge. If asked for unrelated items (e.g. food orders), it politely states it specializes in sports equipment."}
                </div>
              </div>

              <div className="flex items-center justify-between pt-4 border-t border-slate-100 dark:border-white/[0.06]">
                <button
                  type="button"
                  onClick={() => setCurrentStep(2)}
                  className="px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-50 transition flex items-center gap-1.5"
                >
                  <ArrowLeft className="w-3.5 h-3.5" />
                  <span>{fr ? "Précédent" : "Previous"}</span>
                </button>
                <button
                  type="button"
                  disabled={saving}
                  onClick={async () => {
                    const ok = await saveBusinessProfile();
                    if (ok) setCurrentStep(4);
                  }}
                  className="px-5 py-2.5 rounded-xl bg-[#0076FF] hover:bg-blue-600 text-white font-bold text-xs shadow-md transition flex items-center gap-2 disabled:opacity-50"
                >
                  {saving && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                  <span>{fr ? "Enregistrer et continuer" : "Save & Continue"}</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}

          {/* ========================================================
              STEP 4: MON TÉLÉPHONE ET MES EMPLOYÉS (UNIFIED TELEPHONY)
              ======================================================== */}
          {currentStep === 4 && (
            <div className="space-y-6 animate-in fade-in duration-200">
              <div className="border-b border-slate-100 dark:border-white/[0.06] pb-4">
                <h3 className="text-lg font-extrabold text-slate-900 dark:text-white">
                  {fr ? "Étape 4 : Téléphone et gestion des employés" : "Step 4: Phone & Employee Security"}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  {fr
                    ? "Architecture téléphonique canonique : Votre numéro dédié achemine les appels avec un menu vocal simple."
                    : "Canonical telephony architecture: Your dedicated phone number routes calls via an intuitive voice menu."}
                </p>
              </div>

              {/* DEDICATED NUMBER CARD */}
              <div className="p-6 rounded-3xl border border-slate-200 dark:border-slate-800 bg-gradient-to-br from-slate-50 to-blue-50/20 dark:from-[#060B13] dark:to-[#0B132B] space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-2xl bg-blue-100 dark:bg-blue-900/50 text-[#0076FF] flex items-center justify-center shrink-0">
                      <PhoneCall className="w-5 h-5" />
                    </div>
                    <div>
                      <span className="text-[10px] font-extrabold uppercase tracking-widest text-[#0076FF]">
                        {fr ? "Ligne Dédiée Entreprise" : "Dedicated Business Line"}
                      </span>
                      <h4 className="text-lg font-mono font-black text-slate-900 dark:text-white">
                        {assignedNumber}
                      </h4>
                    </div>
                  </div>

                  <span className="self-start sm:self-auto px-3 py-1 rounded-full text-xs font-bold bg-blue-100 dark:bg-blue-950 text-[#0076FF] border border-blue-200 dark:border-blue-900">
                    {fr ? "Numéro vérifié" : "Verified Line"}
                  </span>
                </div>

                {/* DUAL PATH IVR EXPLANATION */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                  <div className="p-4 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-white/[0.08] space-y-2">
                    <div className="flex items-center gap-2">
                      <span className="w-6 h-6 rounded-full bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 font-bold text-xs flex items-center justify-center">
                        2
                      </span>
                      <span className="font-extrabold text-xs text-slate-900 dark:text-white">
                        {fr ? "Touche 2 : Clients" : "Touch 2: Customers"}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      {fr
                        ? "Accueil direct sans AUCUN NIP. Le client pose ses questions sur les snowboards, les prix ou réserve un entretien."
                        : "Direct access with ZERO PIN. Caller asks about equipment, prices or books appointments immediately."}
                    </p>
                  </div>

                  <div className="p-4 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-white/[0.08] space-y-2">
                    <div className="flex items-center gap-2">
                      <span className="w-6 h-6 rounded-full bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300 font-bold text-xs flex items-center justify-center">
                        1
                      </span>
                      <span className="font-extrabold text-xs text-slate-900 dark:text-white">
                        {fr ? "Touche 1 : Employés" : "Touch 1: Employees"}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      {fr
                        ? "Accès privé réservé aux employés munis de leur NIP individuel (4 à 8 chiffres haché avec Argon2). 5 essais max avant verrouillage."
                        : "Private extension for staff with their individual PIN (4-8 digits, Argon2 hashed). 5 failed attempts lockout."}
                    </p>
                  </div>
                </div>
              </div>

              {/* EMPLOYEE PERSONAL PIN CONFIGURATION FORM */}
              <div className="p-5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50 space-y-3">
                <div className="flex items-center gap-2">
                  <Lock className="w-4 h-4 text-[#0076FF]" />
                  <h4 className="text-sm font-bold text-slate-900 dark:text-white">
                    {fr ? "Définir ou modifier votre code NIP personnel employé" : "Set or change your employee PIN"}
                  </h4>
                </div>
                <p className="text-xs text-slate-500">
                  {fr
                    ? "Permet d'accéder au mode interne lorsque vous appelez votre numéro dédié et appuyez sur 1."
                    : "Allows you to access the staff private mode when dialing your dedicated line and pressing 1."}
                </p>

                <div className="flex items-center gap-2 max-w-sm">
                  <input
                    type="password"
                    pattern="[0-9]*"
                    maxLength={8}
                    placeholder="NIP (4 à 8 chiffres)"
                    value={employeePin}
                    onChange={(e) => setEmployeePin(e.target.value.replace(/\D/g, ""))}
                    className="flex-1 px-3.5 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs font-mono font-bold text-slate-900 dark:text-white focus:outline-hidden focus:border-[#0076FF]"
                  />
                  <button
                    type="button"
                    disabled={employeePinSaving || employeePin.length < 4}
                    onClick={savePersonalPin}
                    className="px-4 py-2.5 rounded-xl bg-[#0076FF] hover:bg-blue-600 text-white text-xs font-bold shadow-xs transition disabled:opacity-50"
                  >
                    {employeePinSaving ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : (fr ? "Enregistrer" : "Save")}
                  </button>
                </div>

                {employeePinFeedback && (
                  <p className="text-xs font-semibold text-blue-600 dark:text-blue-400 mt-1">
                    {employeePinFeedback}
                  </p>
                )}
              </div>

              {/* ADVANCED ACCORDION: SHARED CENTRAL GATEWAY */}
              <div className="pt-2">
                <button
                  type="button"
                  onClick={() => setShowAdvancedAccordion(!showAdvancedAccordion)}
                  className="flex items-center justify-between w-full p-4 rounded-2xl border border-slate-200 dark:border-slate-800 text-left text-xs font-bold text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-900 transition"
                >
                  <div className="flex items-center gap-2">
                    <Sliders className="w-4 h-4 text-purple-600" />
                    <span>{fr ? "Options avancées : Standard central partagé (Secours)" : "Advanced: Shared Central Dispatcher (Backup)"}</span>
                  </div>
                  {showAdvancedAccordion ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                </button>

                {showAdvancedAccordion && (
                  <div className="mt-3 p-5 rounded-2xl border border-purple-200/80 dark:border-purple-900/40 bg-purple-50/30 dark:bg-purple-950/20 text-xs space-y-3 animate-in fade-in">
                    <p className="text-slate-600 dark:text-slate-300 leading-relaxed">
                      {fr
                        ? "Cette option permet d'appeler le standard partagé Avenqo (+1 438-607-5438) en composant un NIP d'entreprise. Ceci est un système de secours et n'est pas le parcours recommandé pour vos clients réguliers."
                        : "Allows calling Avenqo's shared gateway using a company DTMF PIN. This is a backup option, not the primary customer flow."}
                    </p>
                    {routingNip && (
                      <div className="flex items-center gap-3">
                        <span className="font-bold">{fr ? "Code d'entreprise DTMF :" : "Company DTMF PIN:"}</span>
                        <span className="font-mono font-black text-purple-700 dark:text-purple-300 text-sm bg-purple-100 dark:bg-purple-900/50 px-2 py-0.5 rounded-md">
                          {routingNip}#
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="flex items-center justify-between pt-4 border-t border-slate-100 dark:border-white/[0.06]">
                <button
                  type="button"
                  onClick={() => setCurrentStep(3)}
                  className="px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-50 transition flex items-center gap-1.5"
                >
                  <ArrowLeft className="w-3.5 h-3.5" />
                  <span>{fr ? "Précédent" : "Previous"}</span>
                </button>
                <button
                  type="button"
                  onClick={() => setCurrentStep(5)}
                  className="px-5 py-2.5 rounded-xl bg-[#0076FF] hover:bg-blue-600 text-white font-bold text-xs shadow-md transition flex items-center gap-2"
                >
                  <span>{fr ? "Passer au test et activation" : "Proceed to Test & Activate"}</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}

          {/* ========================================================
              STEP 5: TESTER ET ACTIVER (REAL SERVER VALIDATION)
              ======================================================== */}
          {currentStep === 5 && (
            <div className="space-y-6 animate-in fade-in duration-200">
              <div className="border-b border-slate-100 dark:border-white/[0.06] pb-4">
                <h3 className="text-lg font-extrabold text-slate-900 dark:text-white">
                  {fr ? "Étape 5 : Vérification des prérequis et activation sécurisée" : "Step 5: Server Checklist & Fail-Closed Activation"}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  {fr
                    ? "La checklist vérifie les prérequis en direct sur le serveur PostgreSQL. L'activation échoue de manière sécurisée (fail-closed) si un élément manque."
                    : "The checklist queries real PostgreSQL server state. Activation is fail-closed."}
                </p>
              </div>

              {/* CANONICAL SERVER LIFECYCLE CARD */}
              <VoiceLifecycleCard
                tenantId={tenantId}
                canManage={canManage}
                businessName={businessName}
              />

              <div className="flex items-center justify-between pt-4 border-t border-slate-100 dark:border-white/[0.06]">
                <button
                  type="button"
                  onClick={() => setCurrentStep(4)}
                  className="px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-50 transition flex items-center gap-1.5"
                >
                  <ArrowLeft className="w-3.5 h-3.5" />
                  <span>{fr ? "Précédent" : "Previous"}</span>
                </button>
                <span className="text-xs font-bold text-emerald-600 dark:text-emerald-400 flex items-center gap-1.5">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>{fr ? "Assistant configuré" : "Wizard completed"}</span>
                </span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
