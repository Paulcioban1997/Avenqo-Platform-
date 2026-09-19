"use client";

import Link from "next/link";
import Image from "next/image";
import { Header } from "@/components/header";
import { useLocale, useTranslations } from "@/lib/i18n/locale-context";
import { ArrowRight, Check, Sparkles, Shield, ArrowLeft, BarChart3 } from "lucide-react";

type ModuleData = {
  nameFr: string;
  nameEn: string;
  taglineFr: string;
  taglineEn: string;
  descriptionFr: string;
  descriptionEn: string;
  featuresFr: string[];
  featuresEn: string[];
  metricsFr: { label: string; value: string }[];
  metricsEn: { label: string; value: string }[];
  dashboardRoute: string;
};

export function ModuleDetailView({ slug, data }: { slug: string; data: ModuleData }) {
  const { locale } = useLocale();
  const isEn = locale === "en";
  const t = useTranslations();

  const name = isEn ? data.nameEn : data.nameFr;
  const tagline = isEn ? data.taglineEn : data.taglineFr;
  const description = isEn ? data.descriptionEn : data.descriptionFr;
  const features = isEn ? data.featuresEn : data.featuresFr;
  const metrics = isEn ? data.metricsEn : data.metricsFr;

  return (
    <main className="min-h-screen flex flex-col bg-background text-foreground">
      <Header />

      <section className="section page-shell" style={{ paddingTop: 140, paddingBottom: 80, maxWidth: 1060, margin: "0 auto" }}>
        <Link
          href="/#modules"
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-8"
          style={{ textDecoration: "none" }}
        >
          <ArrowLeft size={16} /> {isEn ? "Back to all modules" : "Retour aux modules Avenqo"}
        </Link>

        <div style={{ textAlign: "center", maxWidth: 800, margin: "0 auto 50px" }}>
          <span className="section-kicker">
            {isEn ? `Module • ${slug.toUpperCase()}` : `Module • ${slug.toUpperCase()}`}
          </span>
          <h1 style={{ fontSize: "clamp(34px, 4.5vw, 54px)", fontWeight: 800, letterSpacing: "-0.02em", margin: "14px 0" }}>
            {name}
          </h1>
          <p style={{ fontSize: "clamp(18px, 2.2vw, 22px)", color: "var(--foreground)", fontWeight: 600, marginBottom: 16 }}>
            {tagline}
          </p>
          <p style={{ fontSize: "clamp(15px, 1.8vw, 17px)", color: "var(--muted)", lineHeight: 1.7, maxWidth: 680, margin: "0 auto" }}>
            {description}
          </p>

          <div style={{ display: "flex", justifyContent: "center", gap: 14, flexWrap: "wrap", marginTop: 32 }}>
            <Link
              href={`/register?plan=professional&module=${slug}`}
              className="button button-primary"
              style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "12px 24px" }}
            >
              {isEn ? "Activate with Professional" : "Activer ce module"} <ArrowRight size={16} />
            </Link>
            <Link
              href="/contact"
              className="button button-secondary"
              style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "12px 24px" }}
            >
              {isEn ? "Book a Demo" : "Demander une démo"}
            </Link>
          </div>
        </div>

        {/* Metrics Grid */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 20, marginBottom: 50 }}>
          {metrics.map((m, i) => (
            <div
              key={i}
              style={{
                background: "var(--card-bg, rgba(255,255,255,0.03))",
                border: "1px solid var(--border)",
                borderRadius: 16,
                padding: "24px",
                textAlign: "center",
              }}
            >
              <span style={{ fontSize: "2.4rem", fontWeight: 800, color: "#38bdf8", display: "block", marginBottom: 6 }}>
                {m.value}
              </span>
              <span style={{ fontSize: "0.9rem", color: "var(--muted)", fontWeight: 500 }}>
                {m.label}
              </span>
            </div>
          ))}
        </div>

        {/* Features List */}
        <div
          style={{
            background: "var(--card-bg, rgba(255,255,255,0.03))",
            border: "1px solid var(--border)",
            borderRadius: 20,
            padding: "36px 40px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 24 }}>
            <Sparkles size={22} color="#38bdf8" />
            <h2 style={{ fontSize: "1.4rem", fontWeight: 700 }}>
              {isEn ? "Core Capabilities & Automation" : "Capacités clés & Automatisation"}
            </h2>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 20 }}>
            {features.map((feat, index) => (
              <div
                key={index}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 12,
                  padding: "16px",
                  borderRadius: 12,
                  background: "rgba(255, 255, 255, 0.02)",
                  border: "1px solid rgba(255, 255, 255, 0.05)",
                }}
              >
                <div style={{ padding: 4, borderRadius: 8, background: "rgba(56, 189, 248, 0.1)", color: "#38bdf8", flexShrink: 0 }}>
                  <Check size={16} />
                </div>
                <span style={{ fontSize: "0.95rem", lineHeight: 1.5 }}>{feat}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
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
