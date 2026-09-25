"use client";

import Link from "next/link";
import Image from "next/image";
import { ArrowLeft, ArrowRight, CheckCircle2, Eye, EyeOff, LoaderCircle, AlertCircle } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { RegionLanguageSelector } from "./region-language-selector";
import { ThemeToggle } from "./theme-toggle";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAuthStrings } from "@/lib/i18n/auth-dictionary";

export type AuthMode = "login" | "register" | "forgot-password" | "reset-password";

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

function isPasswordStrong(pw: string): boolean {
  if (pw.length < 10) return false;
  const hasUpper = /[A-Z]/.test(pw);
  const hasLower = /[a-z]/.test(pw);
  const hasDigit = /[0-9]/.test(pw);
  const hasSymbol = /[^A-Za-z0-9]/.test(pw);
  return hasUpper && hasLower && hasDigit && hasSymbol;
}

export function AuthForm({ mode }: { mode: AuthMode }) {
  const isRegister = mode === "register";
  const isForgot = mode === "forgot-password";
  const isReset = mode === "reset-password";
  const isLogin = mode === "login";

  const [tokenFromUrl, setTokenFromUrl] = useState("");
  useEffect(() => {
    if (typeof window !== "undefined") {
      const t = new URLSearchParams(window.location.search).get("token") || "";
      setTokenFromUrl(t);
    }
  }, []);

  const { locale } = useLocale();
  const s = getAuthStrings(locale);

  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string>();
  const [isError, setIsError] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage(undefined);
    setIsError(false);

    const form = new FormData(event.currentTarget);
    const email = (form.get("email")?.toString() || "").trim().toLowerCase();
    const password = form.get("password")?.toString() || "";
    const confirmPassword = form.get("confirm_password")?.toString() || "";

    if (isReset) {
      if (!tokenFromUrl) {
        setIsError(true);
        setMessage(s.missingToken);
        setBusy(false);
        return;
      }
      if (password !== confirmPassword) {
        setIsError(true);
        setMessage(s.passwordsDoNotMatch);
        setBusy(false);
        return;
      }
      if (!isPasswordStrong(password)) {
        setIsError(true);
        setMessage(s.passwordTooWeak);
        setBusy(false);
        return;
      }
    }

    let payload: Record<string, unknown>;
    if (isRegister) {
      payload = {
        company_name: form.get("company_name"),
        company_email: form.get("company_email") || email,
        first_name: form.get("first_name"),
        last_name: form.get("last_name"),
        email: email,
        password: password,
        country: form.get("country") || "Canada",
        timezone: "America/Toronto",
        industry: form.get("industry") || "Commerce",
        currency_code: form.get("currency_code") || "CAD",
        company_size: form.get("company_size") || "1-10",
        billing_email: form.get("company_email") || email,
        plan_code: form.get("plan_code") || "base",
      };
    } else if (isForgot) {
      payload = { email: email };
    } else if (isReset) {
      payload = { token: tokenFromUrl, new_password: password };
    } else {
      payload = { email: email, password: password };
    }

    try {
      const endpoint = isForgot
        ? "/api/auth/forgot-password"
        : isReset
        ? "/api/auth/reset-password"
        : `/api/auth/${mode}`;

      const response = await fetch(endpoint, {
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

        let errorMsg = detail || errorDetails || data.error?.message || data.message;
        if (typeof errorMsg === "string") {
          // Remove Pydantic "Value error, " prefix
          errorMsg = errorMsg.replace(/^Value error,\s*/i, "").trim();
          // Fix UTF-8 mojibake
          errorMsg = errorMsg
            .replace(/caractÃ¨re spÃ©cial/g, "caractère spécial")
            .replace(/vÃ©rifiÃ©e/g, "vérifiée")
            .replace(/Ã©/g, "é")
            .replace(/Ã¨/g, "è")
            .replace(/Ã /g, "à");

          const lower = errorMsg.toLowerCase();
          if (lower.includes("mot de passe") && (lower.includes("minuscule") || lower.includes("caractère") || lower.includes("special"))) {
            errorMsg = locale === "en"
              ? "The password must contain at least one lowercase letter, one uppercase letter, one digit, and one special character."
              : "Le mot de passe doit contenir au moins une lettre minuscule, une lettre majuscule, un chiffre et un caractère spécial.";
          }
        }
        if (isReset && response.status === 400) {
          errorMsg = s.linkInvalid || s.linkExpired || errorMsg;
        }
        throw new Error(errorMsg || s.genericError);
      }

      if (typeof window !== "undefined" && isLogin) {
        if (data.access_token) {
          localStorage.setItem("avenqo_token", data.access_token);
          localStorage.setItem("avenqo_access_token", data.access_token);
        }
        if (data.refresh_token) {
          localStorage.setItem("avenqo_refresh_token", data.refresh_token);
        }
      }

      if (isLogin) {
        window.location.href = "/dashboard";
        return;
      }

      setIsSuccess(true);
      if (isForgot) {
        setMessage(s.forgotPasswordSuccess);
      } else if (isReset) {
        setMessage(s.resetSuccess);
      } else if (isRegister) {
        setMessage(
          data.message ||
            (locale === "en"
              ? "Your workspace has been created! Please check your email to activate your account."
              : "Votre espace a été créé avec succès ! Veuillez vérifier votre boîte de réception pour activer votre compte.")
        );
      }
    } catch (error) {
      setIsError(true);
      setMessage(error instanceof Error ? error.message : s.genericError);
    } finally {
      setBusy(false);
    }
  }

  // Titles & Descriptors
  const asideTitle = isRegister
    ? s.asideRegisterTitle
    : isForgot
    ? s.asideForgotTitle
    : isReset
    ? s.asideResetTitle
    : s.asideLoginTitle;

  const asideDesc = isRegister
    ? s.asideRegisterDesc
    : isForgot
    ? s.asideForgotDesc
    : isReset
    ? s.asideResetDesc
    : s.asideLoginDesc;

  const badgeText = isRegister
    ? s.badgeRegister
    : isForgot
    ? s.badgeForgot
    : isReset
    ? s.badgeReset
    : s.badgeLogin;

  const headingText = isRegister
    ? s.headingRegister
    : isForgot
    ? s.headingForgot
    : isReset
    ? s.headingReset
    : s.headingLogin;

  const subheadingText = isRegister
    ? s.subheadingRegister
    : isForgot
    ? s.subheadingForgot
    : isReset
    ? s.subheadingReset
    : s.subheadingLogin;

  return (
    <div className="auth-layout">
      <aside className="auth-aside">
        <Link href="/" className="auth-back">
          <ArrowLeft size={16} /> {s.backToHome}
        </Link>
        <div className="auth-aside-copy">
          <span>{s.workspace}</span>
          <h1>{asideTitle}</h1>
          <p>{asideDesc}</p>
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
            <span>{badgeText}</span>
            <h2>{headingText}</h2>
            <p>{subheadingText}</p>
          </div>

          {isReset && !tokenFromUrl && !isSuccess && (
            <div className="auth-message error">
              <AlertCircle size={18} />
              <div>
                <p>{s.missingToken}</p>
                <Link href="/forgot-password" className="auth-forgot-link" style={{ marginTop: 8, display: "inline-block" }}>
                  {s.forgotPasswordTitle}
                </Link>
              </div>
            </div>
          )}

          {(!isReset || tokenFromUrl || isSuccess) && (
            <form onSubmit={submit} className="auth-form">
              {isRegister && (
                <>
                  <div className="auth-field-row">
                    <AuthField name="first_name" label={s.firstName} autoComplete="given-name" />
                    <AuthField name="last_name" label={s.lastName} autoComplete="family-name" />
                  </div>
                  <AuthField
                    name="company_name"
                    label={locale === "en" ? "Workspace / Organization" : "Nom de l'espace / Organisation"}
                    autoComplete="organization"
                    placeholder="Acme Inc."
                  />
                  <div className="auth-field-row">
                    <label className="auth-field">
                      <span>{s.industry}</span>
                      <select name="industry" defaultValue="Commerce" required>
                        <option value="Commerce">{locale === "en" ? "Commerce / Retail" : "Commerce / Détail"}</option>
                        <option value="Services professionnels">{locale === "en" ? "Professional Services" : "Services professionnels"}</option>
                        <option value="Technologie">{locale === "en" ? "Technology / SaaS" : "Technologie / SaaS"}</option>
                        <option value="Automobile">{locale === "en" ? "Automotive / Garage" : "Automobile / Garage"}</option>
                        <option value="Santé">{locale === "en" ? "Healthcare / Clinic" : "Santé / Clinique"}</option>
                        <option value="Finance">{locale === "en" ? "Finance / Accounting" : "Finance / Comptabilité"}</option>
                        <option value="Immobilier">{locale === "en" ? "Real Estate" : "Immobilier"}</option>
                        <option value="Autre">{locale === "en" ? "Other" : "Autre"}</option>
                      </select>
                    </label>
                    <label className="auth-field">
                      <span>{locale === "en" ? "Team size" : "Taille de l'équipe"}</span>
                      <select name="company_size" defaultValue="1-10" required>
                        <option value="1-10">1-10 {locale === "en" ? "employees" : "employés"}</option>
                        <option value="11-50">11-50 {locale === "en" ? "employees" : "employés"}</option>
                        <option value="51-200">51-200 {locale === "en" ? "employees" : "employés"}</option>
                        <option value="201+">201+ {locale === "en" ? "employees" : "employés"}</option>
                      </select>
                    </label>
                  </div>
                  <div className="auth-field-row">
                    <label className="auth-field">
                      <span>{locale === "en" ? "Country" : "Pays"}</span>
                      <select name="country" defaultValue="Canada" required>
                        <option value="Canada">Canada</option>
                        <option value="France">France</option>
                        <option value="États-Unis">{locale === "en" ? "United States" : "États-Unis"}</option>
                        <option value="Belgique">{locale === "en" ? "Belgium" : "Belgique"}</option>
                        <option value="Suisse">{locale === "en" ? "Switzerland" : "Suisse"}</option>
                        <option value="Autre">{locale === "en" ? "Other" : "Autre"}</option>
                      </select>
                    </label>
                    <label className="auth-field">
                      <span>{locale === "en" ? "Currency" : "Devise"}</span>
                      <select name="currency_code" defaultValue="CAD" required>
                        <option value="CAD">CAD ($ CA)</option>
                        <option value="USD">USD ($ US)</option>
                        <option value="EUR">EUR (€)</option>
                      </select>
                    </label>
                  </div>
                  <div className="auth-field-row">
                    <AuthField name="company_email" label={s.billingEmail} type="email" autoComplete="email" placeholder="facturation@entreprise.ca" />
                    <label className="auth-field">
                      <span>{locale === "en" ? "Formula / Plan" : "Formule d'abonnement"}</span>
                      <select name="plan_code" defaultValue="base" required>
                        <option value="base">{locale === "en" ? "Base ($29.99/mo - 6,500 credits)" : "Base (29.99 $/mois - 6 500 crédits)"}</option>
                        <option value="professional">{locale === "en" ? "Professional ($49.99/mo - 25,000 credits)" : "Professional (49.99 $/mois - 25 000 crédits)"}</option>
                      </select>
                    </label>
                  </div>
                </>
              )}

              {!isReset && (
                <AuthField
                  name="email"
                  label={isForgot ? s.emailAddress : s.email}
                  type="email"
                  autoComplete="email"
                  placeholder="nom@entreprise.ca"
                />
              )}

              {(isLogin || isRegister) && (
                <label className="auth-field">
                  <div className="auth-field-header">
                    <span>{s.password}</span>
                    {isLogin && (
                      <Link
                        href="/forgot-password"
                        className="auth-forgot-link"
                        tabIndex={0}
                        aria-label={s.forgotPasswordLink}
                      >
                        {s.forgotPasswordLink}
                      </Link>
                    )}
                  </div>
                  <div className="password-field">
                    <input
                      name="password"
                      type={showPassword ? "text" : "password"}
                      autoComplete={isRegister ? "new-password" : "current-password"}
                      minLength={isRegister ? 10 : 1}
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((visible) => !visible)}
                      aria-label={showPassword ? "Masquer le mot de passe" : "Afficher le mot de passe"}
                    >
                      {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                    </button>
                  </div>
                  {isRegister && <small>{s.passwordHint}</small>}
                </label>
              )}

              {isReset && !isSuccess && (
                <>
                  <label className="auth-field">
                    <span>{s.newPassword}</span>
                    <div className="password-field">
                      <input
                        name="password"
                        type={showPassword ? "text" : "password"}
                        autoComplete="new-password"
                        minLength={10}
                        required
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword((visible) => !visible)}
                        aria-label={showPassword ? "Masquer le mot de passe" : "Afficher le mot de passe"}
                      >
                        {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                      </button>
                    </div>
                    <small>{s.passwordHint}</small>
                  </label>

                  <label className="auth-field">
                    <span>{s.confirmPassword}</span>
                    <div className="password-field">
                      <input
                        name="confirm_password"
                        type={showConfirmPassword ? "text" : "password"}
                        autoComplete="new-password"
                        minLength={10}
                        required
                      />
                      <button
                        type="button"
                        onClick={() => setShowConfirmPassword((visible) => !visible)}
                        aria-label={showConfirmPassword ? "Masquer le mot de passe" : "Afficher le mot de passe"}
                      >
                        {showConfirmPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                      </button>
                    </div>
                  </label>
                </>
              )}

              {message && (
                <div className={`auth-message ${isError ? "error" : "success"}`} role="status">
                  {isError ? <AlertCircle size={18} /> : <CheckCircle2 size={18} />}
                  <span>{message}</span>
                </div>
              )}

              {isSuccess && (isReset || isRegister) && (
                <Link
                  href="/login"
                  className="auth-submit"
                  style={{ textDecoration: "none" }}
                >
                  {s.loginSubmit} <ArrowRight size={17} />
                </Link>
              )}

              {(!isSuccess || isLogin) && (
                <button className="auth-submit" type="submit" disabled={busy}>
                  {busy ? (
                    <LoaderCircle className="spin" size={18} />
                  ) : (
                    <>
                      {isRegister
                        ? s.registerSubmit
                        : isForgot
                        ? s.sendResetLink
                        : isReset
                        ? s.resetSubmit
                        : s.loginSubmit}
                      <ArrowRight size={17} />
                    </>
                  )}
                </button>
              )}
            </form>
          )}

          <div className="auth-switch">
            {isLogin && (
              <p>
                {s.newToAvenqoPrompt} <Link href="/register">{s.createOrgLink}</Link>
              </p>
            )}
            {isRegister && (
              <p>
                {s.hasAccountPrompt} <Link href="/login">{s.signInLink}</Link>
              </p>
            )}
            {(isForgot || isReset) && (
              <p>
                <Link href="/login" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <ArrowLeft size={15} /> {s.backToLogin}
                </Link>
              </p>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

function AuthField({
  name,
  label,
  type = "text",
  autoComplete,
  placeholder,
}: {
  name: string;
  label: string;
  type?: string;
  autoComplete?: string;
  placeholder?: string;
}) {
  return (
    <label className="auth-field">
      <span>{label}</span>
      <input name={name} type={type} autoComplete={autoComplete} placeholder={placeholder} required />
    </label>
  );
}
