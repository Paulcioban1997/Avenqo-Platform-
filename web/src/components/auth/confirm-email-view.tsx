"use client";

import { FormEvent, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ApiRequestError, apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";

export function ConfirmEmailView() {
  const params = useSearchParams();
  const rawToken = params.get("token")?.trim() || "";
  const token = rawToken.length >= 60 ? rawToken : "";
  const { locale } = useLocale();
  const fr = locale.startsWith("fr");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [companyName, setCompanyName] = useState("");
  const [person, setPerson] = useState("");
  const [releaseName, setReleaseName] = useState("");
  const [releaseCompany, setReleaseCompany] = useState("");
  const [replacement, setReplacement] = useState("");

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    void apiFetch(`/api/v1/workspace/email-corrections/preview?token=${encodeURIComponent(token)}`)
      .then(async (response) => {
        const payload = await response.json();
        if (cancelled || !response.ok) return;
        setCompanyName(String(payload.company_name || ""));
        setPerson(`${payload.first_name || ""} ${payload.last_name || ""} · ${payload.job_title || ""}`.trim());
        setReleaseName(String(payload.release_name || ""));
        setReleaseCompany(String(payload.release_company || ""));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function confirm(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const response = await apiFetch("/api/v1/workspace/email-corrections/confirm", {
        method: "POST",
        body: JSON.stringify({
          ...(token ? { token } : { email: email.trim(), code: code.trim() }),
          ...(replacement.trim() ? { replacement_email: replacement.trim() } : {}),
        }),
      });
      const payload = await response.json();
      setDone(
        fr
          ? `${payload.job_title || "Ce poste"} chez ${payload.company_name || "l'entreprise"} utilise maintenant cette adresse. Le compte et les droits sont inchangés. Connectez-vous avec cette adresse et le mot de passe déjà choisi.`
          : `${payload.job_title || "This job"} at ${payload.company_name || "the company"} now uses this address. The account and permissions are unchanged. Sign in with this address and the existing password.`,
      );
    } catch (err) {
      setError(
        err instanceof ApiRequestError && err.publicMessage
          ? err.publicMessage
          : fr
            ? "Cette confirmation ne peut pas être acceptée."
            : "This confirmation cannot be accepted.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#070B16] text-white flex items-center justify-center p-6">
      <form onSubmit={confirm} className="w-full max-w-md rounded-3xl border border-slate-800 bg-[#0B132B] p-7 space-y-4">
        <h1 className="text-2xl font-extrabold">{fr ? "Confirmer l'adresse" : "Confirm the address"}</h1>
        <p className="text-sm text-slate-400">
          {companyName
            ? (fr
              ? `${person} reste dans ${companyName}. Cette confirmation ne déplace aucun autre compte.`
              : `${person} stays at ${companyName}. This confirmation does not move any other account.`)
            : (fr
              ? "Entrez l'adresse et le code reçus. Le poste et les droits restent les mêmes."
              : "Enter the address and the code you received. The job and permissions stay the same.")}
        </p>
        {done ? (
          <p className="text-sm text-emerald-300">{done}</p>
        ) : (
          <>
            {releaseName && (
              <>
                <p className="text-sm text-amber-200">
                  {fr
                    ? `Cette adresse est déjà le compte de ${releaseName}${releaseCompany ? ` chez ${releaseCompany}` : ""}. Les deux entreprises restent séparées. Indiquez l'adresse de remplacement de ce compte.`
                    : `This address is already ${releaseName}${releaseCompany ? ` at ${releaseCompany}` : ""}. The two companies stay separate. Enter the replacement address for that account.`}
                </p>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-300">
                  {fr ? "Adresse de remplacement" : "Replacement address"}
                  <input required type="email" value={replacement} onChange={(event) => setReplacement(event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-2.5 text-sm font-normal normal-case" />
                </label>
              </>
            )}
            {!token && (
              <>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-300">
                  {fr ? "Nouvelle adresse" : "New address"}
                  <input required type="email" value={email} onChange={(event) => setEmail(event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-2.5 text-sm font-normal normal-case" />
                </label>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-300">
                  {fr ? "Code de confirmation" : "Confirmation code"}
                  <input required inputMode="numeric" value={code} onChange={(event) => setCode(event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-2.5 text-sm font-normal normal-case" />
                </label>
              </>
            )}
            {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
            <button type="submit" disabled={submitting} className="w-full rounded-xl bg-[#0076FF] px-4 py-3 text-sm font-bold">
              {submitting ? (fr ? "Confirmation..." : "Confirming...") : (fr ? "Confirmer cette adresse" : "Confirm this address")}
            </button>
          </>
        )}
      </form>
    </main>
  );
}
