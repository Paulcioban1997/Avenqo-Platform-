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
  Bookmark,
  Search,
  Info,
} from "lucide-react";
import { useLocale } from "@/lib/i18n/locale-context";
import { apiFetch } from "@/lib/api-request";
import { VoiceLifecycleCard } from "@/components/voice/voice-lifecycle-card";
import {
  INDUSTRY_CATALOG,
  INDUSTRY_CATEGORIES,
  IndustryItem,
  getLocalizedCategory,
  getLocalizedIndustry,
  getVoiceIndustryUi,
} from "./voice-industry-catalog";

interface WizardProps {
  tenantId?: string;
  canManage: boolean;
  businessName?: string;
  onRefreshStatus?: () => void;
}

interface BusinessProfile {
  business_name: string;
  industry: string;
  industries?: string[];
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
  expected_version?: number;
}

interface CustomizationConfig {
  voice_id: string;
  speech_speed: number;
  personality_tone: string;
  voice_display_name?: string;
  voice_pronunciation?: string;
  greeting_message?: string;
  farewell_message?: string;
  custom_pronunciation?: Record<string, string>;
  personality_preset?: string;
  professionalism_level?: number;
  warmth_level?: number;
  humor_level?: number;
  formality_level?: number;
  allow_natural_interruptions?: boolean;
  realtime_provider?: string;
  gemini_live_enabled?: boolean;
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
  const [openSection, setOpenSection] = useState<number | null>(1);
  const [showAdvancedParams, setShowAdvancedParams] = useState<boolean>(false);
  const [selectedIndustry, setSelectedIndustry] = useState<string>("");
  const [selectedIndustries, setSelectedIndustries] = useState<string[]>([]);
  const [failedImages, setFailedImages] = useState<Record<string, boolean>>({});
  const [industrySearch, setIndustrySearch] = useState<string>("");
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [isExpandedCatalog, setIsExpandedCatalog] = useState<boolean>(false);
  const [customIndustryName, setCustomIndustryName] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [saveFeedback, setSaveFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  // Step 1: Business Profile State
  const [profile, setProfile] = useState<BusinessProfile>({
    business_name: businessName || "",
    industry: "",
    description: "",
    activities: [],
    locations: [],
    timezone: "America/Montreal",
    opening_hours: {},
    primary_locale: "fr-CA",
    secondary_locales: ["en-US"],
    contact_phone: null,
    website: "",
    bookable_service_ids: [],
    allowed_actions: ["retail:read_products", "crm:read_availability", "crm:create_appointment", "crm:read_client_self"],
    communication_style: "professionnel",
    expected_version: 0,
  });

  // Step 1: Real Business Hours Schedule State (Not pre-selected!)
  const [openingHours, setOpeningHours] = useState<Record<string, { open: string; close: string } | null>>({});

  // Step 2: Receptionist Customization State
  const [voices, setVoices] = useState<VoiceItem[]>([]);
  const [customization, setCustomization] = useState<CustomizationConfig>({
    voice_id: "shimmer",
    speech_speed: 1.0,
    personality_tone: "professionnel",
    voice_display_name: "",
    voice_pronunciation: "",
    greeting_message: "",
    farewell_message: "",
    personality_preset: "professional_premium_warm",
    professionalism_level: 100,
    warmth_level: 85,
    humor_level: 40,
    formality_level: 65,
    allow_natural_interruptions: true,
    realtime_provider: "gemini_live",
    gemini_live_enabled: true,
  });

  useEffect(() => {
    if (businessName) {
      setProfile((prev) => ({ ...prev, business_name: businessName }));
    }
  }, [businessName]);
  const [playingVoice, setPlayingVoice] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState<boolean>(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Step 3: 4 Business Capabilities State (Zero Technical Clutter)
  const [retailEnabled, setRetailEnabled] = useState<boolean>(true);
  const [crmEnabled, setCrmEnabled] = useState<boolean>(true);
  const [customerServiceEnabled, setCustomerServiceEnabled] = useState<boolean>(true);
  const [internalInsightsEnabled, setInternalInsightsEnabled] = useState<boolean>(false);

  // Step 4: Telephony & Employees (Canonical Architecture)
  const [assignedNumber, setAssignedNumber] = useState<string>("");
  const [employeePin, setEmployeePin] = useState<string>("");
  const [employeePinConfirm, setEmployeePinConfirm] = useState<string>("");
  const [currentPassword, setCurrentPassword] = useState<string>("");
  const [employeePhone, setEmployeePhone] = useState<string>("");
  const [employeePinSaving, setEmployeePinSaving] = useState<boolean>(false);
  const [employeePinFeedback, setEmployeePinFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);
  interface VoicePinStatus {
    configured: boolean;
    enabled: boolean;
    has_pin: boolean;
    phone_access_enabled: boolean;
    phone_number: string | null;
    is_locked: boolean;
    failed_attempts: number;
    locked_until: string | null;
    active_sessions_count: number;
  }

  const normalizePinStatus = (data: any): VoicePinStatus => {
    const isConfigured = Boolean(data?.configured ?? data?.has_pin);
    const rawEnabled = data?.enabled !== undefined ? data.enabled : data?.phone_access_enabled;
    const isEnabled = isConfigured && rawEnabled !== undefined ? Boolean(rawEnabled) : Boolean(data?.enabled ?? data?.phone_access_enabled);
    const isLocked = Boolean(data?.is_locked || (data?.locked_until && new Date(data.locked_until).getTime() > Date.now()));
    return {
      configured: isConfigured,
      enabled: isEnabled,
      has_pin: isConfigured,
      phone_access_enabled: isEnabled,
      phone_number: data?.phone_number || null,
      is_locked: isLocked,
      failed_attempts: typeof data?.failed_attempts === "number" ? data.failed_attempts : 0,
      locked_until: data?.locked_until || (isLocked ? "locked" : null),
      active_sessions_count: typeof data?.active_sessions_count === "number" ? data.active_sessions_count : 0,
    };
  };

  const [pinStatus, setPinStatus] = useState<VoicePinStatus | null>(null);
  const [lifecycleData, setLifecycleData] = useState<any>(null);
  const [isConfigDropdownOpen, setIsConfigDropdownOpen] = useState<boolean>(true);
  const [hasInteractedWithDropdown, setHasInteractedWithDropdown] = useState<boolean>(false);

  // Advanced Section toggle (Shared Dispatcher & DTMF fallback)
  const [showAdvancedAccordion, setShowAdvancedAccordion] = useState<boolean>(false);
  const [routingNip, setRoutingNip] = useState<string | null>(null);
  const [dispatcherNumber, setDispatcherNumber] = useState<string>("");

  // Load initial configuration from server APIs
  const loadConfiguration = useCallback(async () => {
    if (!tenantId) return;
    setLoading(true);
    try {
      const [profileRes, customRes, voicesRes, statusRes, pinRes] = await Promise.all([
        apiFetch("/api/v1/voice/business-profile").catch(() => null),
        apiFetch("/api/v1/voice/customization").catch(() => null),
        apiFetch("/api/v1/voice/voices").catch(() => null),
        apiFetch("/api/v1/voice/status").catch(() => null),
        apiFetch("/api/v1/voice/auth/pin/status").catch(() => null),
      ]);

      if (profileRes && profileRes.ok) {
        const data = await profileRes.json();
        if (data.profile) {
          setProfile((prev) => ({
            ...prev,
            ...data.profile,
            expected_version: typeof data.profile.expected_version === "number" ? data.profile.expected_version : prev.expected_version ?? 0,
            business_name: data.profile.business_name || businessName,
          }));

          // Restore multi-industry selections from backend
          let restoredIndustries: string[] = [];
          if (Array.isArray(data.profile.industries) && data.profile.industries.length > 0) {
            restoredIndustries = data.profile.industries;
          } else if (data.profile.industry && typeof data.profile.industry === "string" && data.profile.industry.trim()) {
            const rawInd = data.profile.industry.trim().toLowerCase();
            const matched = INDUSTRY_CATALOG.find(
              (item) =>
                item.id.toLowerCase() === rawInd ||
                item.nameFr.toLowerCase() === rawInd ||
                item.nameEn.toLowerCase() === rawInd
            );
            restoredIndustries = [matched ? matched.id : rawInd];
          }
          setSelectedIndustries(restoredIndustries);
          setSelectedIndustry(restoredIndustries[0] || "");
          if (data.profile.opening_hours && typeof data.profile.opening_hours === "object") {
            const rawHours = data.profile.opening_hours;
            if (rawHours.weekly && typeof rawHours.weekly === "object") {
              const extracted: Record<string, { open: string; close: string }> = {};
              for (const [day, periods] of Object.entries(rawHours.weekly)) {
                if (Array.isArray(periods) && periods.length > 0 && periods[0]?.open && periods[0]?.close) {
                  extracted[day] = { open: String(periods[0].open), close: String(periods[0].close) };
                }
              }
              setOpeningHours(extracted);
            } else {
              setOpeningHours(rawHours);
            }
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
            speech_speed: typeof data.speech_speed === "number" ? data.speech_speed : prev.speech_speed,
            personality_tone: data.personality_tone || prev.personality_tone,
            voice_display_name: data.voice_display_name || data.voice_pronunciation || prev.voice_display_name,
            voice_pronunciation: data.voice_pronunciation || data.voice_display_name || prev.voice_pronunciation,
            greeting_message: data.greeting_message ?? prev.greeting_message,
            farewell_message: data.farewell_message ?? prev.farewell_message,
            personality_preset: data.personality_preset || prev.personality_preset || "professional_premium_warm",
            professionalism_level: typeof data.professionalism_level === "number" ? data.professionalism_level : prev.professionalism_level ?? 100,
            warmth_level: typeof data.warmth_level === "number" ? data.warmth_level : prev.warmth_level ?? 85,
            humor_level: typeof data.humor_level === "number" ? data.humor_level : prev.humor_level ?? 40,
            formality_level: typeof data.formality_level === "number" ? data.formality_level : prev.formality_level ?? 65,
            allow_natural_interruptions: typeof data.allow_natural_interruptions === "boolean" ? data.allow_natural_interruptions : prev.allow_natural_interruptions ?? true,
            realtime_provider: data.realtime_provider || prev.realtime_provider || "gemini_live",
            gemini_live_enabled: typeof data.gemini_live_enabled === "boolean" ? data.gemini_live_enabled : prev.gemini_live_enabled ?? true,
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

      if (pinRes && pinRes.ok) {
        const pinData = await pinRes.json();
        const normalized = normalizePinStatus(pinData);
        setPinStatus(normalized);
        // Security rule: Never re-inject masked phone into the editable field.
        // Rotation without changing phone keeps employeePhone empty and omits phone_number in PUT.
        setEmployeePhone("");
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

  // Audio preview playback with real TTS endpoint
  const playPreviewAudio = async (text: string, voiceId?: string) => {
    const targetVoice = voiceId || customization.voice_id || "shimmer";
    if (playingVoice === targetVoice) {
      if (audioRef.current) audioRef.current.pause();
      setPlayingVoice(null);
      return;
    }

    if (audioRef.current) audioRef.current.pause();
    setPreviewLoading(true);
    setPlayingVoice(targetVoice);

    try {
      const res = await apiFetch("/api/v1/voice/voices/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          voice_id: targetVoice,
          speech_speed: customization.speech_speed || 1.0,
          text: text,
        }),
      });

      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        audioRef.current = audio;
        audio.onended = () => {
          setPlayingVoice(null);
          URL.revokeObjectURL(url);
        };
        audio.onerror = () => {
          setPlayingVoice(null);
          URL.revokeObjectURL(url);
        };
        await audio.play();
        return;
      }
    } catch {
      // Fallback to speech synthesis if network fails
    } finally {
      setPreviewLoading(false);
    }

    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = profile.primary_locale || "fr-CA";
      utterance.rate = customization.speech_speed;
      utterance.onend = () => setPlayingVoice(null);
      window.speechSynthesis.speak(utterance);
    } else {
      setPlayingVoice(null);
    }
  };

  const togglePlayVoice = (voiceId: string) => {
    const defaultGreeting = customization.greeting_message || (fr ? `Bonjour et bienvenue chez ${customization.voice_display_name || profile.business_name || "notre entreprise"}. Comment puis-je vous aider aujourd'hui ?` : "Hello and welcome! How can I help you today?");
    void playPreviewAudio(defaultGreeting, voiceId);
  };

  // Save Step 1 & 3: Business Profile
  const saveBusinessProfile = async () => {
    setSaving(true);
    setSaveFeedback(null);
    try {
      const allowedActions: string[] = [];
      if (retailEnabled) {
        allowedActions.push("retail:read_products", "retail:read_inventory");
      }
      if (crmEnabled) {
        allowedActions.push("crm:read_availability", "crm:create_appointment");
      }
      if (customerServiceEnabled) {
        allowedActions.push("crm:read_client_self");
      }
      if (internalInsightsEnabled) {
        allowedActions.push("retail:read_sales_summary", "accounting:read_cashflow", "cross_agent:read_business_health");
      }

      const isCrmSchedule = Boolean(
        profile.opening_hours &&
        typeof profile.opening_hours === "object" &&
        ("weekly" in profile.opening_hours || "date_overrides" in profile.opening_hours)
      );

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

      let finalOpeningHours: any = cleanOpeningHours;
      if (isCrmSchedule) {
        const weeklyObj: Record<string, Array<{ open: string; close: string }>> = {};
        for (const [day, period] of Object.entries(cleanOpeningHours)) {
          if (period && period.open && period.close) {
            weeklyObj[day] = [{ open: period.open, close: period.close }];
          } else {
            weeklyObj[day] = [];
          }
        }
        finalOpeningHours = {
          ...(typeof profile.opening_hours === "object" ? profile.opening_hours : {}),
          weekly: {
            ...(typeof (profile.opening_hours as any)?.weekly === "object" ? (profile.opening_hours as any).weekly : {}),
            ...weeklyObj,
          },
        };
      }

      const payload = {
        ...profile,
        expected_version: profile.expected_version ?? 0,
        contact_phone: profile.contact_phone?.trim() || null,
        opening_hours: finalOpeningHours,
        allowed_actions: allowedActions,
        industries: selectedIndustries,
        industry: selectedIndustries[0] || profile.industry || "",
      };

      let res: Response;
      try {
        res = await apiFetch("/api/v1/voice/business-profile", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      } catch (firstErr: any) {
        if (firstErr?.status === 409) {
          // Transparent optimistic concurrency recovery: fetch fresh server version and retry once
          const freshRes = await apiFetch("/api/v1/voice/business-profile");
          const freshData = await freshRes.json();
          const freshVersion = freshData?.profile?.expected_version ?? 0;
          const retryPayload = { ...payload, expected_version: freshVersion };
          res = await apiFetch("/api/v1/voice/business-profile", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(retryPayload),
          });
        } else {
          throw firstErr;
        }
      }

      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || (fr ? "Erreur de sauvegarde de l'entreprise." : "Failed to save business profile."));
      }

      const updated = await res.json().catch(() => null);
      if (updated?.profile) {
        setProfile((prev) => ({
          ...prev,
          ...updated.profile,
          expected_version: updated.profile.expected_version,
        }));
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
        voice_display_name: customization.voice_display_name?.trim() || undefined,
        voice_pronunciation: customization.voice_pronunciation?.trim() || customization.voice_display_name?.trim() || undefined,
        greeting_message: customization.greeting_message?.trim() || undefined,
        farewell_message: customization.farewell_message?.trim() || undefined,
        custom_pronunciation: customization.custom_pronunciation || {},
        personality_preset: customization.personality_preset || "professional_premium_warm",
        professionalism_level: customization.professionalism_level ?? 100,
        warmth_level: customization.warmth_level ?? 85,
        humor_level: customization.humor_level ?? 40,
        formality_level: customization.formality_level ?? 65,
        allow_natural_interruptions: customization.allow_natural_interruptions ?? true,
        realtime_provider: customization.realtime_provider || "gemini_live",
        gemini_live_enabled: customization.gemini_live_enabled ?? true,
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
    const pinRegex = /^\d{6,12}$/;
    if (!employeePin || !pinRegex.test(employeePin)) {
      setEmployeePinFeedback({
        type: "error",
        message: fr ? "Le code NIP doit comporter de 6 à 12 chiffres (chiffres uniquement)." : "PIN must be between 6 and 12 digits (numbers only).",
      });
      return;
    }

    if (employeePin !== employeePinConfirm) {
      setEmployeePinFeedback({
        type: "error",
        message: fr ? "La confirmation du code NIP ne correspond pas." : "PIN and confirmation PIN do not match.",
      });
      return;
    }
    if (!currentPassword.trim()) {
      setEmployeePinFeedback({
        type: "error",
        message: fr ? "Votre mot de passe actuel est requis pour sécuriser la configuration du NIP." : "Current account password is required to configure PIN.",
      });
      return;
    }
    const hasExistingPhone = Boolean(pinStatus?.configured && pinStatus?.phone_number);
    const typedPhone = employeePhone.trim();
    if (!typedPhone && !hasExistingPhone) {
      setEmployeePinFeedback({
        type: "error",
        message: fr
          ? "Un numéro de téléphone portable est obligatoire pour identifier votre ligne appelante."
          : "A mobile phone number is required to identify your calling line.",
      });
      return;
    }

    setEmployeePinSaving(true);
    setEmployeePinFeedback(null);
    try {
      const payload: Record<string, any> = {
        pin: employeePin,
        confirm_pin: employeePinConfirm,
        current_password: currentPassword.trim(),
      };

      // Only provide phone_number if user entered an unmasked full number.
      // For simple PIN rotation without phone change, omit phone_number to retain the verified server value.
      if (typedPhone && !typedPhone.includes("*")) {
        let normalizedPhone = typedPhone;
        const digits = normalizedPhone.replace(/\D/g, "");
        if (digits.length === 10) {
          normalizedPhone = `+1${digits}`;
        } else if (digits.length === 11 && digits.startsWith("1")) {
          normalizedPhone = `+${digits}`;
        }
        payload.phone_number = normalizedPhone;
      }

      // Backend accepts PUT /api/v1/voice/auth/pin for both creation and modification
      const response = await apiFetch("/api/v1/voice/auth/pin", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        let errorMsg = fr ? "Échec de l'enregistrement du code NIP." : "Failed to save PIN.";
        try {
          const errData = await response.json();
          if (errData?.error?.message) {
            errorMsg = errData.error.message;
          } else if (typeof errData?.detail === "string") {
            errorMsg = errData.detail;
          } else if (Array.isArray(errData?.error?.details) && errData.error.details[0]?.msg) {
            errorMsg = errData.error.details[0].msg;
          }
        } catch {
          errorMsg = `${errorMsg} (HTTP ${response.status})`;
        }
        setEmployeePinFeedback({
          type: "error",
          message: errorMsg,
        });
        setEmployeePinSaving(false);
        return;
      }

      // Verify server state via GET /api/v1/voice/auth/pin/status - never declare success without confirmation
      const verifyRes = await apiFetch("/api/v1/voice/auth/pin/status").catch(() => null);
      if (verifyRes && verifyRes.ok) {
        const freshPinData = await verifyRes.json();
        const freshStatus = normalizePinStatus(freshPinData);
        setPinStatus(freshStatus);
        const isTrulyActive = freshStatus.configured && freshStatus.enabled && !freshStatus.is_locked;
        if (isTrulyActive) {
          setEmployeePinFeedback({
            type: "success",
            message: fr
              ? "NIP personnel configuré et vérifié avec succès ! Haché de manière sécurisée (Argon2)."
              : "Personal PIN successfully configured and verified! Securely hashed with Argon2.",
          });
          setEmployeePin("");
          setEmployeePinConfirm("");
          setCurrentPassword("");
          setEmployeePhone("");
          onRefreshStatus?.();
        } else if (freshStatus.is_locked) {
          setEmployeePinFeedback({
            type: "error",
            message: fr
              ? "Le NIP est enregistré mais votre compte est verrouillé suite à de multiples tentatives erronées."
              : "PIN is saved but your account is locked due to multiple failed attempts.",
          });
        } else {
          setEmployeePinFeedback({
            type: "error",
            message: fr
              ? "Le serveur n'a pas confirmé l'activation de votre NIP. Veuillez réessayer."
              : "Server could not confirm PIN activation. Please try again.",
          });
        }
      } else {
        setEmployeePinFeedback({
          type: "error",
          message: fr
            ? "Impossible de vérifier la confirmation du NIP auprès du serveur."
            : "Could not confirm PIN status with the server.",
        });
      }
    } catch (err: any) {
      setEmployeePinFeedback({
        type: "error",
        message: err?.publicMessage || err?.message || String(err),
      });
    } finally {
      setEmployeePinSaving(false);
    }
  };

    const primaryIndustryIds = [
      "auto",
      "medical",
      "restaurant",
      "retail",
      "transport",
      "real_estate",
      "hospitality",
      "beauty",
    ];

    const filteredIndustries = INDUSTRY_CATALOG.filter((item) => {
      // When not expanded and no filter/search active, show the 8 primary industries
      if (!isExpandedCatalog && !industrySearch.trim() && selectedCategory === "all") {
        return primaryIndustryIds.includes(item.id);
      }
      if (selectedCategory !== "all" && item.category !== selectedCategory) {
        return false;
      }
      if (industrySearch.trim()) {
        const q = industrySearch.trim().toLowerCase();
        const matchFr = item.nameFr.toLowerCase().includes(q) || item.descFr.toLowerCase().includes(q);
        const matchEn = item.nameEn.toLowerCase().includes(q) || item.descEn.toLowerCase().includes(q);
        return matchFr || matchEn;
      }
      return true;
    });

    const ui = getVoiceIndustryUi(locale);
    const activePrimaryIndustry = selectedIndustry
      ? (INDUSTRY_CATALOG.find((ind) => ind.id === selectedIndustry) ?? null)
      : (selectedIndustries.length > 0 ? (INDUSTRY_CATALOG.find((ind) => ind.id === selectedIndustries[0]) ?? null) : null);
    const activeLocalizedPrimary = activePrimaryIndustry
      ? getLocalizedIndustry(activePrimaryIndustry.id, locale)
      : null;

    const premiumImprovements = [
      {
        id: 1,
        icon: "⚡",
        title: "1. Ultra-Low Latency Voice",
        desc: fr ? "Réponses vocales plus rapides, interruptions naturelles, moins de silences" : "Faster vocal responses, natural interruptions, less silence",
        status: "available",
        statusLabel: fr ? "Disponible" : "Available",
        statusClass: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/70 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800/60",
      },
      {
        id: 2,
        icon: "🔀",
        title: "2. Adaptive AI Router",
        desc: fr ? "Gemini Live pour les conversations, raisonnement avancé seulement quand nécessaire" : "Gemini Live for speech, advanced reasoning only when required",
        status: "available",
        statusLabel: fr ? "Disponible" : "Available",
        statusClass: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/70 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800/60",
      },
      {
        id: 3,
        icon: "🧠",
        title: "3. Company Knowledge Brain",
        desc: fr ? "IA qui utilise les catalogues, politiques, données et documents autorisés de chaque entreprise" : "AI powered exclusively by verified company catalogs, policies and data",
        status: "available",
        statusLabel: fr ? "Disponible" : "Available",
        statusClass: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/70 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800/60",
      },
      {
        id: 4,
        icon: "📈",
        title: "4. Revenue Growth Copilot",
        desc: fr ? "Détecte des opportunités de ventes supplémentaires avec des données vérifiées" : "Detects upsell and cross-sell opportunities with verified inventory",
        status: "testing",
        statusLabel: fr ? "En test" : "In testing",
        statusClass: "bg-amber-50 text-amber-700 dark:bg-amber-950/70 dark:text-amber-400 border-amber-200 dark:border-amber-800/60",
      },
      {
        id: 5,
        icon: "👥",
        title: "5. Employee Performance Coach",
        desc: fr ? "Objectifs, conseils quotidiens, progrès hebdomadaires et suivi personnalisé" : "Daily goals, personalized advice, weekly progress tracking",
        status: "coming_soon",
        statusLabel: fr ? "À venir" : "Coming soon",
        statusClass: "bg-blue-50 text-blue-700 dark:bg-blue-950/70 dark:text-blue-400 border-blue-200 dark:border-blue-800/60",
      },
      {
        id: 6,
        icon: "🔄",
        title: "6. Omnichannel Memory",
        desc: fr ? "Continuité autorisée entre téléphone, chatbot, CRM et courriels" : "Authorized continuity between phone, chat, CRM and emails",
        status: "testing",
        statusLabel: fr ? "En test" : "In testing",
        statusClass: "bg-amber-50 text-amber-700 dark:bg-amber-950/70 dark:text-amber-400 border-amber-200 dark:border-amber-800/60",
      },
      {
        id: 7,
        icon: "🌐",
        title: "7. Live Multilingual Assistant",
        desc: fr ? "Conversation multilingue et traduction vocale selon les capacités certifiées" : "Multilingual conversations and real-time speech translation",
        status: "available",
        statusLabel: fr ? "Disponible" : "Available",
        statusClass: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/70 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800/60",
      },
      {
        id: 8,
        icon: "🤝",
        title: "8. Smart Human Handoff",
        desc: fr ? "Transfert à la bonne personne avec résumé et contexte autorisé" : "Seamless transfer to staff with real-time call summary",
        status: "available",
        statusLabel: fr ? "Disponible" : "Available",
        statusClass: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/70 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800/60",
      },
      {
        id: 9,
        icon: "🛡️",
        title: "9. Self-Healing Voice",
        desc: fr ? "Détection d'incidents, circuit breakers et basculement sécurisé du fournisseur IA" : "Incident detection, circuit breakers and graceful provider failover",
        status: "available",
        statusLabel: fr ? "Disponible" : "Available",
        statusClass: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/70 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800/60",
      },
      {
        id: 10,
        icon: "📊",
        title: "10. Voice ROI Analytics",
        desc: fr ? "Mesure des rendez-vous, conversions attribuables, coûts et qualité des appels" : "Track booked appointments, revenue conversions, costs and call quality",
        status: "testing",
        statusLabel: fr ? "En test" : "In testing",
        statusClass: "bg-amber-50 text-amber-700 dark:bg-amber-950/70 dark:text-amber-400 border-amber-200 dark:border-amber-800/60",
      },
    ];

  return (
    <div className="space-y-6">
      {/* HEADER */}
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <span className="text-base font-extrabold text-slate-900 dark:text-white flex items-center gap-2">
            <span>🎙️</span>
            <span>Avenqo Voice AI</span>
          </span>
          <span className="px-2 py-0.5 rounded-md text-[10px] font-extrabold tracking-wider uppercase bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border border-slate-200 dark:border-slate-700">
            Sandbox
          </span>
        </div>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {fr ? "Configuration centralisée de votre réceptionniste" : "Centralized receptionist configuration"}
        </p>
      </div>

      {/* HERO STATUS CARD */}
      <div className="p-4 sm:p-5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B132B] shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="space-y-1.5 flex-1">
          <div className="flex items-center gap-2.5 flex-wrap">
            <h3 className="font-extrabold text-base text-slate-900 dark:text-white">
              {profile.business_name || businessName || (fr ? "Entreprise non configurée" : "Unconfigured business")}
            </h3>
            {assignedNumber ? (
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 dark:bg-emerald-950/70 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800/60 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                <span>{fr ? "Numéro connecté" : "Connected number"}</span>
              </span>
            ) : (
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400 border border-slate-200 dark:border-slate-700 flex items-center gap-1.5">
                <span>{fr ? "Non configuré" : "Not configured"}</span>
              </span>
            )}
          </div>

          {/* NIP employé en haut de page, AU-DESSUS du numéro */}
          <div className="flex items-center gap-2 pt-0.5" data-testid="voice-hero-pin-status">
            {pinStatus?.configured ? (
              pinStatus.is_locked ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-rose-50 text-rose-700 dark:bg-rose-950/70 dark:text-rose-400 border border-rose-200 dark:border-rose-800/60">
                  <Lock className="w-3.5 h-3.5 text-rose-500" />
                  <span>{fr ? "NIP employé verrouillé" : "Employee PIN locked"}</span>
                </span>
              ) : !pinStatus.enabled ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-50 text-amber-700 dark:bg-amber-950/70 dark:text-amber-400 border border-amber-200 dark:border-amber-800/60">
                  <Pause className="w-3.5 h-3.5 text-amber-500" />
                  <span>{fr ? "NIP employé désactivé" : "Employee PIN disabled"}</span>
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-700 dark:bg-emerald-950/70 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800/60">
                  <Lock className="w-3.5 h-3.5 text-emerald-500" />
                  <span>{fr ? "NIP actif et configuré" : "Employee PIN active & configured"}</span>
                  {pinStatus.phone_number && (
                    <span className="text-[10px] font-mono text-emerald-800 dark:text-emerald-300">
                      ({pinStatus.phone_number})
                    </span>
                  )}
                </span>
              )
            ) : (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400 border border-slate-200 dark:border-slate-700">
                <Lock className="w-3.5 h-3.5 text-slate-400" />
                <span>{fr ? "NIP employé à configurer" : "Employee PIN to configure"}</span>
              </span>
            )}
          </div>

          {/* Numéro de téléphone */}
          <div className="text-xs font-mono font-bold text-slate-700 dark:text-slate-300">
            {assignedNumber ? `${assignedNumber} · Gemini Live` : (fr ? "Numéro non configuré" : "Number not configured")}
          </div>
          <div className="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400 font-medium pt-0.5">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            <span>{fr ? "Appels réels : validation de fiabilité en cours" : "Real calls: reliability validation in progress"}</span>
          </div>
        </div>

        {/* Bouton rapide de repli/dépliage dans le hero si configuré */}
        <div className="flex items-center">
          <button
            type="button"
            data-testid="voice-toggle-config-button"
            onClick={() => {
              setIsConfigDropdownOpen((prev) => !prev);
              setHasInteractedWithDropdown(true);
            }}
            className="w-full sm:w-auto px-4 py-2 rounded-xl text-xs font-bold transition flex items-center justify-center gap-2 border bg-slate-100 hover:bg-slate-200 text-slate-800 dark:bg-slate-800 dark:hover:bg-slate-700 dark:text-white border-slate-200 dark:border-slate-700 shadow-sm"
          >
            <Sliders className="w-3.5 h-3.5 text-primary" />
            <span>
              {isConfigDropdownOpen
                ? (fr ? "Enrouler la configuration" : "Collapse configuration")
                : (fr ? "⚙️ Reconfigurer mon agent Voice" : "⚙️ Reconfigure Voice Agent")}
            </span>
            {isConfigDropdownOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* FEEDBACK BANNER */}
      {saveFeedback && (
        <div
          className={`p-3.5 rounded-2xl text-xs font-semibold flex items-center gap-2.5 animate-in fade-in ${
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

      {/* MENU DÉROULANT DE CONFIGURATION : 5 ÉTAPES */}
      <div className="rounded-2xl border border-slate-200/80 dark:border-white/[0.08] bg-white dark:bg-[#0B132B] shadow-sm overflow-hidden transition-all">
        <button
          type="button"
          data-testid="voice-config-dropdown-header"
          onClick={() => {
            setIsConfigDropdownOpen((prev) => !prev);
            setHasInteractedWithDropdown(true);
          }}
          className="w-full p-4 sm:p-5 flex items-center justify-between text-left hover:bg-slate-50/50 dark:hover:bg-slate-900/50 transition cursor-pointer select-none"
          aria-expanded={isConfigDropdownOpen}
        >
          <div className="flex items-center gap-3.5">
            <div className="w-9 h-9 rounded-xl bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400 flex items-center justify-center shrink-0">
              <Sliders className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h4 className="text-sm font-extrabold text-slate-900 dark:text-white">
                  {fr ? "Configuration de l'agent Voice (5 étapes)" : "Voice Agent Configuration (5 steps)"}
                </h4>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300 border border-blue-200 dark:border-blue-800/60">
                  {isConfigDropdownOpen
                    ? (fr ? "5 étapes visibles" : "5 steps visible")
                    : (fr ? "Cliquer pour modifier" : "Click to edit")}
                </span>
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                {fr
                  ? "Entreprise, voix & industries, scénarios d'appels, NIP employé et diagnostics de mise en service."
                  : "Company, voice & industries, call scenarios, employee PIN and provisioning diagnostics."}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-slate-400">
            <span className="text-xs font-semibold hidden sm:inline text-slate-500 dark:text-slate-400">
              {isConfigDropdownOpen
                ? (fr ? "Enrouler" : "Collapse")
                : (fr ? "Dérouler toutes les étapes" : "Expand all steps")}
            </span>
            {isConfigDropdownOpen ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
          </div>
        </button>

        {/* CONTENU DÉROULANT DES 5 ÉTAPES */}
        {isConfigDropdownOpen && (
          <div className="p-4 sm:p-5 pt-0 space-y-3 border-t border-slate-100 dark:border-white/[0.05]">
            {/* 5 ACCORDION CARDS */}
            <div className="space-y-3">
        {/* ========================================================
            ACCORDION 1: MON ENTREPRISE
            ======================================================== */}
        <div className="rounded-2xl border border-slate-200/80 dark:border-white/[0.08] bg-white dark:bg-[#0B132B] shadow-sm overflow-hidden transition-all">
          <button
            type="button"
            onClick={() => {
              setSaveFeedback(null);
              setOpenSection(openSection === 1 ? null : 1);
              setCurrentStep(1);
            }}
            className="w-full p-4 sm:p-5 flex items-center justify-between text-left hover:bg-slate-50/50 dark:hover:bg-slate-900/50 transition cursor-pointer select-none"
          >
            <div className="flex items-center gap-3.5">
              <div className="w-8 h-8 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 flex items-center justify-center shrink-0">
                <Building2 className="w-4 h-4" />
              </div>
              <div>
                <h4 className="text-sm font-extrabold text-slate-900 dark:text-white">
                  {fr ? "1. Mon entreprise" : "1. My Business"}
                </h4>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  {fr ? "Identité, site web, horaires et langues" : "Identity, website, hours & languages"}
                </p>
              </div>
            </div>
            <div className="text-slate-400">
              {openSection === 1 ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
            </div>
          </button>

          {openSection === 1 && (
            <div className="p-5 sm:p-6 border-t border-slate-100 dark:border-white/[0.06] space-y-6 animate-in fade-in duration-200">
              {/* SUMMARY BULLETS */}
              <div className="space-y-1.5 pb-3 border-b border-slate-100 dark:border-white/[0.06] text-xs text-slate-600 dark:text-slate-300 font-medium">
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400 dark:bg-slate-500" />
                  <span>{fr ? "Nom commercial et prononciation" : "Business name & pronunciation"}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400 dark:bg-slate-500" />
                  <span>{fr ? "Description, secteur et site web vérifié" : "Description, industry & verified website"}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400 dark:bg-slate-500" />
                  <span>{fr ? "Horaires synchronisés avec le CRM" : "CRM-synchronized business hours"}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400 dark:bg-slate-500" />
                  <span>{fr ? "Langues et fuseau horaire" : "Languages & timezone"}</span>
                </div>
              </div>

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
                    placeholder={fr ? "Ex: Nom commercial de l'entreprise" : "Ex: Acme Corp"}
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
                    placeholder={fr ? "Ex: Commerce de détail, services professionnels" : "Ex: Retail store, professional services"}
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
                    placeholder={fr ? "Décrivez les produits et services proposés aux appelants..." : "Describe products and services offered to callers..."}
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
                {Boolean(profile.opening_hours && ("weekly" in profile.opening_hours || "date_overrides" in profile.opening_hours)) && (
                  <div className="p-3 rounded-xl bg-blue-50/80 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-900/40 text-xs text-blue-700 dark:text-blue-300 flex items-center justify-between gap-2">
                    <span>{fr ? "Les plages horaires de votre entreprise sont synchronisées depuis le CRM. Vous pouvez consulter les créneaux ci-dessous." : "Your opening hours are synced from the CRM module. You can view them below."}</span>
                    <Link href="/crm" className="underline font-bold shrink-0">{fr ? "Gérer dans le CRM →" : "Manage in CRM →"}</Link>
                  </div>
                )}
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
                    if (ok) {
                      setOpenSection(2);
                      setCurrentStep(2);
                    }
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
        </div>

        {/* ========================================================
            ACCORDION 2: MA RÉCEPTIONNISTE IA
            ======================================================== */}
        <div className="rounded-2xl border border-slate-200/80 dark:border-white/[0.08] bg-white dark:bg-[#0B132B] shadow-sm overflow-hidden transition-all">
          <button
            type="button"
            onClick={() => {
              setSaveFeedback(null);
              setOpenSection(openSection === 2 ? null : 2);
              setCurrentStep(2);
            }}
            className="w-full p-4 sm:p-5 flex items-center justify-between text-left hover:bg-slate-50/50 dark:hover:bg-slate-900/50 transition cursor-pointer select-none"
          >
            <div className="flex items-center gap-3.5">
              <div className="w-8 h-8 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 flex items-center justify-center shrink-0">
                <Bot className="w-4 h-4" />
              </div>
              <div>
                <h4 className="text-sm font-extrabold text-slate-900 dark:text-white">
                  {fr ? "2. Ma réceptionniste IA" : "2. My AI Receptionist"}
                </h4>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  {fr ? "Voix, personnalité et conversations" : "Voice, personality & conversations"}
                </p>
              </div>
            </div>
            <div className="text-slate-400">
              {openSection === 2 ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
            </div>
          </button>

          {openSection === 2 && (
            <div className="p-5 sm:p-6 border-t border-slate-100 dark:border-white/[0.06] space-y-6 animate-in fade-in duration-200">
              {/* UNE IA ADAPTÉE À CHAQUE INDUSTRIE */}
              <div className="space-y-4 pb-4 border-b border-slate-100 dark:border-white/[0.06]">
                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-sm">🏢</span>
                      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-900 dark:text-white">
                        {ui.sectionTitle}
                      </h4>
                    </div>
                    {selectedIndustries.length > 0 && (
                      <span className="text-[11px] font-semibold text-[#0076FF] bg-blue-500/10 px-2.5 py-0.5 rounded-full border border-blue-500/20">
                        {selectedIndustries.length} {ui.selectedCount}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    {ui.sectionSubtitle}
                  </p>
                </div>

                {/* Search & Categories (Available when expanded or search is active) */}
                {isExpandedCatalog && (
                  <div className="space-y-2.5 pt-1 animate-in fade-in duration-200">
                    <div className="relative">
                      <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                      <input
                        type="text"
                        value={industrySearch}
                        onChange={(e) => setIndustrySearch(e.target.value)}
                        placeholder={ui.searchPlaceholder}
                        className="w-full pl-10 pr-4 py-2 rounded-xl text-xs bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder:text-slate-500 focus:outline-hidden focus:border-[#0076FF]"
                      />
                    </div>

                    <div className="flex flex-wrap items-center gap-1.5 overflow-x-auto pb-1">
                      {INDUSTRY_CATEGORIES.map((cat) => (
                        <button
                          key={cat.id}
                          type="button"
                          onClick={() => setSelectedCategory(cat.id)}
                          className={`px-3 py-1 rounded-full text-[11px] font-semibold transition shrink-0 ${
                            selectedCategory === cat.id
                              ? "bg-[#0076FF] text-white shadow-xs"
                              : "bg-slate-100 dark:bg-slate-800/80 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white border border-transparent hover:border-slate-300 dark:hover:border-slate-700"
                          }`}
                        >
                          {getLocalizedCategory(cat.id, locale)}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Responsive Grid: 4 cols on desktop, 2 on tablet, 1 on mobile */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
                  {filteredIndustries.map((ind) => {
                    const isSelected = selectedIndustries.includes(ind.id) || selectedIndustry === ind.id;
                    const localized = getLocalizedIndustry(ind.id, locale);
                    const title = localized?.name ?? (fr ? ind.nameFr : ind.nameEn);
                    const desc = localized?.desc ?? (fr ? ind.descFr : ind.descEn);
                    const isImgFailed = failedImages[ind.id] || false;

                    return (
                      <div
                        key={ind.id}
                        onClick={() => {
                          const nextIndustries = selectedIndustries.includes(ind.id)
                            ? selectedIndustries.filter((id) => id !== ind.id)
                            : [...selectedIndustries, ind.id];
                          setSelectedIndustries(nextIndustries);
                          const nextPrimary = nextIndustries.length > 0
                            ? (nextIndustries.includes(ind.id) ? ind.id : nextIndustries[0])
                            : "";
                          setSelectedIndustry(nextPrimary);
                          setProfile((p) => ({
                            ...p,
                            industry: (nextPrimary === "custom" || nextPrimary === "other") && customIndustryName
                              ? customIndustryName
                              : (nextPrimary ? (getLocalizedIndustry(nextPrimary, locale)?.name || nextPrimary) : ""),
                          }));
                        }}
                        className={`group relative rounded-2xl overflow-hidden border cursor-pointer transition flex flex-col justify-between ${
                          isSelected
                            ? "border-[#0076FF] ring-2 ring-blue-500/30 bg-slate-50 dark:bg-slate-900"
                            : "border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0F172A] hover:border-slate-300 dark:hover:border-slate-700"
                        }`}
                      >
                        <div className="relative h-32 w-full overflow-hidden bg-slate-100 dark:bg-slate-800">
                          <img
                            src={isImgFailed ? ind.fallbackSvg : ind.image}
                            alt={title}
                            onError={(e) => {
                              const target = e.currentTarget as HTMLImageElement;
                              target.onerror = null;
                              setFailedImages((prev) => ({ ...prev, [ind.id]: true }));
                              target.src = ind.fallbackSvg;
                            }}
                            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                          />
                          <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent" />
                          {isSelected ? (
                            <div className="absolute top-2.5 right-2.5 p-1 rounded-md bg-[#0076FF] text-white shadow-xs">
                              <Check className="w-3.5 h-3.5" />
                            </div>
                          ) : (
                            <div className="absolute top-2.5 right-2.5 p-1 rounded-md bg-black/50 text-white/90">
                              <Bookmark className="w-3.5 h-3.5" />
                            </div>
                          )}
                        </div>
                        <div className="p-3.5 space-y-1">
                          <div className="flex items-center gap-1.5">
                            <span className="text-sm shrink-0">{ind.icon}</span>
                            <h5 className="font-extrabold text-xs text-slate-900 dark:text-white truncate">
                              {title}
                            </h5>
                          </div>
                          <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-snug line-clamp-2">
                            {desc}
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* + Voir plus d'industries Toggle Button */}
                <div className="flex justify-center pt-2">
                  <button
                    type="button"
                    onClick={() => setIsExpandedCatalog((prev) => !prev)}
                    className="inline-flex items-center gap-2 px-6 py-2.5 rounded-full text-xs font-bold border border-slate-300 dark:border-slate-700 hover:border-blue-500 bg-white dark:bg-[#0F172A] text-slate-800 dark:text-slate-200 transition shadow-xs hover:shadow-sm"
                  >
                    {isExpandedCatalog ? (
                      <>
                        <ChevronUp className="w-4 h-4 text-[#0076FF]" />
                        <span>{ui.collapseButton}</span>
                      </>
                    ) : (
                      <>
                        <span className="text-[#0076FF] font-extrabold text-sm">+</span>
                        <span>{ui.expandButton}</span>
                      </>
                    )}
                  </button>
                </div>

                {/* Custom Industry Input if "custom" or "other" is selected */}
                {(selectedIndustries.includes("custom") || selectedIndustries.includes("other") || selectedIndustry === "custom" || selectedIndustry === "other") && (
                  <div className="p-4 rounded-2xl border border-blue-500/30 bg-blue-500/5 space-y-2 animate-in fade-in duration-200">
                    <label className="block text-xs font-bold text-slate-900 dark:text-white">
                      {ui.customIndustryPrompt}
                    </label>
                    <input
                      type="text"
                      value={customIndustryName}
                      onChange={(e) => {
                        setCustomIndustryName(e.target.value);
                        setProfile((p) => ({ ...p, industry: e.target.value }));
                      }}
                      placeholder={ui.customIndustryPlaceholder}
                      className="w-full max-w-lg px-3.5 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs text-slate-900 dark:text-white focus:outline-hidden focus:border-[#0076FF]"
                    />
                  </div>
                )}

                {/* Voice Capability Adaptation Suggestions Panel */}
                {selectedIndustries.length === 0 && !selectedIndustry ? (
                  <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 text-center">
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      {ui.noIndustrySelected}
                    </p>
                  </div>
                ) : (
                  activePrimaryIndustry && (
                    <div className="p-4 rounded-2xl border border-blue-500/20 bg-blue-500/5 dark:bg-blue-950/20 space-y-3">
                      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-blue-500/10 pb-2.5">
                        <div className="flex items-center gap-2">
                          <Sparkles className="w-4 h-4 text-[#0076FF] shrink-0" />
                          <h5 className="text-xs font-bold text-slate-900 dark:text-white">
                            {ui.suggestionsTitle}{" "}
                            <span className="text-[#0076FF]">
                              {activeLocalizedPrimary?.name || (fr ? activePrimaryIndustry.nameFr : activePrimaryIndustry.nameEn)}
                            </span>
                          </h5>
                        </div>
                        <span className="text-[10px] font-semibold text-slate-500 dark:text-slate-400">
                          {ui.primarySector}
                        </span>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 pt-0.5">
                        {(activeLocalizedPrimary?.suggestedCapabilities || (fr ? activePrimaryIndustry.suggestedCapabilitiesFr : activePrimaryIndustry.suggestedCapabilitiesEn)).map((cap, i) => {
                          const lower = cap.toLowerCase();
                          const isCrm =
                            lower.includes("rendez-vous") ||
                            lower.includes("appointment") ||
                            lower.includes("booking") ||
                            lower.includes("réservation") ||
                            lower.includes("reservation") ||
                            lower.includes("consultation") ||
                            lower.includes("agenda") ||
                            lower.includes("visite") ||
                            lower.includes("crm");
                          const isRetail = lower.includes("stock") || lower.includes("pièce") || lower.includes("inventaire") || lower.includes("article") || lower.includes("produit") || lower.includes("inventory") || lower.includes("parts") || lower.includes("order") || lower.includes("commande");

                          let badgeText = ui.generalQa;
                          let badgeClass = "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400 border-slate-200 dark:border-slate-700";
                          let isModuleActive = true;

                          if (isCrm) {
                            if (crmEnabled) {
                              badgeText = ui.crmActive;
                              badgeClass = "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/70 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800/60";
                            } else {
                              badgeText = ui.crmRequired;
                              badgeClass = "bg-amber-50 text-amber-700 dark:bg-amber-950/70 dark:text-amber-400 border-amber-200 dark:border-amber-800/60";
                              isModuleActive = false;
                            }
                          } else if (isRetail) {
                            if (retailEnabled) {
                              badgeText = ui.retailActive;
                              badgeClass = "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/70 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800/60";
                            } else {
                              badgeText = ui.retailRequired;
                              badgeClass = "bg-amber-50 text-amber-700 dark:bg-amber-950/70 dark:text-amber-400 border-amber-200 dark:border-amber-800/60";
                              isModuleActive = false;
                            }
                          }

                          return (
                            <div key={i} className="flex flex-col gap-1 p-2.5 rounded-xl bg-white/70 dark:bg-slate-900/70 border border-slate-200/60 dark:border-slate-800/60">
                              <div className="flex items-start gap-2 text-xs text-slate-700 dark:text-slate-200">
                                {isModuleActive ? (
                                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0 mt-0.5" />
                                ) : (
                                  <Info className="w-3.5 h-3.5 text-amber-500 shrink-0 mt-0.5" />
                                )}
                                <span className="leading-snug">{cap}</span>
                              </div>
                              <div className="pl-5.5">
                                <span className={`inline-block px-2 py-0.5 rounded-md text-[10px] font-semibold border ${badgeClass}`}>
                                  {badgeText}
                                </span>
                              </div>
                            </div>
                          );
                        })}
                      </div>

                      <p className="text-[11px] text-slate-500 dark:text-slate-400 italic pt-1 border-t border-blue-500/10">
                        ℹ️ {ui.suggestionsDisclaimer}
                      </p>
                    </div>
                  )
                )}
              </div>

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

              {/* SPOKEN BUSINESS NAME & PRONUNCIATION */}
              <div className="p-4 rounded-2xl border border-blue-200/80 dark:border-blue-900/60 bg-blue-50/40 dark:bg-blue-950/20 space-y-3">
                <div>
                  <div className="flex items-center justify-between gap-2">
                    <label className="block text-xs font-bold text-slate-800 dark:text-slate-200">
                      {fr
                        ? "Comment votre entreprise doit-elle être prononcée par l'agent vocal ?"
                        : "How should your business name be pronounced by the voice agent?"}
                    </label>
                    <span className="text-[10px] font-semibold text-slate-400">
                      {fr ? "Personnalisation audio" : "Audio tuning"}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                    {fr
                      ? "Évite que l'agent ne prononce des tirets ou identifiants techniques (ex: « Produits Ero » au lieu de « Produits_Ero »)."
                      : "Ensures the agent uses a natural spoken identity instead of technical database slugs."}
                  </p>
                </div>

                <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                  <input
                    type="text"
                    value={customization.voice_display_name || ""}
                    onChange={(e) => {
                      const val = e.target.value;
                      setCustomization((c) => ({ ...c, voice_display_name: val, voice_pronunciation: val }));
                    }}
                    placeholder={profile.business_name ? profile.business_name.replace(/_/g, " ") : (fr ? "Ex: Produits Ero" : "Ex: Acme Corp")}
                    className="flex-1 px-3.5 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs font-semibold text-slate-900 dark:text-white focus:outline-hidden focus:border-[#0076FF]"
                  />
                  <button
                    type="button"
                    disabled={previewLoading}
                    onClick={() => {
                      const spokenName = customization.voice_display_name?.trim() || profile.business_name?.replace(/_/g, " ") || (fr ? "votre entreprise" : "your company");
                      const phrase = fr ? `Bienvenue chez ${spokenName}. Comment puis-je vous aider aujourd'hui ?` : `Welcome to ${spokenName}. How can I help you today?`;
                      void playPreviewAudio(phrase);
                    }}
                    className="px-4 py-2.5 rounded-xl bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-[#0076FF] text-xs font-bold hover:bg-blue-50 dark:hover:bg-blue-950/40 transition flex items-center justify-center gap-1.5 shrink-0"
                  >
                    {previewLoading ? (
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Volume2 className="w-3.5 h-3.5" />
                    )}
                    <span>{fr ? "Écouter un aperçu" : "Listen to preview"}</span>
                  </button>
                </div>
              </div>

              {/* PERSONALITY PROFILE, HUMOR & NATURAL INTERRUPTIONS */}
              <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 space-y-4">
                <div>
                  <label className="block text-xs font-bold text-slate-800 dark:text-slate-200 mb-2">
                    {fr ? "Personnalité de l'assistant :" : "Assistant Personality:"}
                  </label>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                    {[
                      {
                        id: "professional_premium_warm",
                        label: fr ? "Professionnel premium — chaleureux et naturel" : "Premium Professional — warm & natural",
                      },
                      {
                        id: "formal",
                        label: fr ? "Formel — sérieux et institutionnel" : "Formal — serious & institutional",
                      },
                      {
                        id: "casual_friendly",
                        label: fr ? "Décontracté — amical et dynamique" : "Casual — friendly & dynamic",
                      },
                    ].map((preset) => {
                      const active = (customization.personality_preset || "professional_premium_warm") === preset.id;
                      return (
                        <button
                          key={preset.id}
                          type="button"
                          onClick={() => setCustomization((c) => ({ ...c, personality_preset: preset.id }))}
                          className={`p-3 rounded-xl border text-left text-xs font-semibold transition ${
                            active
                              ? "border-[#0076FF] bg-blue-50/70 dark:bg-blue-950/40 text-[#0076FF]"
                              : "border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300"
                          }`}
                        >
                          {preset.label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-center pt-1">
                  <div>
                    <div className="flex items-center justify-between text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                      <span>{fr ? "Humour et spontanéité" : "Humor & spontaneity"}</span>
                      <span className="text-[#0076FF]">{customization.humor_level ?? 40}%</span>
                    </div>
                    <input
                      type="range"
                      min={0}
                      max={100}
                      step={5}
                      value={customization.humor_level ?? 40}
                      onChange={(e) => setCustomization((c) => ({ ...c, humor_level: Number(e.target.value) }))}
                      className="w-full accent-[#0076FF]"
                    />
                  </div>

                  <div className="space-y-2">
                    <label className="flex items-center gap-2.5 cursor-pointer text-xs font-semibold text-slate-700 dark:text-slate-300">
                      <input
                        type="checkbox"
                        checked={customization.allow_natural_interruptions ?? true}
                        onChange={(e) => setCustomization((c) => ({ ...c, allow_natural_interruptions: e.target.checked }))}
                        className="rounded border-slate-300 text-[#0076FF] focus:ring-[#0076FF]"
                      />
                      <span>
                        {fr
                          ? "Permettre les interruptions naturelles pendant les conversations"
                          : "Allow natural interruptions (barge-in) during conversations"}
                      </span>
                    </label>
                    <label className="flex items-center gap-2.5 cursor-pointer text-xs font-semibold text-slate-700 dark:text-slate-300">
                      <input
                        type="checkbox"
                        checked={customization.gemini_live_enabled ?? false}
                        onChange={(e) =>
                          setCustomization((c) => ({
                            ...c,
                            gemini_live_enabled: e.target.checked,
                            realtime_provider: e.target.checked ? "gemini_live" : "retell",
                          }))
                        }
                        className="rounded border-slate-300 text-[#0076FF] focus:ring-[#0076FF]"
                      />
                      <span>
                        {fr
                          ? "Activer Google Gemini Live (Audio temps réel bidirectionnel + repli automatique)"
                          : "Enable Google Gemini Live (Bidirectional real-time audio + automatic fallback)"}
                      </span>
                    </label>
                  </div>
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
                    placeholder={fr ? `Ex: Bonjour et bienvenue chez ${customization.voice_display_name || profile.business_name || "notre entreprise"} ! En quoi puis-je vous renseigner ?` : "Ex: Hello and welcome! How can I help you today?"}
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
                  onClick={() => {
                    setOpenSection(1);
                    setCurrentStep(1);
                  }}
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
                    if (ok) {
                      setOpenSection(3);
                      setCurrentStep(3);
                    }
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
        </div>

        {/* ========================================================
            ACCORDION 3: CONNAISSANCES ET PERMISSIONS
            ======================================================== */}
        <div className="rounded-2xl border border-slate-200/80 dark:border-white/[0.08] bg-white dark:bg-[#0B132B] shadow-sm overflow-hidden transition-all">
          <button
            type="button"
            onClick={() => {
              setSaveFeedback(null);
              setOpenSection(openSection === 3 ? null : 3);
              setCurrentStep(3);
            }}
            className="w-full p-4 sm:p-5 flex items-center justify-between text-left hover:bg-slate-50/50 dark:hover:bg-slate-900/50 transition cursor-pointer select-none"
          >
            <div className="flex items-center gap-3.5">
              <div className="w-8 h-8 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 flex items-center justify-center shrink-0">
                <Layers className="w-4 h-4" />
              </div>
              <div>
                <h4 className="text-sm font-extrabold text-slate-900 dark:text-white">
                  {fr ? "3. Connaissances et permissions" : "3. Knowledge & Permissions"}
                </h4>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  {fr ? "Modules autorisés, données et actions" : "Authorized modules, data & actions"}
                </p>
              </div>
            </div>
            <div className="text-slate-400">
              {openSection === 3 ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
            </div>
          </button>

          {openSection === 3 && (
            <div className="p-5 sm:p-6 border-t border-slate-100 dark:border-white/[0.06] space-y-6 animate-in fade-in duration-200">
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
                  onClick={() => {
                    setOpenSection(2);
                    setCurrentStep(2);
                  }}
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
                    if (ok) {
                      setOpenSection(4);
                      setCurrentStep(4);
                    }
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
        </div>

        {/* ========================================================
            ACCORDION 4: TÉLÉPHONE ET EMPLOYÉS
            ======================================================== */}
        <div className="rounded-2xl border border-slate-200/80 dark:border-white/[0.08] bg-white dark:bg-[#0B132B] shadow-sm overflow-hidden transition-all">
          <button
            type="button"
            onClick={() => {
              setSaveFeedback(null);
              setOpenSection(openSection === 4 ? null : 4);
              setCurrentStep(4);
            }}
            className="w-full p-4 sm:p-5 flex items-center justify-between text-left hover:bg-slate-50/50 dark:hover:bg-slate-900/50 transition cursor-pointer select-none"
          >
            <div className="flex items-center gap-3.5">
              <div className="w-8 h-8 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 flex items-center justify-center shrink-0">
                <PhoneCall className="w-4 h-4" />
              </div>
              <div>
                <h4 className="text-sm font-extrabold text-slate-900 dark:text-white">
                  {fr ? "4. Téléphone et employés" : "4. Phone & Employees"}
                </h4>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  {fr ? "Numéro, IVR, NIP et routage" : "Number, IVR, PIN & routing"}
                </p>
              </div>
            </div>
            <div className="text-slate-400">
              {openSection === 4 ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
            </div>
          </button>

          {openSection === 4 && (
            <div className="p-5 sm:p-6 border-t border-slate-100 dark:border-white/[0.06] space-y-6 animate-in fade-in duration-200">
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
                        {assignedNumber || (fr ? "Numéro en attente d'assignation" : "Pending phone number assignment")}
                      </h4>
                    </div>
                  </div>

                  <span className={`self-start sm:self-auto px-3 py-1 rounded-full text-xs font-bold ${assignedNumber ? "bg-blue-100 dark:bg-blue-950 text-[#0076FF] border border-blue-200 dark:border-blue-900" : "bg-slate-100 dark:bg-slate-800 text-slate-500 border border-slate-200 dark:border-slate-700"}`}>
                    {assignedNumber ? (fr ? "Numéro vérifié" : "Verified Line") : (fr ? "En attente" : "Pending")}
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
                        ? "Accueil direct sans AUCUN NIP. Le client pose ses questions sur vos produits, vos tarifs ou réserve un créneau."
                        : "Direct access with ZERO PIN. Caller inquires about products, prices or books appointments immediately."}
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
              <div className="p-6 rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50 space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-2.5">
                    <div className="w-8 h-8 rounded-xl bg-blue-100 dark:bg-blue-900/40 text-[#0076FF] flex items-center justify-center shrink-0">
                      <Lock className="w-4 h-4" />
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-slate-900 dark:text-white">
                        {pinStatus?.configured
                          ? (fr ? "Modifier votre code NIP personnel employé" : "Update your employee PIN")
                          : (fr ? "Définir votre code NIP personnel employé" : "Set your employee PIN")}
                      </h4>
                      <p className="text-xs text-slate-500 mt-0.5">
                        {fr
                          ? "Permet d'accéder au mode interne lorsque vous appelez votre numéro dédié et appuyez sur 1."
                          : "Allows you to access the staff private mode when dialing your dedicated line and pressing 1."}
                      </p>
                    </div>
                  </div>

                  {pinStatus?.configured ? (
                    pinStatus.is_locked ? (
                      <span className="self-start sm:self-auto px-3 py-1 rounded-full text-xs font-bold bg-rose-50 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300 border border-rose-200 dark:border-rose-800">
                        {fr ? "NIP verrouillé" : "PIN locked"}
                      </span>
                    ) : !pinStatus.enabled ? (
                      <span className="self-start sm:self-auto px-3 py-1 rounded-full text-xs font-bold bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300 border border-amber-200 dark:border-amber-800">
                        {fr ? "NIP désactivé" : "PIN disabled"}
                      </span>
                    ) : (
                      <span className="self-start sm:self-auto px-3 py-1 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
                        {fr ? "NIP actif et configuré" : "PIN active & configured"}
                      </span>
                    )
                  ) : (
                    <span className="self-start sm:self-auto px-3 py-1 rounded-full text-xs font-bold bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400 border border-slate-200 dark:border-slate-700">
                      {fr ? "NIP non configuré" : "PIN not configured"}
                    </span>
                  )}
                </div>

                {(pinStatus?.is_locked || Boolean(pinStatus?.locked_until) || (Boolean(pinStatus?.failed_attempts) && (pinStatus?.failed_attempts ?? 0) >= 3)) && (
                  <div className="p-3.5 rounded-xl bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-xs text-amber-800 dark:text-amber-200">
                    {fr
                      ? `Attention : Le NIP est verrouillé suite à ${pinStatus?.failed_attempts || 3} tentatives erronées. La configuration avec votre mot de passe réinitialisera ce verrou.`
                      : `Warning: PIN is locked after ${pinStatus?.failed_attempts || 3} failed attempts. Setting it with your password will reset this lock.`}
                  </div>
                )}

                <div className="space-y-3.5 pt-1">
                  <div>
                    <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 mb-1.5">
                      {fr ? "Mot de passe actuel de votre compte Avenqo *" : "Current Avenqo Account Password *"}
                    </label>
                    <input
                      type="password"
                      placeholder={fr ? "Mot de passe actuel (requis pour sécuriser le NIP)" : "Current password (required to secure PIN)"}
                      value={currentPassword}
                      onChange={(e) => setCurrentPassword(e.target.value)}
                      className="w-full max-w-md px-3.5 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs text-slate-900 dark:text-white focus:outline-hidden focus:border-[#0076FF]"
                    />
                  </div>

                  <div>
                    <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 mb-1.5">
                      {pinStatus?.configured
                        ? (fr ? "Numéro de téléphone employé (laisser vide pour conserver le numéro)" : "Authorized Staff Phone (leave blank to keep current number)")
                        : (fr ? "Numéro de téléphone employé autorisé *" : "Authorized Staff Phone Number *")}
                    </label>

                    {pinStatus?.configured && pinStatus?.phone_number ? (
                      <div className="mb-2 max-w-md px-3.5 py-2 rounded-xl bg-slate-100 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700/60 flex items-center justify-between text-xs">
                        <span className="text-slate-500 dark:text-slate-400">
                          {fr ? "Numéro actuellement enregistré :" : "Currently registered number:"}
                        </span>
                        <span className="font-mono font-bold text-slate-900 dark:text-white">
                          {pinStatus.phone_number}
                        </span>
                      </div>
                    ) : null}

                    <input
                      type="tel"
                      placeholder={pinStatus?.configured ? (fr ? "Laisser vide pour conserver, ou nouveau +1514..." : "Leave blank to keep, or enter new +1...") : "+15142955720"}
                      value={employeePhone}
                      onChange={(e) => setEmployeePhone(e.target.value)}
                      onBlur={() => {
                        const raw = employeePhone.trim().replace(/\D/g, "");
                        if (raw.length === 10) {
                          setEmployeePhone(`+1${raw}`);
                        } else if (raw.length === 11 && raw.startsWith("1")) {
                          setEmployeePhone(`+${raw}`);
                        }
                      }}
                      className="w-full max-w-md px-3.5 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs font-mono font-bold text-slate-900 dark:text-white focus:outline-hidden focus:border-[#0076FF]"
                    />
                    {pinStatus?.configured ? (
                      <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                        {fr
                          ? "Pour une simple rotation de NIP, laissez ce champ vide. Votre numéro actif reste inchangé côté serveur."
                          : "For a simple PIN rotation, leave this field blank. Your active registered number will be preserved on the server."}
                      </p>
                    ) : null}
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-md">
                    <div>
                      <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 mb-1.5">
                        {pinStatus?.configured
                          ? (fr ? "Nouveau code NIP (6 à 12 chiffres) *" : "New PIN (6 to 12 digits) *")
                          : (fr ? "Code NIP (6 à 12 chiffres) *" : "PIN (6 to 12 digits) *")}
                      </label>
                      <input
                        type="password"
                        pattern="[0-9]*"
                        maxLength={12}
                        placeholder="••••••"
                        value={employeePin}
                        onChange={(e) => setEmployeePin(e.target.value.replace(/\D/g, ""))}
                        className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs font-mono font-bold text-slate-900 dark:text-white focus:outline-hidden focus:border-[#0076FF]"
                      />
                    </div>

                    <div>
                      <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 mb-1.5">
                        {fr ? "Confirmer le code NIP *" : "Confirm PIN *"}
                      </label>
                      <input
                        type="password"
                        pattern="[0-9]*"
                        maxLength={12}
                        placeholder="••••••"
                        value={employeePinConfirm}
                        onChange={(e) => setEmployeePinConfirm(e.target.value.replace(/\D/g, ""))}
                        className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs font-mono font-bold text-slate-900 dark:text-white focus:outline-hidden focus:border-[#0076FF]"
                      />
                    </div>
                  </div>

                  <div className="pt-2">
                    <button
                      type="button"
                      disabled={employeePinSaving || employeePin.length < 6 || !currentPassword.trim() || (!employeePhone.trim() && !pinStatus?.configured && !pinStatus?.phone_number)}
                      onClick={savePersonalPin}
                      className="px-5 py-2.5 rounded-xl bg-[#0076FF] hover:bg-blue-600 text-white text-xs font-bold shadow-xs transition disabled:opacity-50 flex items-center gap-2"
                    >
                      {employeePinSaving ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : null}
                      {pinStatus?.configured ? (fr ? "Mettre à jour le NIP" : "Update PIN") : (fr ? "Enregistrer le NIP" : "Save PIN")}
                    </button>
                  </div>
                </div>

                {employeePinFeedback && (
                  <div
                    className={`p-3.5 rounded-xl text-xs font-semibold border ${
                      employeePinFeedback.type === "success"
                        ? "bg-emerald-50 text-emerald-800 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-200 dark:border-emerald-800"
                        : "bg-red-50 text-red-800 border-red-200 dark:bg-red-950/40 dark:text-red-200 dark:border-red-800"
                    }`}
                  >
                    {employeePinFeedback.message}
                  </div>
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
                  onClick={() => {
                    setOpenSection(3);
                    setCurrentStep(3);
                  }}
                  className="px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-50 transition flex items-center gap-1.5"
                >
                  <ArrowLeft className="w-3.5 h-3.5" />
                  <span>{fr ? "Précédent" : "Previous"}</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setOpenSection(5);
                    setCurrentStep(5);
                  }}
                  className="px-5 py-2.5 rounded-xl bg-[#0076FF] hover:bg-blue-600 text-white font-bold text-xs shadow-md transition flex items-center gap-2"
                >
                  <span>{fr ? "Passer au test et activation" : "Proceed to Test & Activate"}</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* ========================================================
            ACCORDION 5: TESTER ET ACTIVER
            ======================================================== */}
        <div className="rounded-2xl border border-slate-200/80 dark:border-white/[0.08] bg-white dark:bg-[#0B132B] shadow-sm overflow-hidden transition-all">
          <button
            type="button"
            onClick={() => {
              setSaveFeedback(null);
              setOpenSection(openSection === 5 ? null : 5);
              setCurrentStep(5);
            }}
            className="w-full p-4 sm:p-5 flex items-center justify-between text-left hover:bg-slate-50/50 dark:hover:bg-slate-900/50 transition cursor-pointer select-none"
          >
            <div className="flex items-center gap-3.5">
              <div className="w-8 h-8 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 flex items-center justify-center shrink-0">
                <CheckCircle2 className="w-4 h-4" />
              </div>
              <div>
                <h4 className="text-sm font-extrabold text-slate-900 dark:text-white">
                  {fr ? "5. Tester et activer" : "5. Test & Activate"}
                </h4>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  {fr ? "Diagnostic et mise en service" : "Diagnostics & activation"}
                </p>
              </div>
            </div>
            <div className="text-slate-400">
              {openSection === 5 ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
            </div>
          </button>

          {openSection === 5 && (
            <div className="p-5 sm:p-6 border-t border-slate-100 dark:border-white/[0.06] space-y-6 animate-in fade-in duration-200">
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
                onRefreshParent={onRefreshStatus}
                onLifecycleChange={setLifecycleData}
              />

              <div className="flex items-center justify-between pt-4 border-t border-slate-100 dark:border-white/[0.06] flex-wrap gap-3">
                <button
                  type="button"
                  onClick={() => {
                    setOpenSection(4);
                    setCurrentStep(4);
                  }}
                  className="px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-50 transition flex items-center gap-1.5"
                >
                  <ArrowLeft className="w-3.5 h-3.5" />
                  <span>{fr ? "Précédent" : "Previous"}</span>
                </button>

                {(() => {
                  const isPrerequisitesComplete = Boolean(
                    lifecycleData?.status === "ACTIVE" ||
                    lifecycleData?.can_activate ||
                    (lifecycleData?.checklist?.phone_bound &&
                     lifecycleData?.checklist?.voice_selected &&
                     lifecycleData?.checklist?.identity_configured &&
                     lifecycleData?.checklist?.tenant_valid &&
                     lifecycleData?.checklist?.subscription_active)
                  );

                  return isPrerequisitesComplete ? (
                    <button
                      type="button"
                      onClick={() => {
                        setIsConfigDropdownOpen(false);
                        setHasInteractedWithDropdown(true);
                        onRefreshStatus?.();
                        window.scrollTo({ top: 0, behavior: "smooth" });
                      }}
                      className="px-6 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-extrabold shadow-md transition flex items-center gap-2 cursor-pointer"
                    >
                      <CheckCircle2 className="w-4 h-4" />
                      <span>{fr ? "Terminer et enrouler la configuration" : "Complete & Collapse Setup"}</span>
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        setIsConfigDropdownOpen(false);
                        setHasInteractedWithDropdown(true);
                        window.scrollTo({ top: 0, behavior: "smooth" });
                      }}
                      className="px-5 py-2.5 rounded-xl bg-slate-700 hover:bg-slate-800 text-white text-xs font-bold shadow-sm transition flex items-center gap-2 cursor-pointer"
                    >
                      <ChevronUp className="w-4 h-4" />
                      <span>{fr ? "Fermer la configuration" : "Close Setup"}</span>
                    </button>
                  );
                })()}
              </div>
            </div>
          )}
        </div>
      </div>
          </div>
        )}
      </div>

      {/* PARAMÈTRES AVANCÉS (FACULTATIF) */}
      <div className="rounded-2xl border border-slate-200/80 dark:border-white/[0.08] bg-white dark:bg-[#0B132B] shadow-sm overflow-hidden transition-all">
        <button
          type="button"
          onClick={() => setShowAdvancedParams(!showAdvancedParams)}
          className="w-full p-4 sm:p-5 flex items-center justify-between text-left hover:bg-slate-50/50 dark:hover:bg-slate-900/50 transition cursor-pointer select-none"
        >
          <div className="flex items-center gap-3.5">
            <div className="w-8 h-8 rounded-xl bg-purple-50 dark:bg-purple-950/50 text-purple-600 dark:text-purple-400 flex items-center justify-center shrink-0">
              <Sliders className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h4 className="text-sm font-extrabold text-slate-900 dark:text-white">
                  {fr ? "Paramètres avancés" : "Advanced Settings"}
                </h4>
                <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700">
                  {fr ? "Facultatif" : "Optional"}
                </span>
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                {fr
                  ? "Budgets fournisseur, codecs, diagnostics, modèles de secours, latence, sécurité et télémétrie."
                  : "Provider budgets, codecs, diagnostics, fallback models, latency, security and telemetry."}
              </p>
            </div>
          </div>
          <div className="text-slate-400">
            {showAdvancedParams ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
          </div>
        </button>
        {showAdvancedParams && (
          <div className="p-5 sm:p-6 border-t border-slate-100 dark:border-white/[0.06] space-y-4 text-xs text-slate-600 dark:text-slate-300 animate-in fade-in">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 space-y-1.5">
                <span className="text-[10px] font-bold uppercase tracking-wider text-purple-600 dark:text-purple-400">
                  {fr ? "Fournisseur Realtime Actif" : "Active Realtime Provider"}
                </span>
                <p className="font-extrabold text-slate-900 dark:text-white text-sm">
                  Gemini Live (gemini-3.8-live)
                </p>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">
                  {fr
                    ? "Basculement automatique vers OpenAI Realtime en cas d'indisponibilité."
                    : "Automated failover to OpenAI Realtime in case of outage."}
                </p>
              </div>

              <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 space-y-1.5">
                <span className="text-[10px] font-bold uppercase tracking-wider text-blue-600 dark:text-blue-400">
                  {fr ? "Codecs & Traitement Audio" : "Audio Codecs & Processing"}
                </span>
                <p className="font-extrabold text-slate-900 dark:text-white text-sm">
                  PCM 16 kHz / 24 kHz · G.711 μ-law
                </p>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">
                  {fr
                    ? "Trames de 20 à 40 ms, buffering ultra-court et effacement immédiat sur interruption."
                    : "20–40 ms frames, minimal buffering, immediate barge-in flush."}
                </p>
              </div>

              <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 space-y-1.5">
                <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">
                  {fr ? "Budget de Latence & Fluidité" : "Latency Budget & Flow"}
                </span>
                <p className="font-extrabold text-slate-900 dark:text-white text-sm">
                  {"< 1 500 ms · Message d'attente à 2,0s"}
                </p>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">
                  {fr
                    ? "Annonce sonore « Un instant, je vérifie... » pour rassurer l'appelant dès 2 secondes."
                    : "Audible thinking phrase prevents dead air during deep tool lookups."}
                </p>
              </div>

              <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 space-y-1.5">
                <span className="text-[10px] font-bold uppercase tracking-wider text-amber-600 dark:text-amber-400">
                  {fr ? "Sécurité & Multi-Tenant" : "Security & Multi-Tenant"}
                </span>
                <p className="font-extrabold text-slate-900 dark:text-white text-sm">
                  Argon2 · Fail-Closed · Zero Brute-Force
                </p>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">
                  {fr
                    ? "Isolation stricte des données de l'entreprise et rejet par défaut sans autorisation."
                    : "Strict company data isolation with fail-closed server authorization."}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* SHOWCASE: 10 AMÉLIORATIONS PREMIUM */}
      <div className="space-y-4 pt-2">
        <div className="flex items-center gap-2">
          <span className="text-base">🌸</span>
          <h3 className="font-extrabold text-sm text-slate-900 dark:text-white">
            {fr ? "10 améliorations premium" : "10 Premium Improvements"}
          </h3>
        </div>

        <div className="rounded-2xl border border-slate-200/80 dark:border-white/[0.08] overflow-hidden bg-white dark:bg-[#0B132B] shadow-sm">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-slate-100 dark:border-white/[0.06] bg-slate-50/70 dark:bg-slate-900/50 text-slate-500 dark:text-slate-400 font-bold uppercase tracking-wider text-[10px]">
                <th className="p-3.5 w-1/3">{fr ? "Fonctionnalité" : "Feature"}</th>
                <th className="p-3.5">{fr ? "Ce que ça apporte" : "What it delivers"}</th>
                <th className="p-3.5 w-28 text-center">{fr ? "Statut" : "Status"}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-white/[0.04]">
              {premiumImprovements.map((item) => (
                <tr key={item.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-900/30 transition">
                  <td className="p-3.5 font-bold text-slate-900 dark:text-white whitespace-nowrap">
                    <span className="mr-1.5">{item.icon}</span>
                    <span>{item.title}</span>
                  </td>
                  <td className="p-3.5 text-slate-600 dark:text-slate-300 leading-relaxed">
                    {item.desc}
                  </td>
                  <td className="p-3.5 text-center whitespace-nowrap">
                    <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${item.statusClass}`}>
                      {item.statusLabel}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/30 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-slate-500 dark:text-slate-400">
          <p className="leading-relaxed">
            {fr
              ? "Google recommande notamment des blocs audio de 20 à 40 ms, un buffering réduit et l'effacement immédiat du son en attente après une interruption. Ce sont des optimisations concrètes à appliquer à notre connexion Gemini Live—Telnyx."
              : "Google specifically recommends 20–40 ms audio frames, reduced buffering, and immediate flush of queued audio upon interruption. These concrete optimizations are applied to our Gemini Live—Telnyx pipeline."}
          </p>
          <a
            href="https://ai.google.dev"
            target="_blank"
            rel="noreferrer"
            className="px-2.5 py-1 rounded-lg bg-slate-200 dark:bg-slate-800 hover:bg-slate-300 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 font-mono text-[11px] shrink-0 flex items-center gap-1 transition self-start sm:self-auto"
          >
            <span>ai.google.dev</span>
            <ExternalLink className="w-3 h-3" />
          </a>
        </div>
      </div>
    </div>
  );
}
