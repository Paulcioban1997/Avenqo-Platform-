"use client";

import React, { useState, useEffect } from "react";
import {
  X,
  Clock,
  Building2,
  Calendar,
  CheckCircle2,
  ArrowRight,
  ArrowLeft,
  Sparkles,
  Users,
  Briefcase,
  ShieldCheck,
  Plus,
  Trash2,
  AlertCircle,
  HelpCircle,
  Wrench,
  Stethoscope,
  Scissors,
  UtensilsCrossed,
  Landmark,
} from "lucide-react";
import type { AppTranslations } from "@/lib/i18n/app-dictionary";
import { useLocale } from "@/lib/i18n/locale-context";
import { apiFetch } from "@/lib/api-request";
import { getAuthHeaders } from "@/lib/api-headers";

interface CRMSetupWizardProps {
  isOpen: boolean;
  onClose: () => void;
  onComplete: () => void;
  t: AppTranslations;
  currentTimezone?: string;
}

const BUSINESS_TYPES = [
  { id: "clinic", label: "Clinique & Santé", icon: Stethoscope, defaultService: "Consultation générale", defaultDuration: 30 },
  { id: "garage", label: "Garage & Mécanique", icon: Wrench, defaultService: "Changement de pneus & Inspection", defaultDuration: 60 },
  { id: "salon", label: "Salon de beauté & Coiffure", icon: Scissors, defaultService: "Coupe & Coiffage", defaultDuration: 45 },
  { id: "restaurant", label: "Restaurant & Traiteur", icon: UtensilsCrossed, defaultService: "Réservation de table", defaultDuration: 90 },
  { id: "bank", label: "Banque & Finance", icon: Landmark, defaultService: "Conseil financier", defaultDuration: 45 },
  { id: "office", label: "Cabinet professionnel / Juridique", icon: Briefcase, defaultService: "Consultation professionnelle", defaultDuration: 60 },
  { id: "other", label: "Autre commerce / Service", icon: Building2, defaultService: "Rendez-vous client", defaultDuration: 60 },
];

const DAYS = [
  { key: "monday", label: "Lundi" },
  { key: "tuesday", label: "Mardi" },
  { key: "wednesday", label: "Mercredi" },
  { key: "thursday", label: "Jeudi" },
  { key: "friday", label: "Vendredi" },
  { key: "saturday", label: "Samedi" },
  { key: "sunday", label: "Dimanche" },
];

