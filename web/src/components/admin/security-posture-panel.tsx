"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  Shield,
  ShieldCheck,
  ShieldAlert,
  RefreshCw,
  PlugZap,
  CheckCircle2,
  AlertTriangle,
  Lock,
  Activity,
} from "lucide-react";
import { apiFetch } from "@/lib/api-request";

interface SecurityControlItem {
  id: string;
  title_fr: string;
  title_en: string;
  status: "enforced" | "partial" | "attention_required" | string;
  details_fr: string;
  details_en: string;
  evidence?: Record<string, unknown>;
}

interface CrowdStrikeCheckSnapshot {
  status: string;
  siem_enabled: boolean;
  verified: boolean;
  protected_by_crowdstrike: boolean;
  message: string;
  checked_at_utc: string;
  endpoint_host?: string | null;
  http_status?: number | null;
  latency_ms?: number | null;
}

interface CrowdStrikeSummary {
  siem_enabled: boolean;
  status: string;
  verified: boolean;
  protected_by_crowdstrike: boolean;
  display_badge_fr: string;
  display_badge_en: string;
  deployment_mode: string;
  kernel_sensor_assumed: boolean;
  endpoint_host?: string | null;
  fcs_ci_workflow_present?: boolean;
  last_connection_check?: CrowdStrikeCheckSnapshot | null;
}

interface SecurityPostureResponse {
  evaluated_at_utc: string;
  environment: string;
  native_security_mode: string;
  summary_counts: {
    total_controls: number;
    enforced: number;
    partial: number;
    attention_required: number;
  };
  controls: SecurityControlItem[];
  crowdstrike: CrowdStrikeSummary;
}

interface NormalizedSecurityEventItem {
  event_id: string;
  timestamp: string;
  event_type: string;
  severity: "low" | "medium" | "high" | "critical" | string;
  outcome: string;
  summary: string;
  company_id?: string | null;
  ip_address?: string | null;
}

interface SecurityEventsResponse {
  events_count: number;
  supported_categories: string[];
  events: NormalizedSecurityEventItem[];
}

interface SecurityPosturePanelProps {
  isFr: boolean;
}

