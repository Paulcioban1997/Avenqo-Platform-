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

interface ConnectionStatus {
  connected: boolean;
  provider?: string | null;
  account_email?: string | null;
  last_sync_at?: string | null;
  scopes?: string[];
}

interface CRMCalendarConnectionCardProps {
  t: AppTranslations;
}

export function CRMCalendarConnectionCard({ t }: CRMCalendarConnectionCardProps) {
  const [googleStatus, setGoogleStatus] = useState<ConnectionStatus>({ connected: false });
  const [isLoading, setIsLoading] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchConnectionStatus();
  }, []);

  const fetchConnectionStatus = async () => {
    setIsLoading(true);
    try {
      const headers = getAuthHeaders();

      const res = await fetch("/api/v1/crm/summary", { headers });
      if (res.ok) {
        const data = await res.json();
        const conn = data.active_calendar_connection;
        if (conn && conn.is_active) {
          setGoogleStatus({
            connected: true,
            provider: conn.provider,
            account_email: conn.account_email,
            last_sync_at: conn.last_sync_at,
          });
        } else {
          setGoogleStatus({ connected: false });
        }
      }
    } catch {
      setGoogleStatus({ connected: false });
    } finally {
      setIsLoading(false);
    }
  };

  const handleConnectGoogle = async () => {
    setIsConnecting(true);
    setError(null);
    try {
      const headers = getAuthHeaders();

      const res = await fetch("/api/v1/crm/calendar/google/auth-url", { headers });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Google OAuth non configuré sur ce serveur.");
      }
      const data = await res.json();
      if (data.url) {
        window.location.href = data.url;
      }
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
                  <span className="text-xs text-slate-400">Synchronisation bidirectionnelle</span>
                </div>
              </div>

              {googleStatus.connected ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  {t.crm.calendar.connected || "Connecté"}
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 dark:bg-slate-800 text-slate-500">
                  {t.crm.calendar.disconnected || "Non connecté"}
                </span>
              )}
            </div>

            <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
              Synchronise automatiquement les disponibilités réelles et crée instantanément les événements
              dans votre agenda Google Workspace. Chiffrement des jetons au repos AES-256.
            </p>

            {googleStatus.connected && (
              <div className="mt-3 p-3 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 text-xs space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Compte associé:</span>
                  <span className="font-semibold text-slate-900 dark:text-white truncate max-w-[200px]">
                    {googleStatus.account_email || "Google Workspace"}
                  </span>
                </div>
                {googleStatus.last_sync_at && (
                  <div className="flex items-center justify-between text-[11px] text-slate-400">
                    <span>Dernière synchro:</span>
                    <span>{new Date(googleStatus.last_sync_at).toLocaleString("fr-CA")}</span>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="pt-3 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
              <span>OAuth 2.0 Officiel</span>
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
            ) : (
              <button
                onClick={handleConnectGoogle}
                disabled={isConnecting}
                className="px-4 py-1.5 text-xs font-semibold rounded-xl bg-[#0076FF] text-white hover:bg-blue-600 transition flex items-center gap-1.5 shadow-sm"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>
                  {isConnecting ? "Connexion..." : t.crm.calendar.connectGoogle || "Connecter Google"}
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
                    Microsoft Outlook / 365
                  </h4>
                  <span className="text-xs text-slate-400">Connecteur Graph API</span>
                </div>
              </div>

              <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 dark:bg-slate-800 text-slate-500">
                Architecture prête
              </span>
            </div>

            <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
              Le moteur de calendrier Avenqo intègre l'abstraction modulaire CalendarProvider compatible avec Microsoft Graph pour Exchange et Office 365.
            </p>
          </div>

          <div className="pt-3 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
            <span className="text-[11px] text-slate-400">Prêt pour activation</span>
            <button
              disabled
              className="px-4 py-1.5 text-xs font-semibold rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-400 cursor-not-allowed"
            >
              Bientôt disponible
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
