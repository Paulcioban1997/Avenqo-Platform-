"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ShieldCheck, RefreshCw, LogOut, KeyRound, Users } from "lucide-react";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";
import { useSession } from "@/lib/session-context";

type SupportGrant = { id: string; expires_at: string; reason: string };
function SupportAccess() {
  const { locale } = useLocale();
  const fr = locale.startsWith("fr");
  const [grants, setGrants] = useState<SupportGrant[]>([]);
  const [email, setEmail] = useState("");
  const [reason, setReason] = useState("");
  const [duration, setDuration] = useState(15);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const load = useCallback(async () => {
    try { setGrants(await (await apiFetch("/api/v1/security/support-access")).json()); setError(false); }
    catch { setError(true); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const grant = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true); setError(false);
    try {
      await apiFetch("/api/v1/security/support-access", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ recipient_email: email, reason, duration_minutes: duration }) });
      setEmail(""); setReason(""); await load();
    } catch { setError(true); }
    finally { setBusy(false); }
  };
  const revoke = async (id: string) => {
    setBusy(true);
    try { await apiFetch(`/api/v1/security/support-access/${id}`, { method: "DELETE" }); await load(); }
    catch { setError(true); }
    finally { setBusy(false); }
  };
  return <section className={panel}><h2 className="text-lg font-semibold">{fr ? "Accès exceptionnel au support" : "Temporary support access"}</h2>
    <p className="my-3 text-sm text-slate-500">{fr ? "Autorisez un compte de support PMC identifié à consulter les données Retail en lecture seule pour diagnostiquer un problème. Chaque accès est journalisé. L’autorisation expire automatiquement et peut être révoquée à tout moment." : "Allow an identified PMC support account to read Retail data to diagnose a problem. Each access is logged. Consent expires automatically and can be revoked at any time."}</p>
    {error && <p role="alert" className="my-3 text-sm text-rose-500">{fr ? "L’action ou le chargement a échoué. Vérifiez le compte de support et réessayez." : "The action or request failed. Check the support account and retry."}</p>}
    <form onSubmit={grant} className="grid gap-3 md:grid-cols-2">
      <label className="text-sm">{fr ? "Courriel du compte de support" : "Support account email"}<input className="mt-1 w-full rounded-xl border bg-transparent p-3" type="email" value={email} onChange={e => setEmail(e.target.value)} required /></label>
      <label className="text-sm">{fr ? "Durée de l’autorisation" : "Consent duration"}<select className="mt-1 w-full rounded-xl border bg-white p-3 dark:bg-[#0B132B]" value={duration} onChange={e => setDuration(Number(e.target.value))}>{[5, 15, 30, 60].map(n => <option key={n} value={n}>{n} min</option>)}</select></label>
      <label className="text-sm md:col-span-2">{fr ? "Motif du diagnostic" : "Diagnostic reason"}<input className="mt-1 w-full rounded-xl border bg-transparent p-3" value={reason} onChange={e => setReason(e.target.value)} minLength={10} maxLength={250} required /></label>
      <button disabled={busy} type="submit" className="rounded-xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white disabled:opacity-50">{fr ? "Autoriser la consultation temporaire" : "Authorize temporary read access"}</button>
    </form>
    <ul className="mt-4 divide-y divide-slate-200 dark:divide-white/10">{grants.map(g => <li key={g.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm"><div><p>{g.reason}</p><p className="text-xs text-slate-500">{fr ? "Expiration" : "Expires"} : {new Date(g.expires_at).toLocaleString(locale)}</p></div><button disabled={busy} onClick={() => void revoke(g.id)} className="rounded-xl border border-rose-300 px-3 py-2 text-rose-600">{fr ? "Révoquer l’accès support" : "Revoke support access"}</button></li>)}</ul>
  </section>;
}

type SecuritySession = { id: string; current: boolean; created_at: string; expires_at: string };
type AuditEvent = { id: string; action: string; target_type: string; created_at: string };
type Overview = { email_verified: boolean; role: string; mfa_supported: boolean; mfa_enabled?: boolean; session_revocation_supported: boolean; recommendations?: { code: string }[] };
type LoginRow = { id: string; outcome: string; ip_address: string | null; created_at: string | null };
const panel = "rounded-2xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-[#0B132B]";

export function SecurityView() {
  const { locale } = useLocale();
  const fr = locale.startsWith("fr");
  const text = (f: string, e: string) => fr ? f : e;
  const session = useSession();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [sessions, setSessions] = useState<SecuritySession[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [logins, setLogins] = useState<LoginRow[]>([]);
  const [mfaSecret, setMfaSecret] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [auditError, setAuditError] = useState(false);
  const canAudit = ["owner", "admin"].includes(session.identity?.user.role ?? "");
  const load = useCallback(async () => {
    setLoading(true); setError(false); setAuditError(false);
    try {
      const [o, s, h] = await Promise.all([
        apiFetch("/api/v1/security/overview"),
        apiFetch("/api/v1/security/sessions"),
        apiFetch("/api/v1/security/login-history"),
      ]);
      setOverview(await o.json()); setSessions(await s.json());
      if (h.ok) setLogins(await h.json());
    } catch { setError(true); }
    if (canAudit) {
      try { setAudit(await (await apiFetch("/api/v1/security/audit?limit=50")).json()); }
      catch { setAuditError(true); }
    }
    setLoading(false);
  }, [canAudit]);
  useEffect(() => { void load(); }, [load]);
  const revoke = async (id: string) => {
    setBusy(id); setError(false);
    try { await apiFetch(`/api/v1/security/sessions/${id}`, { method: "DELETE" }); await load(); }
    catch { setError(true); }
    finally { setBusy(null); }
  };
  const date = (value: string) => new Date(value).toLocaleString(locale);
  return <div className="mx-auto max-w-6xl space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div><p className="mb-2 text-xs font-semibold uppercase tracking-widest text-cyan-600 dark:text-cyan-300">Avenqo</p>
        <h1 className="flex items-center gap-3 text-3xl font-bold"><ShieldCheck aria-hidden />{text("Centre de sécurité", "Security center")}</h1>
        <p className="mt-2 text-sm text-slate-500">{text("Protégez votre compte et consultez les contrôles de votre entreprise.", "Protect your account and review your organization controls.")}</p></div>
      <button onClick={() => void load()} disabled={loading || busy !== null} className="flex items-center gap-2 rounded-xl border px-4 py-2 text-sm disabled:opacity-50"><RefreshCw size={16} aria-hidden />{text("Actualiser", "Refresh")}</button>
    </div>
    {error && <div role="alert" className="rounded-xl border border-rose-400 p-4 text-sm">{text("Les informations n’ont pas pu être chargées ou l’action a échoué. Réessayez.", "Information could not be loaded or the action failed. Please retry.")}</div>}
    {loading && <p role="status">{text("Chargement des contrôles…", "Loading controls…")}</p>}
    {overview && <div className="grid gap-4 md:grid-cols-3">
      <section className={panel}><ShieldCheck className="mb-3 text-cyan-500" aria-hidden /><h2 className="font-semibold">{text("Adresse courriel", "Email address")}</h2><p className="mt-2 text-sm">{overview.email_verified ? text("Vérifiée", "Verified") : text("À vérifier", "Not verified")}</p></section>
      <section className={panel}><KeyRound className="mb-3 text-cyan-500" aria-hidden /><h2 className="font-semibold">{text("Authentification multifacteur", "Multi-factor authentication")}</h2>
        <p className="mt-2 text-sm">{overview.mfa_enabled ? text("Activée sur ce compte.", "Enabled on this account.") : text("Non activée. Protégez la connexion avec un code temporaire.", "Not enabled. Protect sign-in with a temporary code.")}</p>
        {!overview.mfa_enabled && <button className="mt-3 rounded-xl border px-3 py-2 text-sm" onClick={async () => {
          const response = await apiFetch("/api/v1/security/mfa/enroll", { method: "POST" });
          if (response.ok) { const body = await response.json(); setMfaSecret(body.secret); }
        }}>{text("Générer une clé", "Generate a key")}</button>}
        {mfaSecret && <p className="mt-3 break-all font-mono text-xs">{mfaSecret}</p>}
        {mfaSecret && <form className="mt-3 flex gap-2" onSubmit={async (event) => {
          event.preventDefault();
          const response = await apiFetch("/api/v1/security/mfa/confirm", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code: mfaCode }) });
          if (response.ok) {
            const body = await response.json();
            setRecoveryCodes(body.recovery_codes || []);
            setMfaSecret("");
            setMfaCode("");
            await load();
          }
        }}>
          <input className="flex-1 rounded-xl border bg-transparent px-3 py-2 text-sm" value={mfaCode} onChange={(e) => setMfaCode(e.target.value)} placeholder="123456" />
          <button className="rounded-xl bg-blue-600 px-3 text-sm text-white">{text("Confirmer", "Confirm")}</button>
        </form>}
        {recoveryCodes.length > 0 && (
          <div className="mt-3 rounded-xl border border-amber-300 p-3 text-xs">
            <p className="mb-2 font-semibold">{text("Conservez ces codes de récupération. Ils ne seront plus affichés.", "Store these recovery codes. They will not be shown again.")}</p>
            <ul className="space-y-1 font-mono">{recoveryCodes.map((code) => <li key={code}>{code}</li>)}</ul>
          </div>
        )}
      </section>
      <section className={panel}><Users className="mb-3 text-cyan-500" aria-hidden /><h2 className="font-semibold">{text("Utilisateurs et autorisations", "Users and permissions")}</h2><Link href="/settings" className="mt-2 inline-block text-sm text-blue-600 dark:text-cyan-300 underline">{text("Gérer les paramètres de l’entreprise", "Manage organization settings")}</Link></section>
    </div>}
    <section className={panel}><h2 className="text-lg font-semibold">{text("Mes sessions actives", "My active sessions")}</h2>
      <p className="my-2 text-sm text-slate-500">{text("La révocation bloque immédiatement les accès et le renouvellement de la session choisie.", "Revocation immediately blocks access and renewal for the selected session.")}</p>
      <ul className="divide-y divide-slate-200 dark:divide-white/10">{sessions.map(s => <li key={s.id} className="flex flex-wrap items-center justify-between gap-3 py-4">
        <div className="text-sm"><p className="font-medium">{s.current ? text("Cette session", "This session") : text("Autre session", "Other session")}</p>
          <p className="mt-1 text-slate-500">{text("Ouverte le", "Created")} {date(s.created_at)}</p><p className="text-slate-500">{text("Expire le", "Expires")} {date(s.expires_at)}</p></div>
        {s.current ? <span className="rounded-full bg-cyan-500/10 px-3 py-1 text-xs text-cyan-700 dark:text-cyan-300">{text("Session actuelle", "Current session")}</span>
          : <button disabled={busy !== null} onClick={() => void revoke(s.id)} className="flex items-center gap-2 rounded-xl border border-rose-300 px-3 py-2 text-sm text-rose-600 disabled:opacity-50"><LogOut size={14} aria-hidden />{text("Révoquer", "Revoke")}</button>}
      </li>)}</ul>
      {!loading && !error && sessions.length === 0 && <p className="py-4 text-sm">{text("Aucune session active retournée.", "No active sessions returned.")}</p>}
    </section>
    <section className={panel}><h2 className="text-lg font-semibold">{text("Historique des connexions", "Sign-in history")}</h2>
      <ul className="mt-3 divide-y divide-slate-200 text-sm dark:divide-white/10">
        {logins.map((row) => (
          <li key={row.id} className="py-3">
            <p>{row.outcome}{row.ip_address ? ` · ${row.ip_address}` : ""}</p>
            <p className="text-xs text-slate-500">{row.created_at ? date(row.created_at) : ""}</p>
          </li>
        ))}
      </ul>
      {!loading && logins.length === 0 && <p className="mt-3 text-sm text-slate-500">{text("Aucune connexion enregistrée pour ce compte.", "No sign-in events recorded for this account.")}</p>}
    </section>
    <section className={panel}><h2 className="text-lg font-semibold">{text("Journal d’audit de l’entreprise", "Organization audit log")}</h2>
      {!canAudit ? <p className="mt-3 text-sm">{text("Consultation réservée aux propriétaires et administrateurs de l’entreprise.", "Only organization owners and administrators may view this log.")}</p>
        : auditError ? <p role="alert" className="mt-3 text-sm text-rose-500">{text("Le journal n’a pas pu être chargé.", "The log could not be loaded.")}</p>
        : <ul className="mt-3 divide-y divide-slate-200 dark:divide-white/10">{audit.map(e => <li key={e.id} className="py-3 text-sm"><p>{e.action === "session_revoked" ? text("Session révoquée", "Session revoked") : e.action === "tenant_switched" ? text("Changement d’entreprise", "Organization switched") : text("Action administrative", "Administrative action")}</p><p className="text-xs text-slate-500">{date(e.created_at)}</p></li>)}</ul>}
      {canAudit && !loading && !auditError && audit.length === 0 && <p className="mt-3 text-sm text-slate-500">{text("Aucun événement enregistré. Ce journal ne constitue pas un historique exhaustif des connexions.", "No events recorded. This log is not a complete sign-in history.")}</p>}
    </section>
    {session.identity?.user.role === "owner" && <SupportAccess />}
    <div className="flex flex-wrap gap-4 text-sm"><Link href="/trust" className="underline">{text("Centre de confiance", "Trust center")}</Link><Link href="/privacy" className="underline">{text("Confidentialité", "Privacy")}</Link><Link href="/contact" className="underline">{text("Signaler un incident", "Report an incident")}</Link></div>
  </div>;
}
