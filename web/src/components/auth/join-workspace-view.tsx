"use client";

import { FormEvent, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ApiRequestError, apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";

export function JoinWorkspaceView() {
  const params = useSearchParams();
  const rawToken = params.get("token")?.trim() || "";
  const token = rawToken.length >= 60 ? rawToken : "";
  const { locale } = useLocale();
  const fr = locale.startsWith("fr");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [companyName, setCompanyName] = useState("");
  const [responsibility, setResponsibility] = useState("");

  useEffect(() => {
    const query = token
      ? `token=${encodeURIComponent(token)}`
      : email.trim() && code.trim()
        ? `email=${encodeURIComponent(email.trim())}&code=${encodeURIComponent(code.trim())}`
        : "";
    if (!query) return;
    let cancelled = false;
    void apiFetch(`/api/v1/workspace/invitations/preview?${query}`)
      .then(async (response) => {
        const payload = await response.json();
        if (cancelled || !response.ok) return;
        setCompanyName(String(payload.company_name || ""));
        setResponsibility(String(payload.job_title || ""));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [token, email, code]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch("/api/auth/accept-invitation", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", Accept: "application/json", "X-Requested-With": "avenqo-web" },
        body: JSON.stringify(
          email.trim() && code.trim()
            ? {
                email: email.trim(),
                code: code.trim(),
                first_name: firstName.trim(),
                last_name: lastName.trim(),
                password,
              }
            : {
                token: token || undefined,
                first_name: firstName.trim(),
                last_name: lastName.trim(),
                password,
              },
        ),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = typeof payload?.detail === "string"
          ? payload.detail
          : typeof payload?.error?.message === "string"
            ? payload.error.message
            : typeof payload?.message === "string"
              ? payload.message
              : "";
        throw new ApiRequestError("backend_error", response.status, detail);
      }
      window.location.assign(typeof payload.home === "string" ? payload.home : "/dashboard");
    } catch (err) {
      setError(
        err instanceof ApiRequestError && err.publicMessage
          ? err.publicMessage
          : fr
            ? "Cette invitation ne peut pas être acceptée."
            : "This invitation cannot be accepted.",
      );
      setSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#070B16] text-white flex items-center justify-center p-6">
      <form onSubmit={submit} className="w-full max-w-md rounded-3xl border border-slate-800 bg-[#0B132B] p-7 space-y-4">
        <h1 className="text-2xl font-extrabold">{fr ? "Rejoindre l'entreprise" : "Join the company"}</h1>
        <p className="text-sm text-slate-400">
          {companyName
            ? (fr
              ? `${companyName}${responsibility ? ` · ${responsibility}` : ""}. Vous rejoignez cette entreprise, sans créer un nouvel abonnement.`
              : `${companyName}${responsibility ? ` · ${responsibility}` : ""}. You are joining this company, without a new subscription.`)
            : (fr
              ? "Créez votre accès avec le lien reçu par courriel."
              : "Create your access with the link you received by email.")}
        </p>
        <>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-300">
              {fr ? "Prénom" : "First name"}
              <input required value={firstName} onChange={(event) => setFirstName(event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-2.5 text-sm font-normal normal-case" />
            </label>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-300">
              {fr ? "Nom" : "Last name"}
              <input required value={lastName} onChange={(event) => setLastName(event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-2.5 text-sm font-normal normal-case" />
            </label>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-300">
              {fr ? "Courriel" : "Email"}
              <input required={!token} type="email" value={email} onChange={(event) => setEmail(event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-2.5 text-sm font-normal normal-case" />
            </label>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-300">
              {fr ? "Code du courriel" : "Code from the email"}
              <input required={!token} inputMode="numeric" value={code} onChange={(event) => setCode(event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-2.5 text-sm font-normal normal-case" />
            </label>
            {!token && (
              <p className="text-xs text-amber-200">
                {fr
                  ? "Le lien du courriel est coupé. Entrez le code affiché sous le lien."
                  : "The email link was cut off. Enter the code shown under the link."}
              </p>
            )}
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-300">
              {fr ? "Mot de passe" : "Password"}
              <input required type="password" minLength={10} value={password} onChange={(event) => setPassword(event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-2.5 text-sm font-normal normal-case" />
            </label>
            {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
            <button type="submit" disabled={submitting} className="w-full rounded-xl bg-[#0076FF] px-4 py-3 text-sm font-bold">
              {submitting ? (fr ? "Ouverture..." : "Opening...") : (fr ? "Rejoindre l'entreprise" : "Join the company")}
            </button>
        </>
      </form>
    </main>
  );
}
