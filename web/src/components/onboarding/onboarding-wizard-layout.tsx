"use client";

import React from "react";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import {
  Building2,
  Layers,
  Palette,
  Eye,
  FileText,
  CreditCard,
  Lock,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useLocale } from "@/lib/i18n/locale-context";
import { getOnboardingCopy } from "@/lib/i18n/onboarding-multistep-copy";

export interface OnboardingWizardLayoutProps {
  currentStepIndex: number; // 1 to 8
  title: string;
  subtitle: string;
  onPrev?: () => void;
  onNext?: () => void;
  nextLabel?: string;
  isNextDisabled?: boolean;
  isSubmitting?: boolean;
  saveStatus?: "saving" | "saved" | "idle";
  children: React.ReactNode;
}

const STEPS = [
  { index: 1, key: "company", path: "/onboarding/company", icon: Building2 },
  { index: 2, key: "modules", path: "/onboarding/modules", icon: Layers },
  { index: 3, key: "design", path: "/onboarding/design", icon: Palette },
  { index: 4, key: "preview", path: "/onboarding/preview", icon: Eye },
  { index: 5, key: "contracts", path: "/onboarding/contracts", icon: FileText },
  { index: 6, key: "subscription", path: "/onboarding/subscription", icon: CreditCard },
  { index: 7, key: "checkout", path: "/onboarding/checkout", icon: Lock },
  { index: 8, key: "complete", path: "/onboarding/complete", icon: CheckCircle2 },
];

