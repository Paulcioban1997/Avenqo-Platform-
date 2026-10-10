"use client";

import React, { useState, useEffect, useRef, useId } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import {
  Play,
  Pause,
  RotateCcw,
  ChevronRight,
  ChevronLeft,
  Volume2,
  VolumeX,
  Sparkles,
  CheckCircle2,
  ArrowRight,
  ShieldCheck,
  Layers,
  ShoppingBag,
  Wrench,
  HeartPulse,
  Utensils,
  Building,
  Hammer,
  Truck,
  GraduationCap,
  Compass,
  Briefcase,
  Calculator,
  Factory,
  Users,
  Eye,
  Info,
  ExternalLink,
  ChevronDown,
} from "lucide-react";
import { SECTOR_PROFILES, type SectorProfile, type DemoStep } from "@/lib/sectors/sector-profiles";
import { useLocale } from "@/lib/i18n/locale-context";

const ICON_MAP: Record<string, React.ElementType> = {
  ShoppingBag,
  Wrench,
  HeartPulse,
  Utensils,
  Sparkles,
  Building,
  Hammer,
  Truck,
  GraduationCap,
  Compass,
  Briefcase,
  Calculator,
  Factory,
  ShieldCheck,
  Users,
};

const MODULE_BADGES: Record<string, { labelFr: string; labelEn: string; color: string }> = {
  retail: { labelFr: "Retail IA", labelEn: "Retail AI", color: "from-blue-500 to-indigo-600" },
  crm: { labelFr: "CRM IA", labelEn: "CRM AI", color: "from-cyan-500 to-blue-600" },
  voice: { labelFr: "Voice IA", labelEn: "Voice AI", color: "from-purple-500 to-pink-600" },
  accounting: { labelFr: "Comptabilité IA", labelEn: "Accounting AI", color: "from-emerald-500 to-teal-600" },
  marketing: { labelFr: "Marketing IA", labelEn: "Marketing AI", color: "from-amber-500 to-orange-600" },
  ocr: { labelFr: "OCR IA", labelEn: "OCR AI", color: "from-rose-500 to-red-600" },
  central_ai: { labelFr: "IA Central", labelEn: "IA Central", color: "from-[#0076FF] to-[#7B2CBF]" },
};

