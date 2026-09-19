"use client";

import Link from "next/link";
import Image from "next/image";
import { Header } from "@/components/header";
import { useLocale, useTranslations } from "@/lib/i18n/locale-context";
import { BookOpen, Shield, Cpu, Layers, Database, ArrowRight, CheckCircle2, HelpCircle } from "lucide-react";

export default function DocsPage() {
  const { locale } = useLocale();
  const isEn = locale === "en";
  const t = useTranslations();

  const sections = [
    {
      icon: BookOpen,
      title: isEn ? "1. Getting Started & Account Activation" : "1. Démarrage & Activation du compte",
      desc: isEn
        ? "Create your organization space in minutes. Upon registration at /register, you receive a verification link valid for 24 hours. Once verified, your multi-tenant workspace is instantly provisioned."
        : "Créez l'espace de votre organisation en quelques minutes. Dès votre inscription sur /register, un lien d'activation sécurisé valable 24h vous est envoyé. Une fois validé, votre espace multi-tenant est immédiatement provisionné.",
    },
    {
      icon: Layers,
      title: isEn ? "2. Business AI Modules & Capabilities" : "2. Modules métier & Capacités IA",
      desc: isEn
        ? "Avenqo provides modular business agents: Retail AI (order intelligence, stock predictions), CRM AI (lead scoring, customer interactions), Accounting AI (ledger harmonization), Documents/OCR (automated invoice parsing), and Omnichannel Voice."
        : "Avenqo propose des agents métier spécialisés : Retail AI (intelligence de commande, prévisions de stock), CRM AI (scoring de prospects, interactions clients), Accounting AI (préparation comptable), Documents/OCR (extraction automatique de factures), et Voice omnicanal.",
    },
    {
      icon: Database,
      title: isEn ? "3. Connectors & Data Synchronization" : "3. Connecteurs & Synchronisation de données",
      desc: isEn
        ? "Connect your existing e-commerce storefronts (Shopify, WooCommerce, Etsy) or upload CSV, XLSX, JSON datasets directly. All data ingestion is tenant-isolated, cleaned, and standardized automatically."
        : "Reliez vos boutiques e-commerce (Shopify, WooCommerce, Etsy) ou importez directement vos fichiers CSV, XLSX et JSON. Chaque importation est isolée par tenant, nettoyée et normalisée automatiquement.",
    },
    {
      icon: Cpu,
      title: isEn ? "4. AI Credits & Usage Quotas" : "4. Crédits IA & Quotas d'utilisation",
      desc: isEn
        ? "Every subscription tier includes an AI credit allowance (6,500 credits for Demo, 25,000 credits for Professional, custom for Enterprise). Credits power model inference, predictive forecasting, and autonomous workflow actions."
        : "Chaque formule comprend un volume mensuel de crédits IA (6 500 crédits en Demo, 25 000 crédits en Professional, sur mesure en Enterprise). Ces crédits alimentent l'inférence des modèles, les prédictions et les actions automatisées.",
    },
    {
      icon: Shield,
      title: isEn ? "5. Security, Law 25 & Data Isolation" : "5. Sécurité, Loi 25 & Isolation des données",
      desc: isEn
        ? "Avenqo adheres strictly to Quebec Law 25 and PIPEDA standards. Enterprise data is segregated with cryptographic tokens, Argon2 password hashing, and role-based access control (RBAC). Your proprietary data is never used to train global public models."
        : "Avenqo applique une conformité rigoureuse à la Loi 25 québécoise et aux normes LPRPDE canadiennes. Vos données d'entreprise sont cloisonnées avec des jetons cryptographiques, un hachage Argon2 et un contrôle d'accès basé sur les rôles (RBAC). Vos données ne sont jamais utilisées pour entraîner des modèles publics.",
    },
  ];

  return (
    <main className="min-h-screen flex flex-col bg-background text-foreground">
      <Header />

      <section className="section page-shell" style={{ paddingTop: 140, paddingBottom: 80, maxWidth: 1000, margin: "0 auto" }}>
        <div style={{ textAlign: "center", maxWidth: 720, margin: "0 auto 50px" }}>
          <span className="section-kicker">
            {isEn ? "Documentation & Architecture" : "Documentation & Architecture"}
          </span>
          <h1 style={{ fontSize: "clamp(32px, 4vw, 50px)", fontWeight: 800, letterSpacing: "-0.02em", margin: "14px 0" }}>
            {isEn ? "Platform Guide & Standards" : "Guide de la plateforme & Normes"}
          </h1>
          <p style={{ fontSize: "clamp(16px, 1.8vw, 18px)", color: "var(--muted)", lineHeight: 1.6 }}>
            {isEn
              ? "Everything you need to understand, configure, and scale your business operations with Avenqo."
              : "Tout ce qu'il vous faut pour comprendre, configurer et développer les opérations de votre entreprise avec Avenqo."}
          </p>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          {sections.map((sec, idx) => {
            const Icon = sec.icon;
            return (
              <article
                key={idx}
                style={{
                  background: "var(--card-bg, rgba(255,255,255,0.03))",
                  border: "1px solid var(--border)",
                  borderRadius: 16,
                  padding: "28px 32px",
                  display: "flex",
                  gap: 24,
                  alignItems: "flex-start",
                }}
              >
                <div
                  style={{
                    padding: 12,
                    borderRadius: 12,
                    background: "rgba(56, 189, 248, 0.1)",
                    color: "#38bdf8",
                    flexShrink: 0,
                  }}
                >
                  <Icon size={24} />
                </div>
                <div>
                  <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: 8 }}>{sec.title}</h2>
                  <p style={{ color: "var(--muted)", lineHeight: 1.65, fontSize: "0.95rem" }}>{sec.desc}</p>
                </div>
              </article>
            );
          })}
        </div>

        {/* Support Callout */}
        <div
          style={{
            marginTop: 48,
            padding: "32px",
            borderRadius: 16,
            background: "linear-gradient(135deg, rgba(56, 189, 248, 0.08) 0%, rgba(99, 102, 241, 0.08) 100%)",
            border: "1px solid rgba(56, 189, 248, 0.2)",
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 20,
          }}
        >
          <div>
            <h3 style={{ fontSize: "1.15rem", fontWeight: 700, marginBottom: 4 }}>
              {isEn ? "Have a specific integration question?" : "Une question sur une intégration spécifique ?"}
            </h3>
            <p style={{ color: "var(--muted)", fontSize: "0.9rem" }}>
              {isEn
                ? "Our technical support and solutions architects assist you with custom setups."
                : "Notre support technique et nos architectes de solutions vous accompagnent dans vos configurations."}
            </p>
          </div>
          <Link href="/contact" className="button button-primary" style={{ textDecoration: "none" }}>
            {isEn ? "Contact Support" : "Contacter le support"} <ArrowRight size={16} />
          </Link>
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
