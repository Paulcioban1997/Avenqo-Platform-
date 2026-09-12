"use client";

import Link from "next/link";
import Image from "next/image";
import { ArrowLeft, ArrowRight, CheckCircle2, Eye, EyeOff, LoaderCircle } from "lucide-react";
import { FormEvent, useState } from "react";
import { RegionLanguageSelector } from "./region-language-selector";
import { ThemeToggle } from "./theme-toggle";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAuthStrings } from "@/lib/i18n/auth-dictionary";

type AuthMode = "login" | "register";
type ApiPayload = {
  message?: string;
  detail?: string | Array<{ msg?: string }>;
  error?: {
    message?: string;
    details?: Array<{ msg?: string }>;
  };
  access_token?: string;
  refresh_token?: string;
  user?: { first_name?: string };
};

export function AuthForm({ mode }: { mode: AuthMode }) {
  const isRegister = mode === "register";
  const { locale } = useLocale();
  const s = getAuthStrings(locale);

  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string>();
  const [isError, setIsError] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage(undefined);
    setIsError(false);

    const form = new FormData(event.currentTarget);
    const email = form.get("email")?.toString() || "";
    const payload = isRegister
      ? {
          company_name: form.get("company_name"),
          company_email: form.get("company_email") || email,
          first_name: form.get("first_name"),
          last_name: form.get("last_name"),
          email: email,
          password: form.get("password"),
          country: "Canada",
          timezone: "America/Toronto",
          industry: form.get("industry") || "Commerce",
        }
      : { email: email, password: form.get("password") };

    try {
      const response = await fetch(`/api/auth/${mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = (await response.json()) as ApiPayload;

      if (!response.ok) {
        const detail = Array.isArray(data.detail)
          ? data.detail.map((item) => item.msg).filter(Boolean).join(" ")
          : data.detail;
        const errorDetails = data.error?.details
          ?.map((item) => item.msg)
          .filter(Boolean)
          .join(" ");
        throw new Error(
          detail || errorDetails || data.error?.message || data.message || "Une erreur est survenue.",
        );
      }

      if (typeof window !== "undefined") {
        localStorage.removeItem("avenqo_access_token");
        localStorage.removeItem("avenqo_refresh_token");
      }

      if (!isRegister) {
        window.location.href = "/dashboard";
        return;
      }

      setMessage(
        data.message || "Compte créé. Vérifiez votre adresse email.",
      );
    } catch (error) {
      setIsError(true);
      setMessage(error instanceof Error ? error.message : "Le service est indisponible.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-layout">
      <aside className="auth-aside">
        <Link href="/" className="auth-back"><ArrowLeft size={16} /> {s.backToHome}</Link>
        <div className="auth-aside-copy">
          <span>{s.workspace}</span>
          <h1>{isRegister ? s.asideRegisterTitle : s.asideLoginTitle}</h1>
          <p>{isRegister ? s.asideRegisterDesc : s.asideLoginDesc}</p>
        </div>
        <p className="auth-legal">{s.legal}</p>
      </aside>
      <section className="auth-panel">
        <div className="auth-top-controls" data-testid="auth-top-controls">
          <RegionLanguageSelector />
          <ThemeToggle />
        </div>
        <div className="auth-form-wrap">
          <Link href="/" className="auth-wordmark" aria-label="Avenqo, accueil">
            <Image src="/brand/avenqo-logo.png" alt="Avenqo" width={1920} height={864} priority />
          </Link>
          <div className="auth-heading">
            <span>{isRegister ? s.badgeRegister : s.badgeLogin}</span>
            <h2>{isRegister ? s.headingRegister : s.headingLogin}</h2>
            <p>{isRegister ? s.subheadingRegister : s.subheadingLogin}</p>
          </div>
          <form onSubmit={submit} className="auth-form">
            {isRegister && (
              <>
                <div className="auth-field-row">
                  <AuthField name="first_name" label={s.firstName} autoComplete="given-name" />
                  <AuthField name="last_name" label={s.lastName} autoComplete="family-name" />
                </div>
                <AuthField name="company_name" label={s.organization} autoComplete="organization" />
                <AuthField name="company_email" label={s.billingEmail} type="email" autoComplete="email" />
                <label className="auth-field">
                  <span>{s.industry}</span>
                  <select name="industry" defaultValue="Commerce" required>
                    <option>Commerce</option><option>Services professionnels</option><option>Technologie</option><option>Finance</option><option>Immobilier</option><option>Autre</option>
                  </select>
                </label>
              </>
            )}
            <AuthField name="email" label={s.email} type="email" autoComplete="email" />
            <label className="auth-field">
              <span>{s.password}</span>
              <div className="password-field">
                <input name="password" type={showPassword ? "text" : "password"} autoComplete={isRegister ? "new-password" : "current-password"} minLength={isRegister ? 10 : 1} required />
                <button type="button" onClick={() => setShowPassword((visible) => !visible)} aria-label={showPassword ? "Masquer le mot de passe" : "Afficher le mot de passe"}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button>
              </div>
              {isRegister && <small>{s.passwordHint}</small>}
            </label>
            {message && <div className={`auth-message ${isError ? "error" : "success"}`}><CheckCircle2 size={17} /> {message}</div>}
            <button className="auth-submit" type="submit" disabled={busy}>{busy ? <LoaderCircle className="spin" size={18} /> : <>{isRegister ? s.registerSubmit : s.loginSubmit}<ArrowRight size={17} /></>}</button>
          </form>
          <p className="auth-switch">{isRegister ? s.hasAccountPrompt : s.newToAvenqoPrompt} <Link href={isRegister ? "/login" : "/register"}>{isRegister ? s.signInLink : s.createOrgLink}</Link></p>
        </div>
      </section>
    </div>
  );
}

function AuthField({ name, label, type = "text", autoComplete }: { name: string; label: string; type?: string; autoComplete?: string }) {
  return <label className="auth-field"><span>{label}</span><input name={name} type={type} autoComplete={autoComplete} required /></label>;
}