export function AvenqoLiveExperience() {
  const { locale } = useLocale();
  const isEn = locale === "en";

  const [selectedSectorId, setSelectedSectorId] = useState<string>("retail_ecommerce");
  const [currentStepIndex, setCurrentStepIndex] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [isMuted, setIsMuted] = useState<boolean>(true);
  const [showSubtitles, setShowSubtitles] = useState<boolean>(true);
  const [reducedMotion, setReducedMotion] = useState<boolean>(false);
  const [selectedFilterModule, setSelectedFilterModule] = useState<string | "all">("all");
  const [customSectorText, setCustomSectorText] = useState<string>("");

  const activeSector: SectorProfile =
    SECTOR_PROFILES.find((s) => s.id === selectedSectorId) || SECTOR_PROFILES[0];
  const steps: DemoStep[] = activeSector.demoSteps || [];
  const currentStep: DemoStep | undefined = steps[currentStepIndex];

  // Auto-play timer
  useEffect(() => {
    let timer: NodeJS.Timeout | null = null;
    if (isPlaying) {
      timer = setTimeout(() => {
        if (currentStepIndex < steps.length - 1) {
          setCurrentStepIndex((prev) => prev + 1);
        } else {
          setIsPlaying(false);
        }
      }, 5000);
    }
    return () => {
      if (timer) clearTimeout(timer);
    };
  }, [isPlaying, currentStepIndex, steps.length]);

  // Reset step when changing sector
  const handleSelectSector = (id: string) => {
    setSelectedSectorId(id);
    setCurrentStepIndex(0);
    setIsPlaying(false);
  };

  const handleNext = () => {
    if (currentStepIndex < steps.length - 1) {
      setCurrentStepIndex((prev) => prev + 1);
    }
  };

  const handlePrev = () => {
    if (currentStepIndex > 0) {
      setCurrentStepIndex((prev) => prev - 1);
    }
  };

  const handleReplay = () => {
    setCurrentStepIndex(0);
    setIsPlaying(true);
  };

  // Keyboard controls
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowRight") handleNext();
    if (e.key === "ArrowLeft") handlePrev();
    if (e.key === " ") {
      e.preventDefault();
      setIsPlaying((prev) => !prev);
    }
  };

  const SectorIcon = ICON_MAP[activeSector.iconName] || Sparkles;
  const currentBadge = currentStep ? MODULE_BADGES[currentStep.activeModule] : undefined;

  // Filtered sectors list if module filter is active
  const displayedSectors = SECTOR_PROFILES.filter((s) => {
    if (selectedFilterModule === "all") return true;
    return s.recommendedModules.includes(selectedFilterModule as any);
  });

  return (
    <section
      id="demonstration"
      tabIndex={0}
      onKeyDown={handleKeyDown}
      className="relative mx-auto my-12 w-full max-w-7xl px-4 sm:px-6 lg:px-8 focus:outline-none"
      aria-label="Avenqo Live Experience"
    >
      {/* Anchor for both #demonstration and #live-experience */}
      <div id="live-experience" className="absolute -top-24 left-0" />

      {/* Cinematic Frame Container */}
      <div className="relative overflow-hidden rounded-3xl border border-white/10 bg-[#070E1E] text-white shadow-[0_20px_70px_rgba(0,118,255,0.18)]">
        {/* Subtle Ambient Background Gradients */}
        <div className="pointer-events-none absolute -left-40 -top-40 h-96 w-96 rounded-full bg-[#0076FF]/15 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-40 -right-40 h-96 w-96 rounded-full bg-[#7B2CBF]/15 blur-3xl" />

        {/* Top Bar: Disclaimer & Universal Controls */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 bg-[#0B132B]/70 px-6 py-3.5 backdrop-blur-md">
          <div className="flex items-center gap-2">
            <span className="flex h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-xs font-semibold tracking-wide text-cyan-300">
              AVENQO LIVE EXPERIENCE
            </span>
            <span className="rounded bg-white/10 px-2 py-0.5 text-[11px] font-medium text-slate-300">
              {isEn ? "Interactive Demo — Synthetic Data" : "Démonstration interactive — données fictives"}
            </span>
          </div>

          <div className="flex items-center gap-3 text-xs">
            {/* Audio Toggle */}
            <button
              type="button"
              onClick={() => setIsMuted(!isMuted)}
              aria-label={isMuted ? "Activer le son" : "Couper le son"}
              className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-2.5 py-1 text-slate-300 transition hover:bg-white/10 hover:text-white"
            >
              {isMuted ? <VolumeX size={14} /> : <Volume2 size={14} className="text-cyan-400" />}
              <span>{isMuted ? (isEn ? "Sound Off" : "Son coupé") : (isEn ? "Sound On" : "Son actif")}</span>
            </button>

            {/* Subtitles Toggle */}
            <button
              type="button"
              onClick={() => setShowSubtitles(!showSubtitles)}
              aria-label="Sous-titres"
              className={`rounded-lg border px-2.5 py-1 transition ${
                showSubtitles
                  ? "border-cyan-500/40 bg-cyan-500/10 text-cyan-300"
                  : "border-white/10 bg-white/5 text-slate-400 hover:text-white"
              }`}
            >
              CC {showSubtitles ? "✓" : ""}
            </button>

            {/* Reduced Motion Toggle */}
            <button
              type="button"
              onClick={() => setReducedMotion(!reducedMotion)}
              className={`rounded-lg border px-2 py-1 text-[11px] transition ${
                reducedMotion
                  ? "border-purple-500/40 bg-purple-500/10 text-purple-300"
                  : "border-white/10 bg-white/5 text-slate-400 hover:text-white"
              }`}
            >
              {isEn ? "Reduced Motion" : "Mouvement réduit"}
            </button>
          </div>
        </div>

        {/* Universal Selector Bar: Explore by Module or by Sector */}
        <div className="border-b border-white/10 bg-[#0B132B]/40 px-6 py-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            {/* Left: Sector Selector Dropdown & Pills */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium text-slate-400">
                {isEn ? "Industry Sector:" : "Secteur d'activité :"}
              </span>

              <div className="relative">
                <select
                  value={selectedSectorId}
                  onChange={(e) => handleSelectSector(e.target.value)}
                  className="cursor-pointer appearance-none rounded-xl border border-white/15 bg-[#111D3D] py-1.5 pl-3 pr-8 text-xs font-semibold text-white shadow-inner outline-none transition focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400"
                >
                  {displayedSectors.map((sector) => (
                    <option key={sector.id} value={sector.id} className="bg-[#0B132B] text-white">
                      {isEn ? sector.nameEn : sector.nameFr}
                    </option>
                  ))}
                </select>
                <ChevronDown size={14} className="pointer-events-none absolute right-2.5 top-2.5 text-slate-400" />
              </div>
            </div>

            {/* Right: Module Filter Pills (Explore by Module) */}
            <div className="flex flex-wrap items-center gap-1.5 text-xs">
              <span className="mr-1 text-[11px] text-slate-400">{isEn ? "Filter by Module:" : "Filtrer par module :"}</span>
              <button
                type="button"
                onClick={() => setSelectedFilterModule("all")}
                className={`rounded-lg px-2.5 py-1 text-[11px] font-medium transition ${
                  selectedFilterModule === "all"
                    ? "bg-[#0076FF] text-white"
                    : "bg-white/5 text-slate-300 hover:bg-white/10"
                }`}
              >
                {isEn ? "All" : "Tous"}
              </button>
              {(["retail", "crm", "voice", "accounting", "marketing", "ocr"] as const).map((modKey) => {
                const b = MODULE_BADGES[modKey];
                const active = selectedFilterModule === modKey;
                return (
                  <button
                    key={modKey}
                    type="button"
                    onClick={() => setSelectedFilterModule(modKey)}
                    className={`rounded-lg px-2.5 py-1 text-[11px] font-medium transition ${
                      active
                        ? "bg-gradient-to-r text-white shadow-sm " + b.color
                        : "bg-white/5 text-slate-300 hover:bg-white/10"
                    }`}
                  >
                    {isEn ? b.labelEn : b.labelFr}
                  </button>
                );
              })}
            </div>
          </div>

          {/* If "other_custom" is selected: allow typing custom sector */}
          {selectedSectorId === "other_custom" && (
            <div className="mt-3 flex items-center gap-2 pt-2">
              <input
                type="text"
                placeholder={isEn ? "Describe your specific industry (e.g. Solar panel installer)..." : "Décrivez votre activité spécifique (ex: Installateur solaire, Garderie)..."}
                value={customSectorText}
                onChange={(e) => setCustomSectorText(e.target.value)}
                className="w-full max-w-md rounded-xl border border-white/20 bg-white/5 px-3 py-1.5 text-xs text-white placeholder-slate-400 outline-none focus:border-cyan-400"
              />
              <span className="text-[11px] text-slate-400">
                {isEn ? "Avenqo adapts to your exact business model." : "Avenqo s'adapte à vos processus exacts."}
              </span>
            </div>
          )}
        </div>

        {/* Main Interactive Stage */}
        <div className="grid grid-cols-1 lg:grid-cols-12 min-h-[460px]">
          {/* Left Panel: Sector Overview & Modules Flow (5 cols) */}
          <div className="border-b border-white/10 p-6 lg:col-span-5 lg:border-b-0 lg:border-r">
            {/* Sector Header */}
            <div className="flex items-start gap-3">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-tr from-[#0076FF] to-[#7B2CBF] text-white shadow-lg shadow-blue-500/20">
                <SectorIcon size={24} />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">
                  {isEn ? activeSector.nameEn : activeSector.nameFr}
                </h3>
                <p className="mt-1 text-xs text-slate-300 leading-relaxed">
                  {isEn ? activeSector.descriptionEn : activeSector.descriptionFr}
                </p>
              </div>
            </div>

            {/* Recommended Business Modules */}
            <div className="mt-5 space-y-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                {isEn ? "Recommended Modules for this Sector" : "Modules recommandés pour ce secteur"}
              </span>
              <div className="flex flex-wrap gap-1.5">
                {activeSector.recommendedModules.map((mKey) => {
                  const b = MODULE_BADGES[mKey];
                  const isCurrentActive = currentStep?.activeModule === mKey;
                  return (
                    <span
                      key={mKey}
                      className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-semibold transition ${
                        isCurrentActive
                          ? "bg-gradient-to-r text-white ring-2 ring-cyan-300 shadow-md " + b.color
                          : "border border-white/15 bg-white/5 text-slate-200"
                      }`}
                    >
                      {isCurrentActive && <span className="h-1.5 w-1.5 rounded-full bg-white animate-ping" />}
                      {isEn ? b.labelEn : b.labelFr}
                    </span>
                  );
                })}
              </div>
            </div>

            {/* Concrete Real Use Cases */}
            <div className="mt-5 space-y-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                {isEn ? "Typical Business Outcomes" : "Bénéfices métiers concrets"}
              </span>
              <ul className="space-y-1.5 text-xs text-slate-300">
                {(isEn ? activeSector.useCasesEn : activeSector.useCasesFr).map((uc, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <CheckCircle2 size={14} className="mt-0.5 shrink-0 text-cyan-400" />
                    <span>{uc}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Regulatory & Compliance Notice */}
            <div className="mt-5 rounded-xl border border-white/10 bg-white/[0.03] p-3 text-[11px] text-slate-400">
              <div className="flex items-center gap-1.5 font-medium text-slate-300">
                <ShieldCheck size={13} className="text-emerald-400" />
                <span>{isEn ? "Compliance & Security" : "Conformité & Sécurité"}</span>
              </div>
              <p className="mt-1">
                {isEn ? activeSector.regulatoryConstraintsEn : activeSector.regulatoryConstraintsFr}
              </p>
            </div>
          </div>

          {/* Right Panel: Simulated Live Journey & Interactive Execution (7 cols) */}
          <div className="flex flex-col justify-between p-6 lg:col-span-7 bg-gradient-to-b from-[#0B132B]/50 to-[#070E1E]">
            {/* Step Stepper Header */}
            <div>
              <div className="flex items-center justify-between pb-3 border-b border-white/10">
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-cyan-500/20 text-xs font-bold text-cyan-300">
                    {currentStepIndex + 1}
                  </span>
                  <span className="text-xs font-semibold text-slate-300">
                    {isEn ? `Step ${currentStepIndex + 1} of ${steps.length}` : `Étape ${currentStepIndex + 1} sur ${steps.length}`}
                  </span>
                </div>

                {/* Module Badge for this step */}
                {currentBadge && (
                  <span
                    className={`rounded-full bg-gradient-to-r px-3 py-0.5 text-xs font-bold text-white shadow-sm ${currentBadge.color}`}
                  >
                    {isEn ? currentBadge.labelEn : currentBadge.labelFr}
                  </span>
                )}
              </div>

              {/* Step Card Visual Animation */}
              <AnimatePresence mode="wait">
                {currentStep && (
                  <motion.div
                    key={`${selectedSectorId}-${currentStepIndex}`}
                    initial={reducedMotion ? { opacity: 1 } : { opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={reducedMotion ? { opacity: 1 } : { opacity: 0, y: -12 }}
                    transition={{ duration: 0.35 }}
                    className="mt-5 space-y-4"
                  >
                    <div>
                      <h4 className="text-lg font-bold text-white">
                        {isEn ? currentStep.titleEn : currentStep.titleFr}
                      </h4>
                      <p className="mt-1 text-xs text-slate-300 leading-relaxed">
                        {isEn ? currentStep.descriptionEn : currentStep.descriptionFr}
                      </p>
                    </div>

                    {/* Step Execution Mockup Window */}
                    <div className="rounded-2xl border border-white/10 bg-[#0B132B]/80 p-4 shadow-inner">
                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                        {/* Input Box */}
                        <div className="space-y-1 rounded-xl border border-white/10 bg-white/[0.03] p-3 text-xs">
                          <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                            {isEn ? "Simulated Input" : "Entrée simulée"}
                          </span>
                          <p className="font-mono text-slate-200 text-xs break-words">
                            {currentStep.inputData}
                          </p>
                        </div>

                        {/* Output Box */}
                        <div className="space-y-1 rounded-xl border border-cyan-500/20 bg-cyan-950/20 p-3 text-xs">
                          <span className="text-[10px] font-semibold uppercase tracking-wider text-cyan-300">
                            {isEn ? "Verified AI Outcome" : "Résultat IA vérifié"}
                          </span>
                          <p className="font-medium text-cyan-100 text-xs break-words">
                            {currentStep.simulatedOutput}
                          </p>
                        </div>
                      </div>

                      {/* KPI Metric Pill */}
                      <div className="mt-3.5 flex items-center justify-between rounded-xl border border-emerald-500/20 bg-emerald-950/20 px-3.5 py-2">
                        <span className="text-xs text-emerald-300 font-medium">
                          {isEn ? "Impact & Performance Indicator" : "Indicateur d'impact vérifié"}
                        </span>
                        <span className="font-mono text-xs font-bold text-emerald-400">
                          {currentStep.visualMetric}
                        </span>
                      </div>
                    </div>

                    {/* Subtitle / Narration bar */}
                    {showSubtitles && (
                      <div className="rounded-xl border border-white/5 bg-white/[0.02] px-3.5 py-2 text-xs italic text-slate-400">
                        💬 &laquo; {isEn ? currentStep.descriptionEn : currentStep.descriptionFr} &raquo;
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Stepper Progress Bar & Controls */}
            <div className="mt-6 border-t border-white/10 pt-4">
              {/* Progress Steps Dots */}
              <div className="flex items-center gap-1.5 mb-4">
                {steps.map((s, idx) => (
                  <button
                    key={s.stepNumber}
                    type="button"
                    onClick={() => {
                      setCurrentStepIndex(idx);
                      setIsPlaying(false);
                    }}
                    className={`h-1.5 flex-1 rounded-full transition-all ${
                      idx === currentStepIndex
                        ? "bg-cyan-400 shadow-[0_0_8px_rgba(0,229,255,0.6)]"
                        : idx < currentStepIndex
                        ? "bg-blue-600"
                        : "bg-white/10"
                    }`}
                    aria-label={`Aller à l'étape ${idx + 1}`}
                  />
                ))}
              </div>

              {/* Player Navigation Buttons */}
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  {/* Play / Pause */}
                  <button
                    type="button"
                    onClick={() => setIsPlaying(!isPlaying)}
                    className="inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-[#0076FF] to-[#0052CC] px-4 py-2 text-xs font-semibold text-white shadow-md hover:brightness-110"
                  >
                    {isPlaying ? <Pause size={14} /> : <Play size={14} fill="currentColor" />}
                    <span>{isPlaying ? (isEn ? "Pause" : "Pause") : (isEn ? "Play" : "Lecture")}</span>
                  </button>

                  {/* Replay */}
                  <button
                    type="button"
                    onClick={handleReplay}
                    aria-label="Rejouer"
                    className="flex h-8 w-8 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-slate-300 transition hover:bg-white/10 hover:text-white"
                  >
                    <RotateCcw size={13} />
                  </button>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handlePrev}
                    disabled={currentStepIndex === 0}
                    className="flex items-center gap-1 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-medium text-slate-300 transition hover:bg-white/10 disabled:opacity-30"
                  >
                    <ChevronLeft size={14} />
                    <span>{isEn ? "Previous" : "Précédent"}</span>
                  </button>

                  <button
                    type="button"
                    onClick={handleNext}
                    disabled={currentStepIndex === steps.length - 1}
                    className="flex items-center gap-1 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-medium text-slate-300 transition hover:bg-white/10 disabled:opacity-30"
                  >
                    <span>{isEn ? "Next Step" : "Étape suivante"}</span>
                    <ChevronRight size={14} />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Phase 5 Conversion Bar: Post-Demo Actions */}
        <div className="border-t border-white/10 bg-[#0B132B]/80 px-6 py-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div className="space-y-0.5">
              <span className="text-xs font-semibold text-white">
                {isEn ? "Ready to launch your intelligent workspace?" : "Convaincu par la démonstration ?"}
              </span>
              <p className="text-[11px] text-slate-400">
                {isEn
                  ? "Explore all 6 official modules or create your space with 14 days guided onboarding."
                  : "Explorez nos 6 modules officiels ou créez votre espace avec 14 jours d'accompagnement guidé."}
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Link
                href="/#modules"
                className="rounded-xl border border-white/15 bg-white/5 px-3 py-2 text-xs font-medium text-slate-200 transition hover:bg-white/10"
              >
                {isEn ? "Explore Modules" : "Découvrir les modules"}
              </Link>
              <Link
                href="/#tarifs"
                className="rounded-xl border border-white/15 bg-white/5 px-3 py-2 text-xs font-medium text-slate-200 transition hover:bg-white/10"
              >
                {isEn ? "View Plans" : "Voir les forfaits"}
              </Link>
              <Link
                href="/contact"
                className="rounded-xl border border-cyan-500/30 bg-cyan-500/10 px-3 py-2 text-xs font-medium text-cyan-300 transition hover:bg-cyan-500/20"
              >
                {isEn ? "Request Custom Demo" : "Démonstration sur mesure"}
              </Link>
              <Link
                href="/signup"
                className="inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-[#0076FF] to-[#0052CC] px-4 py-2 text-xs font-bold text-white shadow-md transition hover:brightness-110"
              >
                <span>{isEn ? "Create Workspace" : "Créer votre espace"}</span>
                <ArrowRight size={13} />
              </Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
