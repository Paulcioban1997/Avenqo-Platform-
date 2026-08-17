"use client";

import Link from "next/link";
import Image from "next/image";
import { ArrowLeft, ArrowRight, CheckCircle2, Eye, EyeOff, LoaderCircle } from "lucide-react";
import { FormEvent, useState } from "react";

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
    const payload = isRegister
      ? {
          company_name: form.get("company_name"),
          company_email: form.get("company_email"),
          first_name: form.get("first_name"),
          last_name: form.get("last_name"),
          email: form.get("email"),
          password: form.get("password"),
          country: "Canada",
          timezone: "America/Toronto",
          industry: form.get("industry"),
        }
      : { email: form.get("email"), password: form.get("password") };

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

      if (!isRegister && data.access_token && data.refresh_token) {
        localStorage.setItem("avenqo_access_token", data.access_token);
        localStorage.setItem("avenqo_refresh_token", data.refresh_token);
      }

      setMessage(
        isRegister
          ? data.message || "Compte créé. Vérifiez votre adresse email."
          : `Connexion réussie${data.user?.first_name ? `, ${data.user.first_name}` : ""}.`,
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
        <Link href="/" className="auth-back"><ArrowLeft size={16} /> Retour à l’accueil</Link>
        <div className="auth-aside-copy">
          <span>ESPACE AVENQO</span>
          <h1>{isRegister ? "Votre entreprise, enfin réunie." : "Content de vous revoir."}</h1>
          <p>{isRegister ? "Créez votre espace sécurisé et activez les modules adaptés à vos priorités." : "Retrouvez vos équipes, vos indicateurs et vos prochaines actions."}</p>
        </div>
        <p className="auth-legal">Une plateforme de PMC Solutions AI</p>
      </aside>
      <section className="auth-panel">
        <div className="auth-form-wrap">
          <Link href="/" className="auth-wordmark" aria-label="Avenqo, accueil">
            <Image src="/brand/avenqo-logo.png" alt="Avenqo" width={1920} height={864} priority />
          </Link>
          <div className="auth-heading">
            <span>{isRegister ? "Démarrer avec Avenqo" : "Espace sécurisé"}</span>
            <h2>{isRegister ? "Créer votre organisation" : "Connexion"}</h2>
            <p>{isRegister ? "Configurez votre espace professionnel." : "Accédez à votre espace Avenqo."}</p>
          </div>
          <form onSubmit={submit} className="auth-form">
            {isRegister && (
              <>
                <div className="auth-field-row">
                  <AuthField name="first_name" label="Prénom" autoComplete="given-name" />
                  <AuthField name="last_name" label="Nom" autoComplete="family-name" />
                </div>
                <AuthField name="company_name" label="Organisation" autoComplete="organization" />
                <AuthField name="company_email" label="Email de facturation" type="email" autoComplete="email" />
                <label className="auth-field">
                  <span>Secteur d’activité</span>
                  <select name="industry" defaultValue="Commerce" required>
                    <option>Commerce</option><option>Services professionnels</option><option>Technologie</option><option>Finance</option><option>Immobilier</option><option>Autre</option>
                  </select>
                </label>
              </>
            )}
            <AuthField name="email" label="Email professionnel" type="email" autoComplete="email" />
            <label className="auth-field">
              <span>Mot de passe</span>
              <div className="password-field">
                <input name="password" type={showPassword ? "text" : "password"} autoComplete={isRegister ? "new-password" : "current-password"} minLength={isRegister ? 10 : 1} required />
                <button type="button" onClick={() => setShowPassword((visible) => !visible)} aria-label={showPassword ? "Masquer le mot de passe" : "Afficher le mot de passe"}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button>
              </div>
              {isRegister && <small>10 caractères minimum, avec majuscule, minuscule, chiffre et symbole.</small>}
            </label>
            {message && <div className={`auth-message ${isError ? "error" : "success"}`}><CheckCircle2 size={17} /> {message}</div>}
            <button className="auth-submit" type="submit" disabled={busy}>{busy ? <LoaderCircle className="spin" size={18} /> : <>{isRegister ? "Créer mon espace" : "Se connecter"}<ArrowRight size={17} /></>}</button>
          </form>
          <p className="auth-switch">{isRegister ? "Vous avez déjà un compte ?" : "Nouveau sur Avenqo ?"} <Link href={isRegister ? "/login" : "/register"}>{isRegister ? "Se connecter" : "Créer une organisation"}</Link></p>
        </div>
      </section>
    </div>
  );
}

function AuthField({ name, label, type = "text", autoComplete }: { name: string; label: string; type?: string; autoComplete?: string }) {
  return <label className="auth-field"><span>{label}</span><input name={name} type={type} autoComplete={autoComplete} required /></label>;
}