export function SecurityPosturePanel({ isFr }: SecurityPosturePanelProps) {
  const [posture, setPosture] = useState<SecurityPostureResponse | null>(null);
  const [eventsData, setEventsData] = useState<SecurityEventsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [testingConn, setTestingConn] = useState<boolean>(false);
  const [connResult, setConnResult] = useState<CrowdStrikeCheckSnapshot | null>(null);

  const loadSecuritySection = useCallback(async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const [postureRes, eventsRes] = await Promise.all([
        apiFetch("/api/v1/admin/security/posture"),
        apiFetch("/api/v1/admin/security/events?limit=15"),
      ]);
      const postureJson = (await postureRes.json()) as SecurityPostureResponse;
      const eventsJson = (await eventsRes.json()) as SecurityEventsResponse;
      setPosture(postureJson);
      setEventsData(eventsJson);
      if (postureJson.crowdstrike?.last_connection_check) {
        setConnResult(postureJson.crowdstrike.last_connection_check);
      }
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : isFr
            ? "Impossible de charger la posture de sécurité."
            : "Unable to load security posture.";
      setErrorMsg(message);
    } finally {
      setLoading(false);
    }
  }, [isFr]);

  useEffect(() => {
    void loadSecuritySection();
  }, [loadSecuritySection]);

  const handleTestCrowdStrikeConnection = async () => {
    setTestingConn(true);
    try {
      const res = await apiFetch("/api/v1/admin/security/crowdstrike/test-connection", {
        method: "POST",
        headers: { "X-Requested-With": "avenqo-web" },
      });
      const result = (await res.json()) as CrowdStrikeCheckSnapshot;
      setConnResult(result);
      await loadSecuritySection();
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : isFr
            ? "Échec du test de connexion CrowdStrike."
            : "CrowdStrike connection test failed.";
      setErrorMsg(message);
    } finally {
      setTestingConn(false);
    }
  };

  const cs = posture?.crowdstrike;
  // Strict truthfulness rule: ONLY true when enabled AND live HEC connection verified.
  const isCrowdStrikeVerifiedActive = Boolean(
    cs?.siem_enabled && cs?.verified && cs?.protected_by_crowdstrike && cs?.status === "connected_verified"
  );

  const crowdStrikeHeadlineBadge = isCrowdStrikeVerifiedActive
    ? isFr
      ? "CrowdStrike NG-SIEM actif (connexion vérifiée)"
      : "CrowdStrike NG-SIEM active (connection verified)"
    : cs?.siem_enabled
      ? isFr
        ? cs.display_badge_fr
        : cs.display_badge_en
      : isFr
        ? "Non configuré — mode natif actif"
        : "Not configured — native mode active";

  const renderStatusPill = (status: string) => {
    if (status === "enforced") {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
          <CheckCircle2 className="h-3 w-3" />
          {isFr ? "Vérifié" : "Enforced"}
        </span>
      );
    }
    if (status === "partial") {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-0.5 text-[11px] font-semibold text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
          <AlertTriangle className="h-3 w-3" />
          {isFr ? "Partiel / Env" : "Partial / Env"}
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 px-2.5 py-0.5 text-[11px] font-semibold text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">
        <ShieldAlert className="h-3 w-3" />
        {isFr ? "Action requise" : "Action required"}
      </span>
    );
  };

  const renderSeverityBadge = (severity: string) => {
    const normalized = severity.toLowerCase();
    if (normalized === "critical" || normalized === "high") {
      return (
        <span className="rounded bg-rose-100 px-2 py-0.5 font-mono text-[10px] font-bold uppercase text-rose-700 dark:bg-rose-950/50 dark:text-rose-300">
          {normalized}
        </span>
      );
    }
    if (normalized === "medium") {
      return (
        <span className="rounded bg-amber-100 px-2 py-0.5 font-mono text-[10px] font-bold uppercase text-amber-700 dark:bg-amber-950/50 dark:text-amber-300">
          {normalized}
        </span>
      );
    }
    return (
      <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-[10px] font-bold uppercase text-slate-700 dark:bg-white/10 dark:text-slate-300">
        {normalized}
      </span>
    );
  };

  return (
    <section
      aria-label={isFr ? "Sécurité" : "Security"}
      className="space-y-6 rounded-2xl border border-slate-200/80 bg-white p-6 shadow-xs dark:border-white/[0.08] dark:bg-[#0B132B]"
    >
      {/* Section Header */}
      <div className="flex flex-col gap-3 border-b border-slate-200/80 pb-4 sm:flex-row sm:items-center sm:justify-between dark:border-white/[0.08]">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="rounded-xl bg-indigo-50 p-2 text-indigo-600 dark:bg-indigo-950/50 dark:text-indigo-400">
              <Shield className="h-5 w-5" />
            </div>
            <h2 className="text-lg font-bold text-slate-900 dark:text-white">
              {isFr ? "Sécurité · Posture Native & Télémétrie SIEM" : "Security · Native Posture & SIEM Telemetry"}
            </h2>
          </div>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            {isFr
              ? "Audit en direct des contrôles Avenqo (RLS, MFA, Webhooks, Jetons signés, SBOM) et connecteur optionnel CrowdStrike Falcon Cloud Security / NG-SIEM."
              : "Live audit of Avenqo native controls (RLS, MFA, Webhooks, Signed Tokens, SBOM) and optional CrowdStrike Falcon Cloud Security / NG-SIEM connector."}
          </p>
        </div>

        <button
          type="button"
          onClick={() => void loadSecuritySection()}
          disabled={loading}
          className="inline-flex items-center gap-1.5 self-start rounded-xl border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-700 transition-colors hover:bg-slate-100 disabled:opacity-60 sm:self-auto dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-200 dark:hover:bg-white/[0.08]"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          {isFr ? "Actualiser l'audit" : "Refresh audit"}
        </button>
      </div>

      {errorMsg && (
        <div
          role="alert"
          className="rounded-xl border border-rose-200 bg-rose-50/70 p-3 text-xs font-medium text-rose-700 dark:border-rose-800/50 dark:bg-rose-950/30 dark:text-rose-300"
        >
          {errorMsg}
        </div>
      )}

      {/* Optional CrowdStrike Integration Card */}
      <div className="rounded-2xl border border-slate-200/80 bg-slate-50/60 p-5 dark:border-white/[0.08] dark:bg-white/[0.02]">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-bold text-slate-900 dark:text-white">
                CrowdStrike Falcon Cloud Security & Next-Gen SIEM
              </span>
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                  isCrowdStrikeVerifiedActive
                    ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300"
                    : cs?.siem_enabled
                      ? "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300"
                      : "bg-slate-200/80 text-slate-700 dark:bg-white/10 dark:text-slate-300"
                }`}
              >
                {isCrowdStrikeVerifiedActive ? (
                  <ShieldCheck className="h-3.5 w-3.5" />
                ) : (
                  <Lock className="h-3 w-3" />
                )}
                {crowdStrikeHeadlineBadge}
              </span>
            </div>
            <p className="text-xs text-slate-600 dark:text-slate-400">
              {isFr
                ? "Architecture PaaS managée (Railway / Vercel) sans agent noyau : scan CI/CD fcs-action + télémétrie HEC HTTPS optionnelle avec purge stricte des NIP, jetons, secrets, documents et transcriptions vocales."
                : "Managed PaaS architecture (Railway / Vercel) with zero kernel sensor assumption: CI/CD fcs-action scanning + optional HTTPS HEC telemetry with strict scrubbing of PINs, tokens, secrets, documents, and voice transcripts."}
            </p>
            <div className="flex flex-wrap gap-3 pt-1 font-mono text-[11px] text-slate-500 dark:text-slate-400">
              <span>
                {isFr ? "Statut technique" : "Technical status"}: {cs?.status ?? "disabled"}
              </span>
              <span>
                {isFr ? "Workflow CI FCS/SBOM" : "FCS/SBOM CI Workflow"}:{" "}
                {cs?.fcs_ci_workflow_present ? "present" : "missing"}
              </span>
              {cs?.endpoint_host && (
                <span>
                  HEC: {cs.endpoint_host}
                </span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => void handleTestCrowdStrikeConnection()}
              disabled={testingConn}
              className="inline-flex items-center gap-2 rounded-xl bg-[#0076FF] px-4 py-2 text-xs font-semibold text-white shadow-xs transition-colors hover:bg-blue-600 disabled:opacity-60"
            >
              <PlugZap className="h-3.5 w-3.5" />
              {testingConn
                ? isFr
                  ? "Vérification..."
                  : "Testing..."
                : isFr
                  ? "Tester la connexion HEC"
                  : "Test HEC connection"}
            </button>
          </div>
        </div>

        {connResult && (
          <div className="mt-4 rounded-xl border border-slate-200/80 bg-white p-3 text-xs dark:border-white/[0.08] dark:bg-[#0B132B]">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-semibold text-slate-800 dark:text-slate-200">
                {connResult.message}
              </span>
              <span className="font-mono text-[11px] text-slate-500 dark:text-slate-400">
                status={connResult.status}
                {connResult.http_status ? ` · HTTP ${connResult.http_status}` : ""}
                {typeof connResult.latency_ms === "number" ? ` · ${connResult.latency_ms} ms` : ""}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Native Controls Grid */}
      {loading && !posture ? (
        <div className="py-8 text-center text-xs text-slate-400">
          {isFr ? "Inspection des contrôles de sécurité en cours..." : "Inspecting live security controls..."}
        </div>
      ) : posture ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">
              {isFr ? "Contrôles de Sécurité Natifs Avenqo" : "Avenqo Native Security Controls"}
            </h3>
            <span className="font-mono text-[11px] text-slate-500 dark:text-slate-400">
              {posture.summary_counts.enforced}/{posture.summary_counts.total_controls}{" "}
              {isFr ? "contrôles vérifiés" : "controls enforced"} ({posture.environment})
            </span>
          </div>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {posture.controls.map((ctrl) => (
              <div
                key={ctrl.id}
                className="rounded-xl border border-slate-200/80 p-4 dark:border-white/[0.08]"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="text-xs font-bold text-slate-900 dark:text-white">
                    {isFr ? ctrl.title_fr : ctrl.title_en}
                  </div>
                  {renderStatusPill(ctrl.status)}
                </div>
                <p className="mt-1.5 text-[11px] leading-relaxed text-slate-600 dark:text-slate-400">
                  {isFr ? ctrl.details_fr : ctrl.details_en}
                </p>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* Normalized Recent Security Alerts */}
      <div className="space-y-3 pt-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-indigo-500" />
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">
              {isFr
                ? "Événements & Alertes de Sécurité Normalisés Récents"
                : "Recent Normalized Security Events & Alerts"}
            </h3>
          </div>
          <span className="font-mono text-[11px] text-slate-500 dark:text-slate-400">
            {eventsData?.events_count ?? 0} {isFr ? "entrées" : "entries"}
          </span>
        </div>

        {!eventsData || eventsData.events.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-200 p-4 text-center text-xs text-slate-500 dark:border-white/10 dark:text-slate-400">
            {isFr
              ? "Aucune alerte de sécurité récente détectée."
              : "No recent security alerts detected."}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200/80 text-[10px] font-semibold uppercase text-slate-400 dark:border-white/[0.08]">
                  <th className="py-2 pr-3">{isFr ? "Horodatage" : "Timestamp"}</th>
                  <th className="py-2 pr-3">{isFr ? "Catégorie" : "Category"}</th>
                  <th className="py-2 pr-3">{isFr ? "Sévérité" : "Severity"}</th>
                  <th className="py-2 pr-3">{isFr ? "Résultat" : "Outcome"}</th>
                  <th className="py-2 pr-3">{isFr ? "Synthèse expurgée" : "Sanitized Summary"}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700 dark:divide-white/[0.05] dark:text-slate-300">
                {eventsData.events.map((ev) => (
                  <tr key={ev.event_id}>
                    <td className="py-2.5 pr-3 font-mono text-[11px] whitespace-nowrap text-slate-500">
                      {ev.timestamp ? new Date(ev.timestamp).toLocaleString(isFr ? "fr-CA" : "en-CA") : "—"}
                    </td>
                    <td className="py-2.5 pr-3 font-mono text-[11px] font-medium text-slate-900 dark:text-white">
                      {ev.event_type}
                    </td>
                    <td className="py-2.5 pr-3">{renderSeverityBadge(ev.severity)}</td>
                    <td className="py-2.5 pr-3 font-mono text-[11px]">{ev.outcome}</td>
                    <td className="py-2.5 pr-3 text-xs">{ev.summary}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
