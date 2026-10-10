"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Shield, Lock, CheckCircle2, AlertTriangle, KeyRound, PhoneCall, ArrowRight } from "lucide-react";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
import { AppShell } from "@/components/shell/app-shell";
import { FirstCustomerConcierge } from "@/components/workspace/first-customer-concierge";

interface Entitlements {
  plan_code: string;
  subscription_status: string;
  module_limit: number | null;
  active_modules: string[];
  modules: { key: string; display_name: string; state: string }[];
}

interface PinStatus {
  has_pin: boolean;
  phone_access_enabled: boolean;
  phone_number: string | null;
  is_locked: boolean;
  failed_attempts: number;
}

export default function OnboardingPage() {
  const { locale } = useLocale();
  const t = getAppTranslations(locale);
  const isFrench = locale.startsWith("fr");

  const [data, setData] = useState<Entitlements | null>(null);
  const [progress, setProgress] = useState<{ progress_percent: number; checklist: { key: string; done: boolean }[] } | null>(null);
  const [error, setError] = useState(false);

  // PIN Setup State
  const [pinStatus, setPinStatus] = useState<PinStatus | null>(null);
  const [pinStepOpen, setPinStepOpen] = useState(false);
  const [skippedPin, setSkippedPin] = useState(false);
  const [pin, setPin] = useState("");
  const [confirmPin, setConfirmPin] = useState("");
  const [phone, setPhone] = useState("");
  const [pinSubmitting, setPinSubmitting] = useState(false);
  const [pinError, setPinError] = useState<string | null>(null);
  const [pinSuccess, setPinSuccess] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(async () => {
      try {
        const [entRes, pinRes, onboardingRes] = await Promise.all([
          fetch("/api/v1/modules/entitlements", { signal: controller.signal, cache: "no-store" }),
          fetch("/api/v1/voice/auth/pin/status", { signal: controller.signal, cache: "no-store" }),
          fetch("/api/v1/onboarding", { signal: controller.signal, cache: "no-store" }),
        ]);

        if (entRes.ok) {
          const result = await entRes.json();
          if (!controller.signal.aborted) setData(result);
        } else {
          setError(true);
        }

        if (onboardingRes.ok) {
          const onboarding = await onboardingRes.json();
          if (!controller.signal.aborted) {
            setProgress({
              progress_percent: onboarding.progress_percent ?? 0,
              checklist: onboarding.checklist ?? [],
            });
          }
        }

        if (pinRes.ok) {
          const pinData: PinStatus = await pinRes.json();
          if (!controller.signal.aborted) {
            setPinStatus(pinData);
            if (!pinData.has_pin) {
              setPinStepOpen(true);
            }
          }
        }
      } catch {
        if (!controller.signal.aborted) setError(true);
      }
    });
    return () => controller.abort();
  }, []);

  const handleCreatePin = async (e: React.FormEvent) => {
    e.preventDefault();
    setPinError(null);

    if (!/^\d{6}$/.test(pin)) {
      setPinError(
        isFrench
          ? "Le NIP doit contenir exactement 6 chiffres."
          : "PIN must contain exactly 6 digits."
      );
      return;
    }

    if (pin !== confirmPin) {
      setPinError(
        isFrench
          ? "Les deux saisies de NIP ne correspondent pas."
          : "PIN and confirmation PIN do not match."
      );
      return;
    }

    const trivial = ["000000", "111111", "222222", "333333", "444444", "555555", "666666", "777777", "888888", "999999", "123456", "654321", "012345", "987654"];
    if (trivial.includes(pin)) {
      setPinError(
        isFrench
          ? "Veuillez choisir un NIP non trivial (évitez les suites ou répétitions)."
          : "Please choose a nontrivial PIN (avoid sequences or repeated digits)."
      );
      return;
    }

    setPinSubmitting(true);
    try {
      const payload: Record<string, string> = {
        pin,
        confirm_pin: confirmPin,
      };
      if (phone.trim()) {
        payload.phone_number = phone.trim();
      }

      const res = await fetch("/api/v1/voice/auth/pin", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || (isFrench ? "Erreur lors de la configuration du NIP" : "PIN configuration failed"));
      }

      setPinSuccess(true);
      setPinStepOpen(false);
      setPinStatus((prev) => prev ? { ...prev, has_pin: true, phone_access_enabled: true } : null);
    } catch (err: any) {
      setPinError(err.message || (isFrench ? "Une erreur est survenue." : "An error occurred."));
    } finally {
      setPinSubmitting(false);
    }
  };

  const handleSkipPin = () => {
    setSkippedPin(true);
    setPinStepOpen(false);
  };

  const voiceActive = data?.active_modules.includes("voice") ?? false;

  return (
    <AppShell>
      <main className="mx-auto w-full max-w-4xl space-y-6 px-5 py-8 sm:px-8">
        <header className="border-b border-slate-200 pb-5 dark:border-white/10">
          <h1 className="text-xl font-bold">{t.shell.workspace}</h1>
          {data && (
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
              {data.plan_code} · {data.subscription_status} · {data.module_limit ?? "∞"}
            </p>
          )}
          {progress && (
            <div className="mt-4">
              <div className="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-white/10">
                <div className="h-full bg-[#0076FF]" style={{ width: `${progress.progress_percent}%` }} />
              </div>
              <p className="mt-2 text-xs text-slate-500">{progress.progress_percent}% · {progress.checklist.filter((item) => item.done).length}/{progress.checklist.length}</p>
            </div>
          )}
        </header>

        {error && (
          <p role="alert" className="text-sm text-red-700 dark:text-red-300">
            {t.integrations.statusNeedsAttention}
          </p>
        )}

        <FirstCustomerConcierge />

        {/* STEP 2: Sécurisez votre assistant vocal Avenqo */}
        {pinStepOpen && !pinSuccess && (
          <div className="rounded-2xl border-2 border-[#0076FF]/40 bg-blue-50/40 p-6 shadow-md dark:border-blue-500/30 dark:bg-[#0B132B]/80">
            <div className="flex items-start gap-4">
              <div className="rounded-xl bg-[#0076FF] p-3 text-white shadow-sm">
                <Shield className="h-6 w-6" />
              </div>
              <div className="flex-1 space-y-2">
                <div className="inline-flex items-center gap-2 rounded-md bg-blue-100 px-2 py-0.5 text-xs font-semibold text-blue-800 dark:bg-blue-900/50 dark:text-blue-300">
                  <KeyRound className="h-3 w-3" />
                  {isFrench ? "Sécurité téléphonique P0" : "Voice Security P0"}
                </div>
                <h2 className="text-lg font-bold text-slate-900 dark:text-white">
                  {isFrench ? "Sécurisez votre assistant vocal Avenqo" : "Secure your Avenqo Voice Assistant"}
                </h2>
                <p className="text-sm text-slate-600 dark:text-slate-300">
                  {isFrench
                    ? "Créez votre NIP vocal personnel à 6 chiffres pour accéder aux fonctionnalités confidentielles de votre entreprise par téléphone."
                    : "Create your personal 6-digit voice PIN to access confidential company functions by phone."}
                </p>

                {pinError && (
                  <div className="flex items-center gap-2 rounded-lg bg-red-50 p-3 text-xs text-red-700 dark:bg-red-950/40 dark:text-red-300" role="alert">
                    <AlertTriangle className="h-4 w-4 shrink-0" />
                    <span>{pinError}</span>
                  </div>
                )}

                <form onSubmit={handleCreatePin} className="mt-4 space-y-4">
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <div>
                      <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                        {isFrench ? "NIP vocal personnel (6 chiffres)" : "Personal Voice PIN (6 digits)"}
                      </label>
                      <input
                        type="password"
                        inputMode="numeric"
                        pattern="[0-9]*"
                        maxLength={6}
                        placeholder="••••••"
                        value={pin}
                        onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
                        required
                        className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-center text-lg font-mono tracking-widest text-slate-900 shadow-xs focus:border-[#0076FF] focus:outline-hidden dark:border-white/20 dark:bg-slate-900 dark:text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                        {isFrench ? "Confirmez votre NIP" : "Confirm your PIN"}
                      </label>
                      <input
                        type="password"
                        inputMode="numeric"
                        pattern="[0-9]*"
                        maxLength={6}
                        placeholder="••••••"
                        value={confirmPin}
                        onChange={(e) => setConfirmPin(e.target.value.replace(/\D/g, ""))}
                        required
                        className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-center text-lg font-mono tracking-widest text-slate-900 shadow-xs focus:border-[#0076FF] focus:outline-hidden dark:border-white/20 dark:bg-slate-900 dark:text-white"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                      {isFrench ? "Votre numéro de téléphone (au format +1...)" : "Your telephone number (+1...)"}
                    </label>
                    <input
                      type="tel"
                      placeholder="+15145550199"
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm text-slate-900 shadow-xs focus:border-[#0076FF] focus:outline-hidden dark:border-white/20 dark:bg-slate-900 dark:text-white"
                    />
                    <p className="mt-1 text-[11px] text-slate-500">
                      {isFrench
                        ? "Utilisé pour reconnaître automatiquement votre appel avant l'authentification par clavier DTMF."
                        : "Used to automatically recognize your incoming call prior to DTMF keypad authentication."}
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center gap-3 pt-2">
                    <button
                      type="submit"
                      disabled={pinSubmitting || pin.length !== 6 || confirmPin.length !== 6}
                      className="inline-flex items-center gap-2 rounded-xl bg-[#0076FF] px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-600 disabled:opacity-50"
                    >
                      <Lock className="h-4 w-4" />
                      {pinSubmitting
                        ? (isFrench ? "Sécurisation..." : "Securing...")
                        : (isFrench ? "Créer mon NIP" : "Create my PIN")}
                    </button>
                    <button
                      type="button"
                      onClick={handleSkipPin}
                      className="inline-flex items-center rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-white/20 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
                    >
                      {isFrench ? "Configurer plus tard" : "Set up later"}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        )}

        {/* Feedback if PIN successfully created */}
        {pinSuccess && (
          <div className="flex items-center gap-3 rounded-2xl border border-emerald-300 bg-emerald-50/60 p-4 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300">
            <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-600" />
            <div>
              <h3 className="text-sm font-bold">
                {isFrench ? "NIP vocal personnel configuré avec succès" : "Voice PIN configured successfully"}
              </h3>
              <p className="text-xs text-emerald-700 dark:text-emerald-400">
                {isFrench
                  ? "Vous pourrez accéder aux outils confidentiels (Retail, Accounting, CRM) lors de vos appels en saisissant ce NIP."
                  : "You can now access confidential tools (Retail, Accounting, CRM) during calls by entering this PIN."}
              </p>
            </div>
          </div>
        )}

        {/* Warning banner if skipped */}
        {skippedPin && !pinStatus?.has_pin && (
          <div className="flex items-center gap-3 rounded-2xl border border-amber-300 bg-amber-50/60 p-4 text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
            <AlertTriangle className="h-5 w-5 shrink-0 text-amber-600" />
            <div>
              <h3 className="text-sm font-bold">
                {isFrench ? "Fonctions privées verrouillées sur Voice AI" : "Private functions locked on Voice AI"}
              </h3>
              <p className="text-xs text-amber-700 dark:text-amber-400">
                {isFrench
                  ? "Tant que votre NIP vocal n'est pas configuré, les outils Retail, Accounting et CRM interne resteront inaccessibles par téléphone. Vous pourrez le configurer à tout moment dans vos Paramètres."
                  : "Until your voice PIN is configured, Retail, Accounting, and internal CRM tools remain inaccessible over the phone. You can set it up anytime in Settings."}
              </p>
            </div>
          </div>
        )}

        {!data && !error && <p role="status" className="text-sm">{t.common.retry}</p>}

        {data && (
          <>
            <section className="space-y-3">
              <h2 className="text-sm font-semibold">{t.navigation.agentsAi}</h2>
              <ul className="divide-y divide-slate-200 dark:divide-white/10">
                {data.modules.map((module) => (
                  <li key={module.key} className="flex justify-between gap-4 py-3 text-sm">
                    <span>{module.display_name}</span>
                    <span className="text-slate-500">{module.state}</span>
                  </li>
                ))}
              </ul>
            </section>
            <nav className="flex flex-wrap gap-4 border-t border-slate-200 pt-5 dark:border-white/10">
              <Link
                className="inline-flex items-center gap-2 rounded-xl bg-[#0076FF] px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-600"
                href={voiceActive ? "/voice" : "/dashboard"}
              >
                {voiceActive ? t.navigation.voiceAi : t.navigation.dashboard}
                <ArrowRight className="h-4 w-4" />
              </Link>
              <Link className="inline-flex items-center px-2 py-2 text-sm underline" href="/settings">
                {t.navigation.settings}
              </Link>
            </nav>
          </>
        )}
      </main>
    </AppShell>
  );
}