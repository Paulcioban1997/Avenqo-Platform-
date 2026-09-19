"use client";

import Link from "next/link";
import Image from "next/image";
import { ArrowLeft, ArrowRight, CheckCircle2, AlertCircle, LoaderCircle, Mail } from "lucide-react";
import { useSearchParams, useRouter } from "next/navigation";
import { useEffect, useState, FormEvent } from "react";
import { RegionLanguageSelector } from "@/components/region-language-selector";
import { ThemeToggle } from "@/components/theme-toggle";
import { useLocale } from "@/lib/i18n/locale-context";

type StatusState = "loading" | "success" | "error" | "missing_token";

export function VerifyEmailView() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const token = searchParams.get("token")?.trim() || "";

  const { locale } = useLocale();
  const isEn = locale === "en";

  const [status, setStatus] = useState<StatusState>(token ? "loading" : "missing_token");
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [countdown, setCountdown] = useState<number>(5);

  // Resend state
  const [resendEmail, setResendEmail] = useState("");
  const [resendBusy, setResendBusy] = useState(false);
  const [resendDone, setResendDone] = useState(false);
  const [resendError, setResendError] = useState("");

  useEffect(() => {
    if (!token) {
      setStatus("missing_token");
      return;
    }

    let isMounted = true;

    async function executeVerification() {
      try {
        const response = await fetch("/api/auth/verify-email", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
        });

        const data = await response.json().catch(() => ({}));

        if (!isMounted) return;

        if (response.ok) {
          setStatus("success");
        } else {
          setStatus("error");
          const rawDetail = data.detail || data.error?.message || data.message;
          if (rawDetail && typeof rawDetail === "string") {
            // Clean error details
            if (rawDetail.toLowerCase().includes("expir") || rawDetail.toLowerCase().includes("invalide")) {
              setErrorMessage(
                isEn
                  ? "This verification link is invalid, expired, or has already been used."
                  : "Ce lien de vérification est invalide, expiré ou a déjà été utilisé."
              );
            } else {
              setErrorMessage(rawDetail);
            }
          } else {
            setErrorMessage(
              isEn
                ? "This verification link is invalid, expired, or has already been used."
                : "Ce lien de vérification est invalide, expiré ou a déjà été utilisé."
            );
          }
        }
      } catch {
        if (isMounted) {
          setStatus("error");
          setErrorMessage(
            isEn
              ? "A network error occurred. Please check your connection and try again."
              : "Une erreur réseau est survenue. Veuillez vérifier votre connexion et réessayer."
          );
        }
      }
    }

    executeVerification();

    return () => {
      isMounted = false;
    };
  }, [token, isEn]);

  // Countdown auto-redirect on success
  useEffect(() => {
    if (status !== "success") return;

    if (countdown <= 0) {
      router.push("/login");
      return;
    }

    const timer = setTimeout(() => {
      setCountdown((prev) => prev - 1);
    }, 1000);

    return () => clearTimeout(timer);
  }, [status, countdown, router]);

  async function handleResend(e: FormEvent) {
    e.preventDefault();
    if (!resendEmail.trim()) return;

    setResendBusy(true);
    setResendError("");
    setResendDone(false);

    try {
      const response = await fetch("/api/auth/resend-verification", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: resendEmail.trim().toLowerCase() }),
      });

      if (response.ok) {
        setResendDone(true);
      } else {
        const data = await response.json().catch(() => ({}));
        setResendError(
          data.detail ||
            (isEn
              ? "Unable to send verification email. Please try again."
              : "Impossible d'envoyer l'email de vérification. Veuillez réessayer.")
        );
      }
    } catch {
      setResendError(
        isEn
          ? "Network error while requesting verification email."
          : "Erreur réseau lors de la demande d'envoi."
      );
    } finally {
      setResendBusy(false);
    }
  }

  const asideTitle = isEn ? "Activate your workspace." : "Activez votre espace.";
  const asideDesc = isEn
    ? "Verify your corporate email address to unlock full multi-tenant access and enterprise intelligence modules."
    : "Vérifiez votre adresse email professionnelle pour débloquer l'accès complet et vos modules d'intelligence d'affaires.";

  return (
    <div className="auth-layout">
      <aside className="auth-aside">
        <Link href="/" className="auth-back">
          <ArrowLeft size={16} /> {isEn ? "Back to home" : "Retour à l'accueil"}
        </Link>
        <div className="auth-aside-copy">
          <span>{isEn ? "AVENQO WORKSPACE" : "ESPACE AVENQO"}</span>
          <h1>{asideTitle}</h1>
          <p>{asideDesc}</p>
        </div>
        <p className="auth-legal">Une plateforme de PMC Solutions AI</p>
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
            <span>{isEn ? "Account activation" : "Activation de compte"}</span>
            <h2>{isEn ? "Email verification" : "Vérification d'email"}</h2>
            <p>
              {isEn
                ? "Confirming your identity to secure your organizational data."
                : "Confirmation de votre identité pour sécuriser les données de votre organisation."}
            </p>
          </div>

          {status === "loading" && (
            <div className="auth-message" style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <LoaderCircle className="animate-spin text-primary" size={24} />
              <div>
                <p style={{ fontWeight: 600 }}>
                  {isEn ? "Verification in progress..." : "Vérification en cours..."}
                </p>
                <p style={{ fontSize: "0.875rem", opacity: 0.8 }}>
                  {isEn
                    ? "Validating your activation token with the security server."
                    : "Validation de votre jeton d'activation auprès du serveur de sécurité."}
                </p>
              </div>
            </div>
          )}

          {status === "success" && (
            <div className="space-y-6">
              <div className="auth-message success" style={{ display: "flex", alignItems: "flex-start", gap: "12px" }}>
                <CheckCircle2 size={24} className="text-emerald-500 shrink-0 mt-0.5" />
                <div>
                  <p style={{ fontWeight: 600, fontSize: "1.05rem" }}>
                    {isEn ? "Email address successfully verified!" : "Adresse email vérifiée avec succès !"}
                  </p>
                  <p style={{ fontSize: "0.9rem", marginTop: "4px", opacity: 0.85 }}>
                    {isEn
                      ? `Your account is now fully active. Redirecting to login in ${countdown} second${countdown > 1 ? "s" : ""}...`
                      : `Votre compte est maintenant actif. Redirection automatique vers la connexion dans ${countdown} seconde${countdown > 1 ? "s" : ""}...`}
                  </p>
                </div>
              </div>

              <div className="pt-2">
                <Link
                  href="/login"
                  className="auth-submit inline-flex items-center justify-center gap-2 w-full text-center"
                  style={{ textDecoration: "none" }}
                >
                  {isEn ? "Go to login now" : "Se connecter maintenant"} <ArrowRight size={16} />
                </Link>
              </div>
            </div>
          )}

          {(status === "error" || status === "missing_token") && (
            <div className="space-y-6">
              <div className="auth-message error" style={{ display: "flex", alignItems: "flex-start", gap: "12px" }}>
                <AlertCircle size={24} className="text-rose-500 shrink-0 mt-0.5" />
                <div>
                  <p style={{ fontWeight: 600 }}>
                    {status === "missing_token"
                      ? isEn
                        ? "Missing verification token"
                        : "Jeton de vérification manquant"
                      : isEn
                      ? "Verification failed"
                      : "Échec de la vérification"}
                  </p>
                  <p style={{ fontSize: "0.875rem", marginTop: "4px" }}>
                    {errorMessage ||
                      (isEn
                        ? "The link you followed is invalid or has expired. If your email is already verified, you can sign in directly."
                        : "Le lien utilisé est invalide ou a expiré. Si votre adresse a déjà été validée, vous pouvez vous connecter directement.")}
                  </p>
                </div>
              </div>

              {/* Resend verification email option */}
              <div
                style={{
                  border: "1px solid var(--border-subtle, rgba(255,255,255,0.1))",
                  borderRadius: "12px",
                  padding: "16px",
                  background: "var(--card-bg, rgba(255,255,255,0.02))",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px" }}>
                  <Mail size={18} className="text-primary" />
                  <h3 style={{ fontSize: "0.95rem", fontWeight: 600 }}>
                    {isEn ? "Request a new verification link" : "Demander un nouveau lien de vérification"}
                  </h3>
                </div>
                <p style={{ fontSize: "0.85rem", opacity: 0.8, marginBottom: "12px" }}>
                  {isEn
                    ? "Enter your work email address to receive a fresh activation link."
                    : "Entrez votre email professionnel pour recevoir un nouveau lien d'activation."}
                </p>

                {resendDone ? (
                  <div className="auth-message success" style={{ fontSize: "0.875rem", padding: "10px" }}>
                    {isEn
                      ? "If an unverified account exists for this address, a new verification link has been sent."
                      : "Si un compte non vérifié existe pour cette adresse, un nouveau lien vient d'être envoyé."}
                  </div>
                ) : (
                  <form onSubmit={handleResend} style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                    <input
                      type="email"
                      required
                      placeholder={isEn ? "name@company.com" : "nom@entreprise.com"}
                      value={resendEmail}
                      onChange={(e) => setResendEmail(e.target.value)}
                      className="auth-input"
                      style={{
                        padding: "10px 14px",
                        borderRadius: "8px",
                        fontSize: "0.9rem",
                      }}
                    />
                    {resendError && (
                      <p style={{ color: "#f43f5e", fontSize: "0.8rem" }}>{resendError}</p>
                    )}
                    <button
                      type="submit"
                      disabled={resendBusy}
                      className="auth-submit"
                      style={{ padding: "10px 16px", fontSize: "0.9rem" }}
                    >
                      {resendBusy
                        ? isEn
                          ? "Sending..."
                          : "Envoi en cours..."
                        : isEn
                        ? "Send new link"
                        : "Envoyer un nouveau lien"}
                    </button>
                  </form>
                )}
              </div>

              <div className="pt-2 flex flex-col gap-2">
                <Link
                  href="/login"
                  className="auth-submit inline-flex items-center justify-center gap-2 w-full text-center"
                  style={{ textDecoration: "none" }}
                >
                  {isEn ? "Go to login" : "Aller à la connexion"} <ArrowRight size={16} />
                </Link>
                <Link
                  href="/"
                  className="text-center text-sm text-muted-foreground hover:text-foreground pt-2"
                  style={{ textDecoration: "none" }}
                >
                  {isEn ? "Return to homepage" : "Retour à l'accueil"}
                </Link>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
