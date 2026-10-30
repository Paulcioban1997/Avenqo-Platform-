"use client";

import React, { useState, useEffect } from "react";
import {
  Calendar,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  RefreshCw,
  Unlink,
  Clock,
  ShieldCheck,
} from "lucide-react";
import type { AppTranslations } from "@/lib/i18n/app-dictionary";
import { getAuthHeaders } from "@/lib/api-headers";
import { useLocale } from "@/lib/i18n/locale-context";
import { dateText } from "./crm-format";

interface ConnectionStatus {
  connected: boolean;
  connection_status?: "CONNECTED" | "RECONNECT_REQUIRED" | "DISCONNECTED" | "ERROR";
  provider?: string | null;
  account_email?: string | null;
  last_sync_at?: string | null;
  scopes?: string[];
  calendar_id?: string | null;
  sync_status?: string | null;
  sync_error?: string | null;
  requires_reconnect?: boolean;
  reconnect_message?: string | null;
}

interface GoogleCalendarOption {
  id: string;
  summary: string;
  primary?: boolean;
  time_zone?: string | null;
}

interface CRMCalendarConnectionCardProps {
  t: AppTranslations;
}

export function CRMCalendarConnectionCard({ t }: CRMCalendarConnectionCardProps) {
  const { locale } = useLocale();
  const [googleStatus, setGoogleStatus] = useState<ConnectionStatus>({ connected: false });
  const [isLoading, setIsLoading] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [calendars, setCalendars] = useState<GoogleCalendarOption[]>([]);

  useEffect(() => {
    fetchConnectionStatus();
    if (new URLSearchParams(window.location.search).get("calendar_oauth") === "failed") {
      setError("La reconnexion Google Calendar a échoué. Relancez-la depuis ce navigateur ; aucune réservation n’a été modifiée.");
    }
  }, []);

  const fetchConnectionStatus = async () => {
    setIsLoading(true);
    try {
      const headers = getAuthHeaders();

      const res = await fetch("/api/v1/crm/calendar/connection", { headers });
      if (!res.ok) {
        setGoogleStatus({ connected: false, connection_status: "ERROR" });
        return;
      }
      if (res.ok) {
        const data = await res.json();
        const needsReconnect = Boolean(
          data.requires_reconnect ||
          data.connection_status === "RECONNECT_REQUIRED" ||
          data.sync_status === "reconnect_required" ||
          data.sync_status === "revoked"
        );
        setGoogleStatus({
          connected: Boolean(data.connected) && !needsReconnect,
          connection_status: data.connection_status,
          provider: data.provider,
          account_email: data.account_email,
          last_sync_at: data.last_synced_at,
          calendar_id: data.calendar_id,
          sync_status: data.sync_status,
          sync_error: data.sync_error,
          requires_reconnect: needsReconnect,
          reconnect_message: data.reconnect_message || (needsReconnect ? "Reconnectez Google Calendar pour reprendre les réservations" : null),
        });
      }
    } catch {
      setGoogleStatus({ connected: false, connection_status: "ERROR" });
    } finally {
      setIsLoading(false);
    }
  };

  const loadCalendars = async () => {
    const res = await fetch("/api/v1/crm/calendar/google/calendars", { headers: getAuthHeaders() });
    if (!res.ok) return;
    const data = await res.json();
    setCalendars(data.calendars || []);
  };

  useEffect(() => {
    if (!googleStatus.connected || googleStatus.requires_reconnect) return;
    void loadCalendars();
    void fetch("/api/v1/crm/calendar/google/sync", {
      method: "POST",
      headers: getAuthHeaders(),
    }).then(() => fetchConnectionStatus());
  }, [googleStatus.connected]);

  const handleCalendarSelection = async (calendarId: string) => {
    const res = await fetch("/api/v1/crm/calendar/google/selection", {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...getAuthHeaders() },
      body: JSON.stringify({ calendar_id: calendarId }),
    });
    if (res.ok) setGoogleStatus((current) => ({ ...current, calendar_id: calendarId }));
  };

  const handleConnectGoogle = async () => {
    setIsConnecting(true);
    setError(null);
    try {
      const headers = getAuthHeaders();

      const res = await fetch("/api/v1/crm/calendar/google/auth-url", { headers: { ...headers, "X-Avenqo-Calendar-Return-Origin": window.location.origin } });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const detail = typeof err.detail === "string" ? err.detail : null;
        throw new Error(detail || (res.status === 400
          ? "Cette adresse Avenqo n'est pas autorisée pour la connexion Google Calendar. Contactez le support."
          : "La connexion Google Calendar est momentanément indisponible. Réessayez."));
      }
      const data = await res.json();
      const targetUrl = data.auth_url || data.url;
      if (!targetUrl) throw new Error("Google Calendar n'a pas fourni de lien de connexion. Réessayez.");
      window.location.href = targetUrl;
    } catch (err: any) {
      setError(err.message || "Erreur de connexion");
      setIsConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    if (!confirm("Voulez-vous vraiment déconnecter la synchronisation Google Calendar ?")) return;

    setIsLoading(true);
    try {
      await fetch("/api/v1/crm/calendar/disconnect?provider=google", {
        method: "POST",
        headers: getAuthHeaders(),
      });
      fetchConnectionStatus();
    } catch {
      // ignore
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      {error && (
        <div className="p-3.5 rounded-xl bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900/40 text-amber-800 dark:text-amber-200 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Google Calendar Provider */}
        <div className="p-5 rounded-2xl bg-white dark:bg-[#0B0F19] border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2.5">
                <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-950/50 flex items-center justify-center border border-blue-100 dark:border-blue-900/40">
                  <Calendar className="w-5 h-5 text-[#0076FF]" />
                </div>
                <div>
                  <h4 className="text-sm font-bold text-slate-900 dark:text-white">
                    Google Calendar
                  </h4>
                  <span className="text-xs text-slate-400">{t.integrations.googleCalendarDescription}</span>
                </div>
              </div>

              {googleStatus.connected ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  {t.crm.calendar.connected || "Connecté"}
                </span>
              ) : googleStatus.requires_reconnect ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-200 border border-amber-300 dark:border-amber-800/60">
                  <AlertCircle className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
                  Reconnexion requise
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 dark:bg-slate-800 text-slate-500">
                  {googleStatus.connection_status === "ERROR" ? "Erreur de connexion" : t.crm.calendar.disconnected || "Non connecté"}
                </span>
              )}
            </div>

            <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
              {t.integrations.googleCalendarDescription}
            </p>

            {googleStatus.requires_reconnect && (
              <div className="mt-3 p-3.5 rounded-xl bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900/40 text-xs space-y-2">
                <div className="flex items-start gap-2.5">
                  <AlertCircle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <p className="font-bold text-amber-900 dark:text-amber-200">
                      Reconnectez Google Calendar pour reprendre les réservations
                    </p>
                    <p className="text-[11px] text-amber-800 dark:text-amber-300/90 leading-relaxed">
                      Le jeton pour <strong className="font-semibold">{googleStatus.account_email || "votre compte Google"}</strong> est expiré ou révoqué. Les réservations sont suspendues pour éviter tout conflit ou double réservation tant que la reconnexion n'a pas été confirmée.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {googleStatus.connected && (
              <div className="mt-3 p-3 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 text-xs space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">{t.shell.company}:</span>
                  <span className="font-semibold text-slate-900 dark:text-white truncate max-w-[200px]">
                    {googleStatus.account_email || "Google Workspace"}
                  </span>
                </div>
                {googleStatus.last_sync_at && (
                  <div className="flex items-center justify-between text-[11px] text-slate-400">
                    <span>{t.integrations.lastSynced}:</span>
                    <span>{dateText(googleStatus.last_sync_at, locale, t.common.insufficientData, { dateStyle: "medium", timeStyle: "short" })}</span>
                  </div>
                )}
                {calendars.length > 0 && (
                  <label className="flex items-center justify-between gap-3 text-xs text-slate-400">
                    <span>{t.integrations.googleCalendar}:</span>
                    <select
                      value={googleStatus.calendar_id || ""}
                      onChange={(event) => void handleCalendarSelection(event.target.value)}
                      className="max-w-[200px] rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs font-semibold text-slate-900 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                    >
                      {calendars.map((calendar) => (
                        <option key={calendar.id} value={calendar.id}>
                          {calendar.summary}{calendar.primary ? " (principal)" : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </div>
            )}
          </div>

          <div className="pt-3 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
              <span>{googleStatus.connected ? "Connecté" : googleStatus.requires_reconnect ? "Reconnexion requise" : googleStatus.connection_status === "ERROR" ? "Erreur de connexion" : "Déconnecté"}</span>
            </div>

            {googleStatus.connected ? (
              <button
                onClick={handleDisconnect}
                disabled={isLoading}
                className="px-3.5 py-1.5 text-xs font-semibold rounded-xl text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition flex items-center gap-1.5"
              >
                <Unlink className="w-3.5 h-3.5" />
                <span>{t.crm.calendar.disconnect || "Déconnecter"}</span>
              </button>
            ) : googleStatus.requires_reconnect ? (
              <button
                onClick={handleConnectGoogle}
                disabled={isConnecting}
                className="px-4 py-2 text-xs font-bold rounded-xl bg-amber-600 hover:bg-amber-700 text-white transition flex items-center gap-2 shadow-sm"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isConnecting ? "animate-spin" : ""}`} />
                <span>
                  {isConnecting ? "Connexion..." : "Reconnecter Google Calendar"}
                </span>
              </button>
            ) : (
              <button
                onClick={handleConnectGoogle}
                disabled={isConnecting}
                className="px-4 py-1.5 text-xs font-semibold rounded-xl bg-[#0076FF] text-white hover:bg-blue-600 transition flex items-center gap-1.5 shadow-sm"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>
                  {isConnecting ? t.integrations.googleCalendarConnecting : t.crm.calendar.connectGoogle}
                </span>
              </button>
            )}
          </div>
        </div>

        {/* Microsoft Outlook Provider (Architecture ready) */}
        <div className="p-5 rounded-2xl bg-white dark:bg-[#0B0F19] border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col justify-between space-y-4 opacity-75">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2.5">
                <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-950/50 flex items-center justify-center border border-blue-100 dark:border-blue-900/40">
                  <Calendar className="w-5 h-5 text-[#0076FF]" />
                </div>
                <div>
                  <h4 className="text-sm font-bold text-slate-900 dark:text-white">
                    {t.integrations.categoryAutomation}
                  </h4>
                  <span className="text-xs text-slate-400">{t.integrations.categoryAutomation}</span>
                </div>
              </div>

              <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 dark:bg-slate-800 text-slate-500">
                {t.integrations.googleCalendarDisconnected}
              </span>
            </div>

            <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
              {t.integrations.googleCalendarDescription}
            </p>
          </div>

          <div className="pt-3 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
            <span className="text-[11px] text-slate-400">{t.integrations.statusDisconnected}</span>
            <button
              disabled
              className="px-4 py-1.5 text-xs font-semibold rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-400 cursor-not-allowed"
            >
              {t.integrations.googleCalendarDisconnected}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