export function CRMSetupWizard({
  isOpen,
  onClose,
  onComplete,
  t,
  currentTimezone,
}: CRMSetupWizardProps) {
  const { locale } = useLocale();
  const [step, setStep] = useState(1);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form states
  const [businessType, setBusinessType] = useState("clinic");
  const [timezone, setTimezone] = useState(currentTimezone || "America/Montreal");

  // Weekly opening schedule
  const [weeklySchedule, setWeeklySchedule] = useState<Record<string, { enabled: boolean; open: string; close: string; lunchBreak: boolean; lunchStart: string; lunchEnd: string }>>({
    monday: { enabled: true, open: "09:00", close: "17:00", lunchBreak: true, lunchStart: "12:00", lunchEnd: "13:00" },
    tuesday: { enabled: true, open: "09:00", close: "17:00", lunchBreak: true, lunchStart: "12:00", lunchEnd: "13:00" },
    wednesday: { enabled: true, open: "09:00", close: "17:00", lunchBreak: true, lunchStart: "12:00", lunchEnd: "13:00" },
    thursday: { enabled: true, open: "09:00", close: "17:00", lunchBreak: true, lunchStart: "12:00", lunchEnd: "13:00" },
    friday: { enabled: true, open: "09:00", close: "17:00", lunchBreak: true, lunchStart: "12:00", lunchEnd: "13:00" },
    saturday: { enabled: false, open: "10:00", close: "15:00", lunchBreak: false, lunchStart: "12:00", lunchEnd: "13:00" },
    sunday: { enabled: false, open: "10:00", close: "15:00", lunchBreak: false, lunchStart: "12:00", lunchEnd: "13:00" },
  });

  // Services offered
  const [services, setServices] = useState<{ name: string; duration: number; price: number }[]>([
    { name: "Consultation initiale", duration: 60, price: 90 },
    { name: "Suivi de traitement", duration: 30, price: 50 },
  ]);
  const [newServiceName, setNewServiceName] = useState("");
  const [newServiceDuration, setNewServiceDuration] = useState(45);
  const [newServicePrice, setNewServicePrice] = useState(65);

  // Booking rules
  const [minLeadTimeHours, setMinLeadTimeHours] = useState(2);
  const [maxAdvanceDays, setMaxAdvanceDays] = useState(60);
  const [requireApproval, setRequireApproval] = useState(false);
  const [allowWeekend, setAllowWeekend] = useState(false);

  useEffect(() => {
    if (currentTimezone) {
      setTimezone(currentTimezone);
    }
  }, [currentTimezone]);

  if (!isOpen) return null;

  const handleAddService = () => {
    if (!newServiceName.trim()) return;
    setServices((prev) => [...prev, { name: newServiceName.trim(), duration: newServiceDuration, price: newServicePrice }]);
    setNewServiceName("");
    setNewServiceDuration(45);
    setNewServicePrice(60);
  };

  const handleRemoveService = (index: number) => {
    setServices((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSaveAll = async () => {
    setIsSubmitting(true);
    setError(null);
    try {
      const headers = { "Content-Type": "application/json", ...getAuthHeaders() };

      // Format weekly business hours
      const hoursPayload: Record<string, { open: string; close: string }[]> = {};
      Object.entries(weeklySchedule).forEach(([day, config]) => {
        if (!config.enabled) {
          hoursPayload[day] = [];
          return;
        }
        if (config.lunchBreak && config.lunchStart && config.lunchEnd && config.open < config.lunchStart && config.lunchEnd < config.close) {
          hoursPayload[day] = [
            { open: config.open, close: config.lunchStart },
            { open: config.lunchEnd, close: config.close },
          ];
        } else {
          hoursPayload[day] = [{ open: config.open, close: config.close }];
        }
      });

      // 1. Save business hours and timezone
      const hoursRes = await fetch("/api/v1/crm/settings/business-hours", {
        method: "PUT",
        headers,
        body: JSON.stringify({
          timezone,
          hours: hoursPayload,
        }),
      });

      if (!hoursRes.ok) {
        const errData = await hoursRes.json().catch(() => ({}));
        throw new Error(errData.detail || "Erreur lors de l'enregistrement des horaires.");
      }

      // 2. Persist configured services if none exist yet
      for (const svc of services) {
        await fetch("/api/v1/crm/services", {
          method: "POST",
          headers,
          body: JSON.stringify({
            name: svc.name,
            duration_minutes: svc.duration,
            price: svc.price,
            currency: "CAD",
            category: businessType,
          }),
        }).catch(() => {});
      }

      onComplete();
      onClose();
    } catch (err: any) {
      setError(err.message || "Une erreur est survenue lors de l'enregistrement.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-3xl bg-white dark:bg-[#0B132B] rounded-3xl border border-slate-200 dark:border-white/[0.12] shadow-2xl overflow-hidden max-h-[92vh] flex flex-col">
        {/* Wizard Header */}
        <div className="flex items-center justify-between px-8 py-5 border-b border-slate-100 dark:border-white/[0.08] bg-slate-50/60 dark:bg-white/[0.02]">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-2xl bg-gradient-to-tr from-[#0076FF] to-[#00D4FF] flex items-center justify-center text-white shadow-md shadow-blue-500/20">
              <Clock size={20} />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <span>Configuration de votre planning d'entreprise</span>
                <span className="text-[10px] font-extrabold uppercase px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-950/60 text-[#0076FF] dark:text-[#00D4FF]">
                  Étape {step} sur 4
                </span>
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Définissez vos horaires réels pour alimenter le calendrier CRM, Central AI et Voice AI.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-white/[0.06] transition"
          >
            <X size={18} />
          </button>
        </div>

        {/* Wizard Progress Bar */}
        <div className="h-1 w-full bg-slate-100 dark:bg-white/[0.06]">
          <div
            className="h-full bg-gradient-to-r from-[#0076FF] to-[#00D4FF] transition-all duration-300"
            style={{ width: `${(step / 4) * 100}%` }}
          />
        </div>

        {/* Wizard Body */}
        <div className="flex-1 overflow-y-auto p-8 space-y-6">
          {error && (
            <div className="p-4 rounded-2xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900/40 text-rose-700 dark:text-rose-300 text-xs flex items-center gap-2.5">
              <AlertCircle size={16} className="shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* STEP 1: Type d'entreprise & Fuseau horaire */}
          {step === 1 && (
            <div className="space-y-6">
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300 mb-2">
                  1. Quel est le type d'activité de votre entreprise ?
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {BUSINESS_TYPES.map((bt) => {
                    const Icon = bt.icon;
                    const isSelected = businessType === bt.id;
                    return (
                      <button
                        key={bt.id}
                        type="button"
                        onClick={() => {
                          setBusinessType(bt.id);
                          if (!services.some((s) => s.name === bt.defaultService)) {
                            setServices([{ name: bt.defaultService, duration: bt.defaultDuration, price: 80 }]);
                          }
                        }}
                        className={`flex items-center gap-3.5 p-4 rounded-2xl border text-left transition-all cursor-pointer ${
                          isSelected
                            ? "bg-blue-50/80 dark:bg-[#172652] border-[#0076FF] text-[#0076FF] dark:text-[#00D4FF] shadow-xs"
                            : "bg-white dark:bg-white/[0.02] border-slate-200/80 dark:border-white/[0.08] text-slate-700 dark:text-slate-300 hover:border-slate-300 dark:hover:border-white/[0.15]"
                        }`}
                      >
                        <div className={`p-2.5 rounded-xl ${isSelected ? "bg-[#0076FF] text-white" : "bg-slate-100 dark:bg-white/[0.06] text-slate-500"}`}>
                          <Icon size={18} />
                        </div>
                        <div>
                          <div className="font-bold text-xs">{bt.label}</div>
                          <div className="text-[10px] text-slate-400 mt-0.5">Ex: {bt.defaultService}</div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300 mb-2">
                  2. Fuseau horaire de votre établissement
                </label>
                <select
                  value={timezone}
                  onChange={(e) => setTimezone(e.target.value)}
                  className="w-full px-4 py-3 rounded-2xl bg-slate-50 dark:bg-white/[0.04] border border-slate-200 dark:border-white/[0.1] text-xs font-medium text-slate-900 dark:text-white"
                >
                  <option value="America/Montreal">Amérique / Montréal (EST / EDT)</option>
                  <option value="America/Toronto">Amérique / Toronto (EST / EDT)</option>
                  <option value="America/Vancouver">Amérique / Vancouver (PST / PDT)</option>
                  <option value="America/New_York">Amérique / New York (EST / EDT)</option>
                  <option value="Europe/Paris">Europe / Paris (CET / CEST)</option>
                  <option value="Europe/Bucharest">Europe / Bucarest (EET / EEST)</option>
                  <option value="Europe/London">Europe / Londres (GMT / BST)</option>
                  <option value="UTC">UTC Universel</option>
                </select>
                <p className="text-[11px] text-slate-400 mt-1.5">
                  Tous les créneaux proposés par Central AI et Voice AI seront rigoureusement ancrés sur ce fuseau.
                </p>
              </div>
            </div>
          )}

          {/* STEP 2: Jours & Heures d'ouverture */}
          {step === 2 && (
            <div className="space-y-4">
              <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-white/[0.06]">
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">
                    Jours d'ouverture et plages horaires
                  </h3>
                  <p className="text-[11px] text-slate-400">
                    Activez les jours ouvrés et renseignez les heures d'ouverture et pauses du midi.
                  </p>
                </div>
              </div>

              <div className="space-y-2.5">
                {DAYS.map((d) => {
                  const cfg = weeklySchedule[d.key];
                  return (
                    <div
                      key={d.key}
                      className={`p-3.5 rounded-2xl border transition-all ${
                        cfg.enabled
                          ? "bg-white dark:bg-white/[0.02] border-slate-200 dark:border-white/[0.08]"
                          : "bg-slate-50/50 dark:bg-white/[0.01] border-slate-100 dark:border-white/[0.04] opacity-60"
                      }`}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <label className="flex items-center gap-3 min-w-[120px] cursor-pointer">
                          <input
                            type="checkbox"
                            checked={cfg.enabled}
                            onChange={(e) => {
                              const enabled = e.target.checked;
                              setWeeklySchedule((prev) => ({
                                ...prev,
                                [d.key]: { ...prev[d.key], enabled },
                              }));
                            }}
                            className="rounded border-slate-300 text-[#0076FF] focus:ring-[#0076FF]"
                          />
                          <span className={`text-xs font-bold ${cfg.enabled ? "text-slate-900 dark:text-white" : "text-slate-400"}`}>
                            {d.label}
                          </span>
                        </label>

                        {cfg.enabled ? (
                          <div className="flex flex-wrap items-center gap-3 text-xs">
                            <div className="flex items-center gap-1.5">
                              <span className="text-[11px] text-slate-400">Ouvert :</span>
                              <input
                                type="time"
                                value={cfg.open}
                                onChange={(e) => {
                                  const open = e.target.value;
                                  setWeeklySchedule((prev) => ({
                                    ...prev,
                                    [d.key]: { ...prev[d.key], open },
                                  }));
                                }}
                                className="px-2 py-1 rounded-lg bg-slate-50 dark:bg-white/[0.04] border border-slate-200 dark:border-white/[0.1] text-xs font-semibold"
                              />
                              <span className="text-slate-400">à</span>
                              <input
                                type="time"
                                value={cfg.close}
                                onChange={(e) => {
                                  const close = e.target.value;
                                  setWeeklySchedule((prev) => ({
                                    ...prev,
                                    [d.key]: { ...prev[d.key], close },
                                  }));
                                }}
                                className="px-2 py-1 rounded-lg bg-slate-50 dark:bg-white/[0.04] border border-slate-200 dark:border-white/[0.1] text-xs font-semibold"
                              />
                            </div>

                            <label className="flex items-center gap-1.5 text-[11px] text-slate-500 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={cfg.lunchBreak}
                                onChange={(e) => {
                                  const lunchBreak = e.target.checked;
                                  setWeeklySchedule((prev) => ({
                                    ...prev,
                                    [d.key]: { ...prev[d.key], lunchBreak },
                                  }));
                                }}
                                className="rounded text-[#0076FF]"
                              />
                              <span>Pause midi</span>
                            </label>

                            {cfg.lunchBreak && (
                              <div className="flex items-center gap-1 text-[11px] text-slate-400">
                                <input
                                  type="time"
                                  value={cfg.lunchStart}
                                  onChange={(e) => {
                                    const lunchStart = e.target.value;
                                    setWeeklySchedule((prev) => ({
                                      ...prev,
                                      [d.key]: { ...prev[d.key], lunchStart },
                                    }));
                                  }}
                                  className="px-1.5 py-0.5 rounded bg-slate-50 dark:bg-white/[0.04] border border-slate-200 dark:border-white/[0.1] text-xs"
                                />
                                <span>-</span>
                                <input
                                  type="time"
                                  value={cfg.lunchEnd}
                                  onChange={(e) => {
                                    const lunchEnd = e.target.value;
                                    setWeeklySchedule((prev) => ({
                                      ...prev,
                                      [d.key]: { ...prev[d.key], lunchEnd },
                                    }));
                                  }}
                                  className="px-1.5 py-0.5 rounded bg-slate-50 dark:bg-white/[0.04] border border-slate-200 dark:border-white/[0.1] text-xs"
                                />
                              </div>
                            )}
                          </div>
                        ) : (
                          <span className="text-[11px] text-slate-400 italic">Fermé toute la journée</span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* STEP 3: Services & Durées */}
          {step === 3 && (
            <div className="space-y-5">
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">
                  Prestations proposées et durées estimées
                </h3>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  La durée permet au moteur d'affecter le créneau exact sans chevauchement.
                </p>
              </div>

              {/* Service list */}
              <div className="space-y-2">
                {services.map((svc, index) => (
                  <div
                    key={index}
                    className="flex items-center justify-between p-3.5 rounded-2xl bg-white dark:bg-white/[0.02] border border-slate-200/80 dark:border-white/[0.08]"
                  >
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded-xl bg-blue-50 dark:bg-blue-950/40 text-[#0076FF] dark:text-[#00D4FF]">
                        <Briefcase size={16} />
                      </div>
                      <div>
                        <div className="text-xs font-bold text-slate-900 dark:text-white">{svc.name}</div>
                        <div className="text-[10px] text-slate-400">
                          {svc.duration} minutes · {svc.price} CAD
                        </div>
                      </div>
                    </div>
                    {services.length > 1 && (
                      <button
                        type="button"
                        onClick={() => handleRemoveService(index)}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/20 transition"
                      >
                        <Trash2 size={15} />
                      </button>
                    )}
                  </div>
                ))}
              </div>

              {/* Add service form */}
              <div className="p-4 rounded-2xl bg-slate-50 dark:bg-white/[0.02] border border-dashed border-slate-200 dark:border-white/[0.08] space-y-3">
                <div className="text-xs font-semibold text-slate-700 dark:text-slate-300">Ajouter une prestation</div>
                <div className="grid grid-cols-1 sm:grid-cols-4 gap-2.5">
                  <input
                    type="text"
                    placeholder="Nom du service (ex: Suivi 45 min)"
                    value={newServiceName}
                    onChange={(e) => setNewServiceName(e.target.value)}
                    className="sm:col-span-2 px-3 py-2 rounded-xl bg-white dark:bg-white/[0.04] border border-slate-200 dark:border-white/[0.1] text-xs"
                  />
                  <div className="flex items-center gap-1">
                    <input
                      type="number"
                      min={10}
                      max={480}
                      step={5}
                      value={newServiceDuration}
                      onChange={(e) => setNewServiceDuration(Number(e.target.value))}
                      className="w-full px-3 py-2 rounded-xl bg-white dark:bg-white/[0.04] border border-slate-200 dark:border-white/[0.1] text-xs"
                    />
                    <span className="text-[10px] text-slate-400">min</span>
                  </div>
                  <button
                    type="button"
                    onClick={handleAddService}
                    className="px-4 py-2 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-bold flex items-center justify-center gap-1.5"
                  >
                    <Plus size={14} />
                    <span>Ajouter</span>
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* STEP 4: Politiques de réservation & Confirmation */}
          {step === 4 && (
            <div className="space-y-6">
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">
                  Règles & Politiques de réservation
                </h3>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Contrôlez les délais minimaux et le mode de confirmation.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="p-4 rounded-2xl bg-white dark:bg-white/[0.02] border border-slate-200/80 dark:border-white/[0.08] space-y-2">
                  <label className="block text-xs font-bold text-slate-800 dark:text-slate-200">
                    Délai de prévenance minimal
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      min={0}
                      max={72}
                      value={minLeadTimeHours}
                      onChange={(e) => setMinLeadTimeHours(Number(e.target.value))}
                      className="w-24 px-3 py-2 rounded-xl bg-slate-50 dark:bg-white/[0.04] border border-slate-200 dark:border-white/[0.1] text-xs font-bold"
                    />
                    <span className="text-xs text-slate-500">heures avant le créneau</span>
                  </div>
                  <p className="text-[10px] text-slate-400">
                    Empêche les clients ou l'IA de planifier un créneau au dernier moment sans préavis.
                  </p>
                </div>

                <div className="p-4 rounded-2xl bg-white dark:bg-white/[0.02] border border-slate-200/80 dark:border-white/[0.08] space-y-2">
                  <label className="block text-xs font-bold text-slate-800 dark:text-slate-200">
                    Horizon maximal de réservation
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      min={7}
                      max={365}
                      value={maxAdvanceDays}
                      onChange={(e) => setMaxAdvanceDays(Number(e.target.value))}
                      className="w-24 px-3 py-2 rounded-xl bg-slate-50 dark:bg-white/[0.04] border border-slate-200 dark:border-white/[0.1] text-xs font-bold"
                    />
                    <span className="text-xs text-slate-500">jours à l'avance</span>
                  </div>
                  <p className="text-[10px] text-slate-400">
                    Limite la prise de rendez-vous trop lointaine dans le futur.
                  </p>
                </div>
              </div>

              {/* Summary card */}
              <div className="p-5 rounded-2xl bg-blue-50/60 dark:bg-[#111D3D] border border-blue-100 dark:border-[#0076FF]/30 space-y-3">
                <div className="flex items-center gap-2 font-bold text-xs text-[#0076FF] dark:text-[#00D4FF]">
                  <ShieldCheck size={18} />
                  <span>Récapitulatif de votre moteur d'agenda</span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                  <div>
                    <span className="text-[10px] text-slate-400 block">Fuseau :</span>
                    <span className="font-semibold text-slate-800 dark:text-slate-200">{timezone}</span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400 block">Jours ouverts :</span>
                    <span className="font-semibold text-slate-800 dark:text-slate-200">
                      {Object.values(weeklySchedule).filter((s) => s.enabled).length} jours / 7
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400 block">Prestations :</span>
                    <span className="font-semibold text-slate-800 dark:text-slate-200">{services.length} services configurés</span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400 block">Central AI :</span>
                    <span className="font-semibold text-emerald-600 dark:text-emerald-400">Synchronisé</span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Wizard Footer */}
        <div className="flex items-center justify-between px-8 py-4 border-t border-slate-100 dark:border-white/[0.08] bg-slate-50/60 dark:bg-white/[0.02]">
          <button
            type="button"
            disabled={step === 1 || isSubmitting}
            onClick={() => setStep((s) => Math.max(1, s - 1))}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-slate-200 dark:border-white/[0.1] text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-white dark:hover:bg-white/[0.04] disabled:opacity-30 disabled:pointer-events-none"
          >
            <ArrowLeft size={14} />
            <span>Précédent</span>
          </button>

          {step < 4 ? (
            <button
              type="button"
              onClick={() => setStep((s) => s + 1)}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-bold shadow-xs transition-colors cursor-pointer"
            >
              <span>Suivant</span>
              <ArrowRight size={14} />
            </button>
          ) : (
            <button
              type="button"
              disabled={isSubmitting}
              onClick={handleSaveAll}
              className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-bold shadow-md shadow-emerald-500/20 transition-all cursor-pointer disabled:opacity-50"
            >
              <CheckCircle2 size={16} />
              <span>{isSubmitting ? "Enregistrement..." : "Valider et activer mon planning"}</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
