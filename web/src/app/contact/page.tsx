"use client";

import { useState, FormEvent } from "react";
import Link from "next/link";
import { Header } from "@/components/header";
import { useLocale, useTranslations } from "@/lib/i18n/locale-context";
import { Mail, Phone, MapPin, CheckCircle2, AlertCircle, ArrowRight, LoaderCircle, Sparkles, Clock, ShieldCheck } from "lucide-react";
import Image from "next/image";

export default function ContactPage() {
  const { locale } = useLocale();
  const isEn = locale === "en";
  const t = useTranslations();

  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState("");

  const [formData, setFormData] = useState({
    name: "",
    email: "",
    company: "",
    phone: "",
    need: isEn ? "Custom Enterprise Demo" : "Démonstration Entreprise sur mesure",
    message: "",
  });

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");

    try {
      const response = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || (isEn ? "Failed to send message." : "Impossible d'envoyer le message."));
      }

      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : (isEn ? "An unexpected error occurred." : "Une erreur est survenue."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen flex flex-col bg-background text-foreground">
      <Header />

      <section className="section page-shell" style={{ paddingTop: 140, paddingBottom: 80, maxWidth: 1100, margin: "0 auto" }}>
        <div style={{ textAlign: "center", maxWidth: 720, margin: "0 auto 50px" }}>
          <span className="section-kicker">
            {isEn ? "Contact & Live Demonstration" : "Contact & Démonstration"}
          </span>
          <h1 style={{ fontSize: "clamp(32px, 4vw, 50px)", fontWeight: 800, letterSpacing: "-0.02em", margin: "14px 0" }}>
            {isEn ? "Let's discuss your enterprise needs." : "Parlons de votre entreprise."}
          </h1>
          <p style={{ fontSize: "clamp(16px, 1.8vw, 18px)", color: "var(--muted)", lineHeight: 1.6 }}>
            {isEn
              ? "Schedule a dedicated demonstration or speak with our solutions architect to build your custom business intelligence suite."
              : "Planifiez une démonstration sur mesure ou échangez avec notre équipe pour configurer la suite d'intelligence adaptée à vos opérations."}
          </p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 40, alignItems: "start" }}>
          {/* Left Column: Direct Info & Value Props */}
          <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
            <div
              style={{
                background: "var(--card-bg, rgba(255,255,255,0.03))",
                border: "1px solid var(--border)",
                borderRadius: 16,
                padding: 32,
              }}
            >
              <h3 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: 20 }}>
                {isEn ? "Direct Coordinates" : "Coordonnées directes"}
              </h3>

              <div style={{ display: "flex", flexDirection: "column", gap: 18, fontSize: "0.95rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{ padding: 10, borderRadius: 10, background: "rgba(56, 189, 248, 0.1)", color: "#38bdf8" }}>
                    <Mail size={18} />
                  </div>
                  <div>
                    <span style={{ fontSize: "0.8rem", color: "var(--muted)", display: "block" }}>Email</span>
                    <a href="mailto:bonjour@avenqo.ca" style={{ color: "var(--foreground)", fontWeight: 600, textDecoration: "none" }}>
                      bonjour@avenqo.ca
                    </a>
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{ padding: 10, borderRadius: 10, background: "rgba(56, 189, 248, 0.1)", color: "#38bdf8" }}>
                    <MapPin size={18} />
                  </div>
                  <div>
                    <span style={{ fontSize: "0.8rem", color: "var(--muted)", display: "block" }}>
                      {isEn ? "Headquarters" : "Siège"}
                    </span>
                    <span style={{ fontWeight: 600 }}>Montréal, QC, Canada</span>
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{ padding: 10, borderRadius: 10, background: "rgba(56, 189, 248, 0.1)", color: "#38bdf8" }}>
                    <Clock size={18} />
                  </div>
                  <div>
                    <span style={{ fontSize: "0.8rem", color: "var(--muted)", display: "block" }}>
                      {isEn ? "Response commitment" : "Engagement de réponse"}
                    </span>
                    <span style={{ fontWeight: 600 }}>
                      {isEn ? "Guaranteed under 24 business hours" : "Garantie sous 24h ouvrées"}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <div
              style={{
                background: "var(--card-bg, rgba(255,255,255,0.03))",
                border: "1px solid var(--border)",
                borderRadius: 16,
                padding: 28,
              }}
            >
              <h4 style={{ fontSize: "1rem", fontWeight: 700, display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
                <ShieldCheck size={20} color="#38bdf8" />
                {isEn ? "Data Security & Compliance" : "Sécurité et conformité"}
              </h4>
              <p style={{ fontSize: "0.88rem", color: "var(--muted)", lineHeight: 1.6 }}>
                {isEn
                  ? "Your data remains strictly confidential, isolated within your dedicated tenant, and hosted in compliance with Quebec Law 25 and PIPEDA standards."
                  : "Vos données restent strictement confidentielles, isolées dans votre espace tenant et hébergées conformément à la Loi 25 québécoise et aux normes fédérales canadiennes."}
              </p>
            </div>
          </div>

          {/* Right Column: Form */}
          <div
            style={{
              background: "var(--card-bg, rgba(255,255,255,0.03))",
              border: "1px solid var(--border)",
              borderRadius: 16,
              padding: 36,
            }}
          >
            {success ? (
              <div style={{ textAlign: "center", padding: "40px 10px" }}>
                <CheckCircle2 size={54} color="#10b981" style={{ margin: "0 auto 16px" }} />
                <h3 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: 12 }}>
                  {isEn ? "Thank you for reaching out!" : "Merci pour votre message !"}
                </h3>
                <p style={{ color: "var(--muted)", fontSize: "0.95rem", lineHeight: 1.6, maxWidth: 420, margin: "0 auto 24px" }}>
                  {isEn
                    ? "Your request has been delivered to our team. A dedicated Avenqo specialist will review your requirements and respond within 24 hours."
                    : "Votre demande a été transmise avec succès à notre équipe. Un spécialiste Avenqo l'analysera et vous recontactera sous 24 heures."}
                </p>
                <Link
                  href="/"
                  className="button button-primary"
                  style={{ display: "inline-flex", alignItems: "center", gap: 8 }}
                >
                  {isEn ? "Back to Homepage" : "Retour à l'accueil"} <ArrowRight size={16} />
                </Link>
              </div>
            ) : (
              <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 18 }}>
                <h3 style={{ fontSize: "1.3rem", fontWeight: 700, marginBottom: 6 }}>
                  {isEn ? "Request a Demo or Enterprise Quote" : "Demander une démo ou un devis"}
                </h3>

                {error && (
                  <div className="auth-message error" style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.9rem" }}>
                    <AlertCircle size={18} /> {error}
                  </div>
                )}

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                  <label className="auth-field">
                    <span style={{ fontSize: "0.85rem", fontWeight: 600 }}>{isEn ? "Full Name *" : "Nom complet *"}</span>
                    <input
                      type="text"
                      required
                      placeholder={isEn ? "Jane Doe" : "Alexandre Tremblay"}
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      style={{ padding: "10px 14px", borderRadius: 8, border: "1px solid var(--border)", background: "transparent", color: "inherit" }}
                    />
                  </label>
                  <label className="auth-field">
                    <span style={{ fontSize: "0.85rem", fontWeight: 600 }}>{isEn ? "Work Email *" : "Email professionnel *"}</span>
                    <input
                      type="email"
                      required
                      placeholder="nom@entreprise.ca"
                      value={formData.email}
                      onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                      style={{ padding: "10px 14px", borderRadius: 8, border: "1px solid var(--border)", background: "transparent", color: "inherit" }}
                    />
                  </label>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                  <label className="auth-field">
                    <span style={{ fontSize: "0.85rem", fontWeight: 600 }}>{isEn ? "Company Name" : "Nom de l'entreprise"}</span>
                    <input
                      type="text"
                      placeholder={isEn ? "Acme Corp" : "Entreprise Inc."}
                      value={formData.company}
                      onChange={(e) => setFormData({ ...formData, company: e.target.value })}
                      style={{ padding: "10px 14px", borderRadius: 8, border: "1px solid var(--border)", background: "transparent", color: "inherit" }}
                    />
                  </label>
                  <label className="auth-field">
                    <span style={{ fontSize: "0.85rem", fontWeight: 600 }}>{isEn ? "Phone (optional)" : "Téléphone (optionnel)"}</span>
                    <input
                      type="tel"
                      placeholder="+1 (514) 000-0000"
                      value={formData.phone}
                      onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                      style={{ padding: "10px 14px", borderRadius: 8, border: "1px solid var(--border)", background: "transparent", color: "inherit" }}
                    />
                  </label>
                </div>

                <label className="auth-field">
                  <span style={{ fontSize: "0.85rem", fontWeight: 600 }}>{isEn ? "Inquiry Objective" : "Type de projet / Besoin"}</span>
                  <select
                    value={formData.need}
                    onChange={(e) => setFormData({ ...formData, need: e.target.value })}
                    style={{ padding: "10px 14px", borderRadius: 8, border: "1px solid var(--border)", background: "var(--background)", color: "inherit" }}
                  >
                    <option>{isEn ? "Live Personalized Demo" : "Démonstration personnalisée"}</option>
                    <option>{isEn ? "Enterprise Custom Contract" : "Devis Entreprise sur mesure"}</option>
                    <option>{isEn ? "Retail Intelligence & E-commerce Sync" : "Retail Intelligence & Connexions E-commerce"}</option>
                    <option>{isEn ? "CRM & Automation Workflow" : "CRM & Automatisation de flux"}</option>
                    <option>{isEn ? "Partnership / Other" : "Partenariat / Autre demande"}</option>
                  </select>
                </label>

                <label className="auth-field">
                  <span style={{ fontSize: "0.85rem", fontWeight: 600 }}>{isEn ? "Message or Priorities *" : "Votre message ou priorités métier *"}</span>
                  <textarea
                    required
                    rows={4}
                    placeholder={
                      isEn
                        ? "Describe your current tools (Shopify, WooCommerce, CRM) and your main automation goals..."
                        : "Décrivez vos outils actuels (Shopify, WooCommerce, ERP, etc.) et vos objectifs clés..."
                    }
                    value={formData.message}
                    onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                    style={{ padding: "10px 14px", borderRadius: 8, border: "1px solid var(--border)", background: "transparent", color: "inherit", resize: "vertical" }}
                  />
                </label>

                <button
                  type="submit"
                  disabled={busy}
                  className="button button-primary"
                  style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, padding: "14px 20px", marginTop: 8 }}
                >
                  {busy ? (
                    <>
                      <LoaderCircle className="animate-spin" size={18} /> {isEn ? "Sending inquiry..." : "Envoi en cours..."}
                    </>
                  ) : (
                    <>
                      {isEn ? "Send inquiry" : "Envoyer ma demande"} <ArrowRight size={17} />
                    </>
                  )}
                </button>

                <p style={{ fontSize: "0.78rem", color: "var(--muted)", textAlign: "center", marginTop: 4 }}>
                  {isEn
                    ? "By submitting, you agree to our Privacy Policy. No spam guaranteed."
                    : "En soumettant ce formulaire, vous acceptez notre politique de confidentialité. Aucun spam."}
                </p>
              </form>
            )}
          </div>
        </div>
      </section>

      {/* Full Footer */}
      <footer style={{ marginTop: "auto" }}>
        <div className="page-shell footer-grid">
          <div className="footer-brand">
            <Image src="/brand/avenqo-logo.png" alt="Avenqo" width={1920} height={864} />
            <p>{t.footer.tagline}</p>
          </div>
          <div>
            <strong>{t.footer.platformTitle}</strong>
            <Link href="/#fonctionnalites">{t.nav.features}</Link>
            <Link href="/#modules">{t.nav.modules}</Link>
            <Link href="/pricing">{t.nav.pricing}</Link>
            <Link href="/#fonctionnement">{isEn ? "How it works" : "Fonctionnement"}</Link>
          </div>
          <div>
            <strong>{t.footer.companyTitle}</strong>
            <Link href="/#entreprise">{t.nav.enterprise}</Link>
            <Link href="/contact">{isEn ? "Contact & Demo" : "Contact & Démo"}</Link>
            <Link href="/#securite">{isEn ? "Security" : "Sécurité"}</Link>
            <Link href="/pricing">{t.nav.pricing}</Link>
          </div>
          <div>
            <strong>{t.footer.resourcesTitle}</strong>
            <Link href="/docs">{t.nav.docs}</Link>
            <Link href="/#faq">FAQ</Link>
            <Link href="/privacy">{isEn ? "Privacy Policy" : "Confidentialité"}</Link>
            <Link href="/terms">{isEn ? "Terms of Service" : "Conditions"}</Link>
          </div>
        </div>
        <div className="page-shell footer-bottom">
          <span>{t.footer.copyright}</span>
          <a href="https://avenqo.ca">avenqo.ca</a>
        </div>
      </footer>
    </main>
  );
}