export function OnboardingWizardLayout({
  currentStepIndex,
  title,
  subtitle,
  onPrev,
  onNext,
  nextLabel,
  isNextDisabled = false,
  isSubmitting = false,
  saveStatus = "idle",
  children,
}: OnboardingWizardLayoutProps) {
  const router = useRouter();
  const { locale } = useLocale();
  const copy = getOnboardingCopy(locale);

  const prevStep = STEPS.find((s) => s.index === currentStepIndex - 1);
  const nextStep = STEPS.find((s) => s.index === currentStepIndex + 1);

  const handlePrev = () => {
    if (onPrev) {
      onPrev();
    } else if (prevStep) {
      router.push(prevStep.path);
    }
  };

  const handleNext = () => {
    if (onNext) {
      onNext();
    } else if (nextStep) {
      router.push(nextStep.path);
    }
  };

  const progressPercent = Math.round((currentStepIndex / 8) * 100);

  return (
    <div className="min-h-screen bg-[#060B13] text-[#F4F7FB] flex flex-col selection:bg-[#0076FF] selection:text-white">
      {/* Top Navigation Bar */}
      <header className="sticky top-0 z-40 bg-[#0B132B]/90 backdrop-blur-md border-b border-white/[0.08] px-4 sm:px-8 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href="/onboarding" className="flex items-center gap-2.5 group">
            <Image
              src="/brand/avenqo-icon.png"
              alt="Avenqo"
              width={34}
              height={34}
              className="rounded-xl object-contain shadow-xs shadow-blue-500/20 group-hover:scale-105 transition-transform"
            />
            <div className="flex flex-col">
              <span className="font-extrabold tracking-tight text-white text-base leading-none">
                AVENQO
              </span>
              <span className="text-[10px] font-semibold text-blue-400 tracking-wider uppercase mt-0.5">
                Onboarding Entreprise
              </span>
            </div>
          </Link>
        </div>

        {/* Security badge and save indicator */}
        <div className="flex items-center gap-4">
          {saveStatus === "saving" && (
            <span className="text-xs text-slate-400 animate-pulse flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-blue-500" />
              {copy.navigation.saving}
            </span>
          )}
          {saveStatus === "saved" && (
            <span className="text-xs text-emerald-400 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              {copy.navigation.saved}
            </span>
          )}
          <div className="hidden sm:flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/[0.04] border border-white/[0.08] text-[11px] font-medium text-slate-300">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span>Multi-Tenant Isolé & Sécurisé</span>
          </div>
        </div>
      </header>

      {/* Stepper Progress Header */}
      <div className="bg-[#0B132B]/60 border-b border-white/[0.06] px-4 sm:px-8 py-4">
        <div className="max-w-6xl mx-auto space-y-3">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span className="font-semibold text-white">
              {copy.navigation.stepOf
                .replace("{current}", String(currentStepIndex))
                .replace("{total}", "8")}
            </span>
            <span className="font-mono text-blue-400 font-bold">{progressPercent}%</span>
          </div>

          {/* Progress bar line */}
          <div className="w-full bg-slate-800/80 rounded-full h-2 overflow-hidden">
            <div
              className="bg-gradient-to-r from-blue-600 via-[#0076FF] to-cyan-400 h-2 rounded-full transition-all duration-300 ease-out"
              style={{ width: `${progressPercent}%` }}
            />
          </div>

          {/* Responsive Stepper Pills */}
          <nav aria-label="Progression de l'onboarding" className="pt-2 overflow-x-auto scrollbar-none">
            <ol className="flex items-center justify-between min-w-[700px] gap-2">
              {STEPS.map((step) => {
                const Icon = step.icon;
                const isCurrent = step.index === currentStepIndex;
                const isPassed = step.index < currentStepIndex;
                const stepTitle = copy.steps[step.key as keyof typeof copy.steps] || step.key;

                return (
                  <li key={step.index} className="flex-1">
                    <Link
                      href={step.path}
                      className={`flex items-center gap-2 p-2 rounded-xl transition-all ${
                        isCurrent
                          ? "bg-[#0076FF]/20 border border-[#0076FF] text-white shadow-sm shadow-blue-500/20"
                          : isPassed
                          ? "bg-white/[0.03] border border-white/[0.06] text-slate-300 hover:bg-white/[0.06]"
                          : "opacity-50 text-slate-500 cursor-not-allowed pointer-events-none"
                      }`}
                      aria-current={isCurrent ? "step" : undefined}
                    >
                      <div
                        className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 text-xs font-bold ${
                          isCurrent
                            ? "bg-[#0076FF] text-white"
                            : isPassed
                            ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                            : "bg-slate-800 text-slate-400"
                        }`}
                      >
                        {isPassed ? <CheckCircle2 className="w-4 h-4" /> : <Icon className="w-4 h-4" />}
                      </div>
                      <div className="truncate">
                        <div className="text-[10px] uppercase font-semibold text-slate-400 leading-none">
                          Étape {step.index}
                        </div>
                        <div className="text-xs font-medium truncate mt-0.5">{stepTitle}</div>
                      </div>
                    </Link>
                  </li>
                );
              })}
            </ol>
          </nav>
        </div>
      </div>

      {/* Main Content Area */}
      <main className="flex-1 max-w-5xl w-full mx-auto px-4 sm:px-6 py-8">
        <div className="mb-8">
          <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">{title}</h1>
          <p className="mt-2 text-sm text-slate-400 max-w-3xl leading-relaxed">{subtitle}</p>
        </div>

        {children}
      </main>

      {/* Footer Navigation Buttons */}
      <footer className="sticky bottom-0 z-30 bg-[#0B132B]/95 backdrop-blur-md border-t border-white/[0.08] px-4 sm:px-8 py-4">
        <div className="max-w-5xl mx-auto flex items-center justify-between gap-4">
          {currentStepIndex > 1 ? (
            <button
              type="button"
              onClick={handlePrev}
              disabled={isSubmitting}
              className="px-5 py-2.5 rounded-xl border border-white/10 bg-white/[0.04] hover:bg-white/[0.08] text-sm font-semibold text-slate-300 transition-colors flex items-center gap-2 cursor-pointer disabled:opacity-50"
            >
              <ChevronLeft className="w-4 h-4" />
              <span>{copy.navigation.back}</span>
            </button>
          ) : (
            <div />
          )}

          {currentStepIndex < 8 && (
            <button
              type="button"
              onClick={handleNext}
              disabled={isNextDisabled || isSubmitting}
              className="px-6 py-2.5 rounded-xl bg-[#0076FF] hover:bg-blue-600 active:scale-[0.98] text-sm font-bold text-white shadow-md shadow-blue-500/25 transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <span>{nextLabel || copy.navigation.continue}</span>
              <ChevronRight className="w-4 h-4" />
            </button>
          )}

          {currentStepIndex === 8 && (
            <button
              type="button"
              onClick={handleNext}
              className="px-8 py-3 rounded-xl bg-gradient-to-r from-blue-600 via-[#0076FF] to-cyan-500 hover:opacity-95 text-sm font-extrabold text-white shadow-lg shadow-blue-500/30 transition-all flex items-center gap-2 cursor-pointer"
            >
              <Sparkles className="w-4 h-4" />
              <span>{copy.navigation.goToDashboard}</span>
            </button>
          )}
        </div>
      </footer>
    </div>
  );
}

