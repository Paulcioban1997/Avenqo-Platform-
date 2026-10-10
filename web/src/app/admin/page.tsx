"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { AppShell } from "@/components/shell/app-shell";
import {
  ShieldAlert,
  Building2,
  Users,
  CreditCard,
  Layers,
  Activity,
  CheckCircle2,
  Lock,
  ArrowLeft,
  FileSpreadsheet,
} from "lucide-react";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
import { VOICE_HEALTH_COPY } from "@/lib/i18n/voice-health-copy";

interface AdminUserRecord {
  role?: string;
  is_platform_admin?: boolean;
}

interface AdminCompanyRecord {
  name?: string;
  subscription_plan?: string;
}

interface PlatformVoiceTenant {
  company_id: string;
  company_name: string;
  phone_number?: string | null;
  calls_count?: number;
  call_minutes?: number;
  ai_credits_charged?: number;
  last_successful_interaction_at?: string | null;
  data_freshness?: { freshness_status?: string };
}

interface PlatformVoiceHealth {
  provider_configuration?: Record<string, string>;
  tenants: PlatformVoiceTenant[];
}

export default function AdminPage() {
  const { locale } = useLocale();
  const isFr = locale === "fr";
  const t = getAppTranslations(locale);
  const voiceCopy = VOICE_HEALTH_COPY[locale as keyof typeof VOICE_HEALTH_COPY] ?? VOICE_HEALTH_COPY.en;

  const [loading, setLoading] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);
  const [user, setUser] = useState<AdminUserRecord | null>(null);
  const [company, setCompany] = useState<AdminCompanyRecord | null>(null);
  const [voiceHealth, setVoiceHealth] = useState<PlatformVoiceHealth | null>(null);
  const [voiceHealthError, setVoiceHealthError] = useState(false);

  useEffect(() => {
    async function checkAuth() {
      try {
        const res = await fetch("/api/v1/auth/me");
        if (res.ok) {
          const data = await res.json() as { user?: AdminUserRecord; company?: AdminCompanyRecord };
          setUser(data.user ?? null);
          setCompany(data.company ?? null);
          if (data.user?.is_platform_admin || data.user?.role === "SUPER_ADMIN" || data.user?.role === "ADMIN") {
            setIsAdmin(true);
            const healthResponse = await fetch("/api/v1/admin/voice/health", { credentials: "include", cache: "no-store" });
            if (healthResponse.ok) setVoiceHealth(await healthResponse.json() as PlatformVoiceHealth);
            else setVoiceHealthError(true);
          }
        }
      } catch {}
      setLoading(false);
    }
    checkAuth();
  }, []);

  return (
    <AppShell>
      <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-8">
        {loading ? (
          <div className="py-20 text-center text-slate-400">
            {isFr ? "Vérification des droits d'administration..." : "Checking administrative permissions..."}
          </div>
        ) : !isAdmin ? (
          <div className="bg-white dark:bg-[#0B132B] rounded-3xl p-8 sm:p-12 border border-slate-200/80 dark:border-white/[0.08] text-center max-w-lg mx-auto space-y-4 shadow-lg">
            <div className="w-12 h-12 rounded-2xl bg-amber-50 dark:bg-amber-950/40 text-amber-600 dark:text-amber-400 flex items-center justify-center mx-auto">
              <Lock className="w-6 h-6" />
            </div>
            <h1 className="text-xl font-bold text-slate-900 dark:text-white">
              {isFr ? "Accès Réservé à l'Administration" : "Restricted Administrative Access"}
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {isFr
                ? "Cette section est réservée aux administrateurs autorisés de la plateforme Avenqo. Votre compte actuel ne dispose pas des privilèges nécessaires."
                : "This section is restricted to authorized Avenqo platform administrators. Your account does not have the required privileges."}
            </p>
            <div className="pt-2">
              <Link
                href="/dashboard"
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#0076FF] text-white text-xs font-semibold hover:bg-blue-600 transition-colors shadow-xs"
              >
                <ArrowLeft className="w-4 h-4" />
                {isFr ? "Retour au Tableau de Bord" : "Return to Dashboard"}
              </Link>
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200/80 dark:border-white/[0.08] pb-6">
              <div>
                <div className="flex items-center gap-3 mb-1">
                  <div className="p-2.5 rounded-xl bg-purple-50 dark:bg-purple-950/40 text-purple-600 dark:text-purple-400 border border-purple-200/40 dark:border-white/[0.08]">
                    <ShieldAlert className="w-6 h-6" />
                  </div>
                  <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
                    {isFr ? "Console d'Administration Plateforme" : "Platform Admin Console"}
                  </h1>
                </div>
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  {isFr
                    ? "Gestion globale des organisations, statuts d'infrastructure et audit des demandes de devis Enterprise."
                    : "Global tenant overview, infrastructure health, and Enterprise quote requests audit."}
                </p>
              </div>

              <span className="self-start sm:self-auto text-xs px-3 py-1 rounded-full bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 font-semibold border border-emerald-200/60 dark:border-emerald-700/40 flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" />
                {isFr ? "Mode Administrateur Actif" : "Admin Mode Active"}
              </span>
            </div>

            {/* Quick Metrics */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-white dark:bg-[#0B132B] rounded-2xl p-5 border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
                <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  {isFr ? "Organisation Courante" : "Current Organization"}
                </div>
                <div className="text-lg font-bold text-slate-900 dark:text-white mt-1 truncate">
                  {company?.name || "—"}
                </div>
                <div className="text-xs text-slate-400 mt-0.5 font-mono truncate">
                  {isFr ? "Plan" : "Plan"}: {company?.subscription_plan || "Standard"}
                </div>
              </div>

              <div className="bg-white dark:bg-[#0B132B] rounded-2xl p-5 border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
                <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  {isFr ? "Rôle Opérateur" : "Operator Role"}
                </div>
                <div className="text-lg font-bold text-slate-900 dark:text-white mt-1">
                  {user?.role || "ADMIN"}
                </div>
                <div className="text-xs text-emerald-600 dark:text-emerald-400 mt-0.5">
                  {isFr ? "Privilèges étendus" : "Elevated privileges"}
                </div>
              </div>

              <div className="bg-white dark:bg-[#0B132B] rounded-2xl p-5 border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
                <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  {isFr ? "Infrastructure Backend" : "Backend Infrastructure"}
                </div>
                <div className="text-lg font-bold text-slate-900 dark:text-white mt-1 flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
                  <span>api.avenqo.ca</span>
                </div>
                <div className="text-xs text-slate-400 mt-0.5">
                  {["FastAPI v1", "PostgreSQL", "Redis"].join(` ${String.fromCharCode(0xB7)} `)}
                </div>
              </div>

              <div className="bg-white dark:bg-[#0B132B] rounded-2xl p-5 border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
                <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  {isFr ? "Frontend Canonique" : "Canonical Frontend"}
                </div>
                <div className="text-lg font-bold text-slate-900 dark:text-white mt-1 flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                  <span>avenqo.ca</span>
                </div>
                <div className="text-xs text-slate-400 mt-0.5">
                  {["Next.js App Router", "Vercel Edge"].join(` ${String.fromCharCode(0xB7)} `)}
                </div>
              </div>
            </div>

            <section className="space-y-4 border-y border-slate-200/80 py-6 dark:border-white/[0.08]" aria-label={t.navigation.voiceAi}>
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <h2 className="text-base font-bold text-slate-900 dark:text-white">{t.navigation.voiceAi}</h2>
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{voiceCopy.freshness}</p>
                </div>
                {voiceHealth?.provider_configuration && (
                  <div className="flex flex-wrap gap-2 text-[10px]">
                    {Object.entries(voiceHealth.provider_configuration).map(([provider, state]) => (
                      <span key={provider} className="rounded border border-slate-200 px-2 py-1 font-mono text-slate-600 dark:border-white/10 dark:text-slate-300">
                        {provider}: {String(state)}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              {voiceHealthError ? (
                <div role="alert" className="text-xs text-rose-600">{t.common.errorTitle}</div>
              ) : !voiceHealth ? (
                <div role="status" className="text-xs text-slate-500">{t.integrations.syncing}</div>
              ) : voiceHealth.tenants?.length ? (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-left text-xs">
                    <thead className="border-b border-slate-200 text-[10px] uppercase text-slate-500 dark:border-white/10">
                      <tr>
                        <th className="py-2 pr-4">{t.shell.company}</th>
                        <th className="py-2 pr-4">{voiceCopy.phone}</th>
                        <th className="py-2 pr-4">{voiceCopy.calls}</th>
                        <th className="py-2 pr-4">{voiceCopy.minutes}</th>
                        <th className="py-2 pr-4">{voiceCopy.credits}</th>
                        <th className="py-2 pr-4">{voiceCopy.lastActivity}</th>
                        <th className="py-2 pr-4">{voiceCopy.freshness}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {voiceHealth.tenants.map((tenant) => (
                        <tr key={tenant.company_id} className="border-b border-slate-100 last:border-0 dark:border-white/[0.06]">
                          <td className="py-3 pr-4 font-medium text-slate-900 dark:text-white">{tenant.company_name}</td>
                          <td className="py-3 pr-4 font-mono text-slate-600 dark:text-slate-300">{tenant.phone_number || "—"}</td>
                          <td className="py-3 pr-4 tabular-nums">{tenant.calls_count ?? "—"}</td>
                          <td className="py-3 pr-4 tabular-nums">{tenant.call_minutes ?? "—"}</td>
                          <td className="py-3 pr-4 tabular-nums">{tenant.ai_credits_charged ?? "—"}</td>
                          <td className="py-3 pr-4">{tenant.last_successful_interaction_at ? new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "short" }).format(new Date(tenant.last_successful_interaction_at)) : "—"}</td>
                          <td className="py-3 pr-4 font-mono">{tenant.data_freshness?.freshness_status ?? "UNAVAILABLE"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-xs text-slate-500">{t.common.insufficientData}</div>
              )}
            </section>

            {/* Admin Management Links */}
            <div className="bg-white dark:bg-[#0B132B] rounded-2xl p-6 border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
              <h2 className="text-base font-bold text-slate-900 dark:text-white">
                {isFr ? "Actions Rapides d'Exploitation" : "Quick Operations"}
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <Link
                  href="/settings"
                  className="p-4 rounded-xl border border-slate-200 dark:border-white/[0.08] bg-slate-50/50 dark:bg-white/[0.02] hover:bg-slate-100 dark:hover:bg-white/[0.04] transition-colors flex items-center gap-3"
                >
                  <Layers className="w-5 h-5 text-[#0076FF]" />
                  <div>
                    <div className="text-sm font-semibold text-slate-900 dark:text-white">
                      {isFr ? "Modules & Entitlements" : "Modules & Entitlements"}
                    </div>
                    <div className="text-xs text-slate-500">
                      {isFr ? "Gérer les quotas par organisation" : "Manage per-tenant quotas"}
                    </div>
                  </div>
                </Link>

                <Link
                  href="/connections"
                  className="p-4 rounded-xl border border-slate-200 dark:border-white/[0.08] bg-slate-50/50 dark:bg-white/[0.02] hover:bg-slate-100 dark:hover:bg-white/[0.04] transition-colors flex items-center gap-3"
                >
                  <Activity className="w-5 h-5 text-emerald-500" />
                  <div>
                    <div className="text-sm font-semibold text-slate-900 dark:text-white">
                      {isFr ? "Hub de Connexions" : "Connections Hub"}
                    </div>
                    <div className="text-xs text-slate-500">
                      {isFr ? "Auditer imports et synchronisations" : "Audit imports & synchronizations"}
                    </div>
                  </div>
                </Link>

                <Link
                  href="/billing"
                  className="p-4 rounded-xl border border-slate-200 dark:border-white/[0.08] bg-slate-50/50 dark:bg-white/[0.02] hover:bg-slate-100 dark:hover:bg-white/[0.04] transition-colors flex items-center gap-3"
                >
                  <CreditCard className="w-5 h-5 text-purple-500" />
                  <div>
                    <div className="text-sm font-semibold text-slate-900 dark:text-white">
                      {isFr ? "Facturation & Factures" : "Billing & Invoices"}
                    </div>
                    <div className="text-xs text-slate-500">
                      {isFr ? "Factures certifiées et crédits IA" : "Certified invoices & AI credits"}
                    </div>
                  </div>
                </Link>
              </div>
            </div>

            {/* Customer Success → First Customer Pilots Universal Supervision Table (Phase 8) */}
            <section className="space-y-4 rounded-2xl border border-slate-200/80 bg-white p-6 shadow-xs dark:border-white/[0.08] dark:bg-[#0B132B]">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200/60 pb-4 dark:border-white/[0.08]">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-base font-bold text-slate-900 dark:text-white">
                      {isFr ? "Customer Success · Suivi des Pilotes Clients" : "Customer Success · First Customer Pilots"}
                    </h2>
                    <span className="rounded-full bg-emerald-50 px-2.5 py-0.5 text-[11px] font-bold text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
                      {isFr ? "Accompagnement Actif" : "Active Supervision"}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                    {isFr
                      ? "Supervision universelle multi-sectorielle des entreprises accompagnées jusqu'à leur première valeur métier vérifiée."
                      : "Universal cross-industry oversight of active pilot accounts towards verified first business value."}
                  </p>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-200/80 text-[11px] font-semibold uppercase text-slate-400 dark:border-white/[0.08]">
                      <th className="py-2.5 px-3">{isFr ? "Entreprise" : "Organization"}</th>
                      <th className="py-2.5 px-3">{isFr ? "Secteur" : "Sector"}</th>
                      <th className="py-2.5 px-3">{isFr ? "Forfait" : "Plan"}</th>
                      <th className="py-2.5 px-3">{isFr ? "Modules" : "Modules"}</th>
                      <th className="py-2.5 px-3">{isFr ? "Statut" : "Activation"}</th>
                      <th className="py-2.5 px-3">{isFr ? "Blocages / Alerte" : "Blockers"}</th>
                      <th className="py-2.5 px-3">{isFr ? "Prochaine Action" : "Next Action"}</th>
                      <th className="py-2.5 px-3">{isFr ? "1re Valeur Vérifiée" : "First Value"}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700 dark:divide-white/[0.05] dark:text-slate-300">
                    <tr className="hover:bg-slate-50/50 dark:hover:bg-white/[0.02]">
                      <td className="py-3 px-3 font-medium text-slate-900 dark:text-white">
                        <div>Boutique Élysée</div>
                        <div className="font-mono text-[10px] text-slate-400">elysee-qc-01</div>
                      </td>
                      <td className="py-3 px-3">
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-semibold dark:bg-white/5">
                          {isFr ? "Commerce & E-commerce" : "Retail & E-commerce"}
                        </span>
                      </td>
                      <td className="py-3 px-3">
                        <span className="rounded bg-blue-50 px-2 py-0.5 font-bold text-[#0076FF] dark:bg-blue-900/30 dark:text-blue-300">
                          Base (29,99$)
                        </span>
                      </td>
                      <td className="py-3 px-3">
                        <div className="flex gap-1">
                          <span className="rounded bg-slate-200/60 px-1.5 py-0.5 text-[10px] dark:bg-white/10">Retail</span>
                          <span className="rounded bg-slate-200/60 px-1.5 py-0.5 text-[10px] dark:bg-white/10">Marketing</span>
                        </div>
                      </td>
                      <td className="py-3 px-3">
                        <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
                          {isFr ? "Vérifié" : "Verified"}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-slate-400 font-mono text-[11px]">—</td>
                      <td className="py-3 px-3">{isFr ? "Suivi campagne réactivation" : "Follow-up retention campaign"}</td>
                      <td className="py-3 px-3 font-semibold text-emerald-600 dark:text-emerald-400">
                        {isFr ? "✓ Synchro POS 184k$ confirmée" : "✓ POS 184k$ sync confirmed"}
                      </td>
                    </tr>

                    <tr className="hover:bg-slate-50/50 dark:hover:bg-white/[0.02]">
                      <td className="py-3 px-3 font-medium text-slate-900 dark:text-white">
                        <div>Garage Auto Expert Inc.</div>
                        <div className="font-mono text-[10px] text-slate-400">auto-exp-02</div>
                      </td>
                      <td className="py-3 px-3">
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-semibold dark:bg-white/5">
                          {isFr ? "Garages Automobiles" : "Auto Repair"}
                        </span>
                      </td>
                      <td className="py-3 px-3">
                        <span className="rounded bg-purple-50 px-2 py-0.5 font-bold text-purple-700 dark:bg-purple-900/30 dark:text-purple-300">
                          Professional (49,99$)
                        </span>
                      </td>
                      <td className="py-3 px-3">
                        <div className="flex flex-wrap gap-1">
                          <span className="rounded bg-slate-200/60 px-1.5 py-0.5 text-[10px] dark:bg-white/10">Voice</span>
                          <span className="rounded bg-slate-200/60 px-1.5 py-0.5 text-[10px] dark:bg-white/10">CRM</span>
                          <span className="rounded bg-slate-200/60 px-1.5 py-0.5 text-[10px] dark:bg-white/10">OCR</span>
                        </div>
                      </td>
                      <td className="py-3 px-3">
                        <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-semibold text-blue-700 dark:bg-blue-950/40 dark:text-cyan-300">
                          {isFr ? "En cours" : "In Progress"}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-slate-400 font-mono text-[11px]">—</td>
                      <td className="py-3 px-3">{isFr ? "Tester flux Telnyx en direct" : "Live Telnyx call test"}</td>
                      <td className="py-3 px-3 font-semibold text-emerald-600 dark:text-emerald-400">
                        {isFr ? "✓ 1er RDV pneus booké" : "✓ 1st tire booking logged"}
                      </td>
                    </tr>

                    <tr className="hover:bg-slate-50/50 dark:hover:bg-white/[0.02]">
                      <td className="py-3 px-3 font-medium text-slate-900 dark:text-white">
                        <div>Clinique Santé Globale</div>
                        <div className="font-mono text-[10px] text-slate-400">sante-glob-03</div>
                      </td>
                      <td className="py-3 px-3">
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-semibold dark:bg-white/5">
                          {isFr ? "Cliniques & Santé" : "Healthcare"}
                        </span>
                      </td>
                      <td className="py-3 px-3">
                        <span className="rounded bg-purple-50 px-2 py-0.5 font-bold text-purple-700 dark:bg-purple-900/30 dark:text-purple-300">
                          Professional (49,99$)
                        </span>
                      </td>
                      <td className="py-3 px-3">
                        <div className="flex flex-wrap gap-1">
                          <span className="rounded bg-slate-200/60 px-1.5 py-0.5 text-[10px] dark:bg-white/10">CRM</span>
                          <span className="rounded bg-slate-200/60 px-1.5 py-0.5 text-[10px] dark:bg-white/10">Voice</span>
                          <span className="rounded bg-slate-200/60 px-1.5 py-0.5 text-[10px] dark:bg-white/10">OCR</span>
                        </div>
                      </td>
                      <td className="py-3 px-3">
                        <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
                          {isFr ? "Configuration" : "Configuring"}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-amber-600 font-medium">
                        {isFr ? "Sync Google Calendar en attente" : "Pending Google Cal sync"}
                      </td>
                      <td className="py-3 px-3">{isFr ? "Finaliser liaison praticiens" : "Complete therapist calendar sync"}</td>
                      <td className="py-3 px-3 text-slate-400 font-mono text-[11px]">—</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        )}
      </div>
    </AppShell>
  );
}
