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
  const [step, setStep] = useState<"identify" | "password">("identify");
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
    if (!token) return;
    let cancelled = false;
    void apiFetch(`/api/v1/workspace/invitations/preview?token=${encodeURIComponent(token)}`)
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
  }, [token]);

  async function confirmCode(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const response = await apiFetch(
        `/api/v1/workspace/invitations/preview?email=${encodeURIComponent(email.trim())}&code=${encodeURIComponent(code.trim())}`,
      );
      const payload = await response.json();
      if (payload.already_member) {
        throw new ApiRequestError(
          "backend_error",
          409,
          fr
            ? `Ce courriel appartient déjà à ${payload.member_name} dans ${payload.company_name}. Le code ouvre seulement cette entreprise et ne crée pas un autre employé.`
            : `This email already belongs to ${payload.member_name} in ${payload.company_name}. The code only opens that company.`,
        );
      }
      setCompanyName(String(payload.company_name || ""));
      setResponsibility(String(payload.job_title || ""));
      setStep("password");
    } catch (err) {
      setError(
        err instanceof ApiRequestError && err.publicMessage
          ? err.publicMessage
          : fr
            ? "Ce code ne correspond pas à une invitation de cette entreprise."
            : "This code does not match an invitation from this company.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function createAccess(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch("/api/auth/accept-invitation", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", Accept: "application/json", "X-Requested-With": "avenqo-web" },
        body: JSON.stringify({
          email: email.trim(),
          code: code.trim(),
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          password,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = typeof payload?.detail === "string"
          ? payload.detail
          : typeof payload?.error?.message === "string"
            ? payload.error.message
            : "";
        throw new ApiRequestError("backend_error", response.status, detail);
      }
      window.location.assign(typeof payload.home === "string" ? payload.home : "/employees");
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
      <form onSubmit={step === "identify" ? confirmCode : createAccess} className="w-full max-w-md rounded-3xl border border-slate-800 bg-[#0B132B] p-7 space-y-4">
        <h1 className="text-2xl font-extrabold">{fr ? "Rejoindre l'entreprise" : "Join the company"}</h1>
        <p className="text-sm text-slate-400">
          {companyName
            ? (fr
              ? `${companyName}${responsibility ? ` · ${responsibility}` : ""}. Le code ouvre seulement cette entreprise.`
              : `${companyName}${responsibility ? ` · ${responsibility}` : ""}. The code opens only this company.`)
            : (fr
              ? "Entrez votre courriel et le code reçu de votre entreprise."
              : "Enter your email and the code sent by your company.")}
        </p>
        {step === "identify" ? (
          <>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-300">
              {fr ? "Votre courriel" : "Your email"}
              <input required type="email" value={email} onChange={(event) => setEmail(event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-2.5 text-sm font-normal normal-case" />
            </label>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-300">
              {fr ? "Code d'accès de l'entreprise" : "Company access code"}
              <input required inputMode="numeric" value={code} onChange={(event) => setCode(event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-2.5 text-sm font-normal normal-case" />
            </label>
            {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
            <button type="submit" disabled={submitting} className="w-full rounded-xl bg-[#0076FF] px-4 py-3 text-sm font-bold">
              {submitting ? (fr ? "Vérification..." : "Checking...") : (fr ? "Vérifier le code" : "Check the code")}
            </button>
          </>
        ) : (
          <>
            <p className="text-sm text-emerald-300">
              {fr
                ? `${responsibility || "Ce poste"} dans ${companyName}. Choisissez ensuite votre mot de passe. Vous n'aurez que les tâches de ce poste.`
                : `${responsibility || "This role"} at ${companyName}. Then choose your password. You only receive that job's tasks.`}
            </p>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-300">
              {fr ? "Prénom" : "First name"}
              <input required value={firstName} onChange={(event) => setFirstName(event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-2.5 text-sm font-normal normal-case" />
            </label>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-300">
              {fr ? "Nom" : "Last name"}
              <input required value={lastName} onChange={(event) => setLastName(event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-2.5 text-sm font-normal normal-case" />
            </label>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-300">
              {fr ? "Mot de passe" : "Password"}
              <input required type="password" minLength={10} value={password} onChange={(event) => setPassword(event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-2.5 text-sm font-normal normal-case" />
            </label>
            {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
            <button type="submit" disabled={submitting} className="w-full rounded-xl bg-[#0076FF] px-4 py-3 text-sm font-bold">
              {submitting ? (fr ? "Création..." : "Creating...") : (fr ? "Créer mon accès" : "Create my access")}
            </button>
          </>
        )}
      </form>
    </main>
  );
}
