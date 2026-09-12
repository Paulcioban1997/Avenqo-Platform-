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
        country: "Canada",
        timezone: "America/Toronto",
        industry: form.get("industry") || "Commerce",
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
        if (isReset && response.status === 400) {
          errorMsg = s.linkInvalid || s.linkExpired || errorMsg;
        }
        throw new Error(errorMsg || s.genericError);
      }

      if (typeof window !== "undefined" && isLogin) {
        localStorage.removeItem("avenqo_access_token");
        localStorage.removeItem("avenqo_refresh_token");
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
        setMessage(data.message || "Compte créé. Vérifiez votre adresse email.");
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
                  <AuthField name="company_name" label={s.organization} autoComplete="organization" />
                  <AuthField name="company_email" label={s.billingEmail} type="email" autoComplete="email" />
                  <label className="auth-field">
                    <span>{s.industry}</span>
                    <select name="industry" defaultValue="Commerce" required>
                      <option>Commerce</option>
                      <option>Services professionnels</option>
                      <option>Technologie</option>
                      <option>Finance</option>
                      <option>Immobilier</option>
                      <option>Autre</option>
                    </select>
                  </label>
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

              {isSuccess && isReset && (
                <Link
                  href="/login"
                  className="auth-submit"
                  style={{ textDecoration: "none" }}
                >
                  {s.loginSubmit} <ArrowRight size={17} />
                </Link>
              )}

              {(!isSuccess || isLogin || isRegister) && (
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
