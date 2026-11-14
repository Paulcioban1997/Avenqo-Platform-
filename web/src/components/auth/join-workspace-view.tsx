"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ApiRequestError, apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";

export function JoinWorkspaceView() {
  const params = useSearchParams();
  const token = params.get("token")?.trim() || "";
  const { locale } = useLocale();
  const fr = locale.startsWith("fr");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const response = await apiFetch("/api/v1/workspace/invitations/accept", {
        method: "POST",
        body: JSON.stringify({
          token: token || undefined,
          email: token ? undefined : email.trim(),
          code: token ? undefined : code.trim(),
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          password,
        }),
      });
      if (!response.ok) return;
      setDone(true);
    } catch (err) {
      setError(
        err instanceof ApiRequestError && err.publicMessage
          ? err.publicMessage
          : fr
            ? "Cette invitation ne peut pas être acceptée."
            : "This invitation cannot be accepted.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#070B16] text-white flex items-center justify-center p-6">
      <form onSubmit={submit} className="w-full max-w-md rounded-3xl border border-slate-800 bg-[#0B132B] p-7 space-y-4">
        <h1 className="text-2xl font-extrabold">{fr ? "Rejoindre l'entreprise" : "Join the company"}</h1>
        <p className="text-sm text-slate-400">
          {fr
            ? "Créez votre accès avec le lien reçu par courriel."
            : "Create your access with the link you received by email."}
        </p>
        {done ? (
          <p className="text-sm text-emerald-300">
            {fr ? "Votre accès est créé. " : "Your access is ready. "}
            <Link href="/login" className="underline">{fr ? "Se connecter" : "Sign in"}</Link>
          </p>
        ) : (
          <>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-300">
              {fr ? "Prénom" : "First name"}
              <input required value={firstName} onChange={(event) => setFirstName(event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-2.5 text-sm font-normal normal-case" />
            </label>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-300">
              {fr ? "Nom" : "Last name"}
              <input required value={lastName} onChange={(event) => setLastName(event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-2.5 text-sm font-normal normal-case" />
            </label>
            {!token && (
              <>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-300">
                  {fr ? "Courriel" : "Email"}
                  <input required type="email" value={email} onChange={(event) => setEmail(event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-2.5 text-sm font-normal normal-case" />
                </label>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-300">
                  {fr ? "Code reçu par courriel" : "Code from the email"}
                  <input required inputMode="numeric" value={code} onChange={(event) => setCode(event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-2.5 text-sm font-normal normal-case" />
                </label>
              </>
            )}
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
