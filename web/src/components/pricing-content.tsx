"use client";

import Link from "next/link";
import Image from "next/image";
import { motion } from "framer-motion";
import { ArrowRight, Check, ShieldCheck, Zap, Sparkles } from "lucide-react";
import { Header } from "@/components/header";
import { useLocale, useTranslations } from "@/lib/i18n/locale-context";

export function PricingContent() {
  const t = useTranslations();
  const { locale } = useLocale();
  const isFr = locale.startsWith("fr");

  const planMeta = [
    {
      tier: "Base",
      price: "$29.99",
      period: isFr ? "USD / mois" : "USD / month",
      credits: isFr ? "6 500 crédits IA inclus / mois" : "6,500 AI credits included / mo",
      creditExtra: isFr ? "3 modules au choix • Jusqu'à 5 utilisateurs" : "3 modules of choice • Up to 5 users",
      actionHref: "/register?plan=base",
      actionText: isFr ? "Choisir Base" : "Select Base",
      featured: false,
    },
    {
      tier: "Professional",
      price: "$49.99",
      period: isFr ? "USD / mois" : "USD / month",
      credits: isFr ? "25 000 crédits IA inclus / mois" : "25,000 AI credits included / mo",
      creditExtra: isFr ? "Jusqu'à 6 modules • Jusqu'à 25 utilisateurs" : "Up to 6 modules • Up to 25 users",
      actionHref: "/register?plan=professional",
      actionText: isFr ? "Choisir Professional" : "Select Professional",
      featured: true,
    },
    {
      tier: "Enterprise",
      price: isFr ? "Sur mesure" : "Custom quote",
      period: isFr ? "Devis personnalisé" : "Tailored solution",
      credits: isFr ? "Crédits IA sur mesure" : "Custom AI credit volume",
      creditExtra: isFr ? "Tous modules illimités • SLA dédié" : "All unlimited modules • Dedicated SLA",
      actionHref: "/contact",
      actionText: isFr ? "Contacter les ventes" : "Contact sales",
      featured: false,
    },
  ];

  return (
    <main>
      <Header />
      <section className="section pricing-page-hero" style={{ paddingTop: 140, paddingBottom: 60 }}>
        <div className="page-shell" style={{ textAlign: "center", maxWidth: 840, margin: "0 auto" }}>
          <span className="section-kicker">{t.pricing.kicker}</span>
          <h1 style={{ fontSize: "clamp(34px, 4.5vw, 54px)", margin: "14px 0 20px", fontWeight: 700, letterSpacing: "-0.02em" }}>
            {t.pricing.title}
          </h1>
          <p style={{ fontSize: "clamp(16px, 2vw, 19px)", color: "var(--muted)", lineHeight: 1.6, maxWidth: 640, margin: "0 auto 36px" }}>
            {t.pricing.subtitle}
          </p>
          <div style={{ display: "flex", justifyContent: "center", gap: 24, flexWrap: "wrap", fontSize: 14, color: "var(--muted)" }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><Check size={16} color="#38bdf8" /> {t.common.guidedSetup}</span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><Zap size={16} color="#38bdf8" /> Activation immédiate</span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><ShieldCheck size={16} color="#38bdf8" /> {t.common.isolatedData}</span>
          </div>
        </div>
      </section>

      <section className="section" style={{ paddingTop: 0, paddingBottom: 80 }}>
        <div className="page-shell">
          <div className="pricing-grid">
            {t.pricing.plans.map((plan, index) => {
              const meta = planMeta[index] || planMeta[0];
              const isEnterprise = index === 2;

              return (
                <motion.article
                  key={plan.tier}
                  className={`price-card ${meta.featured ? "featured-price" : ""}`}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5, delay: index * 0.1, ease: "easeOut" }}
                  whileHover={{ y: -4 }}
                >
                  {meta.featured && <div className="popular">{t.pricing.popular}</div>}
                  <span>{meta.tier}</span>
                  <h3>{plan.title}</h3>
                  <div style={{ margin: "16px 0 8px" }}>
                    <span style={{ fontSize: 36, fontWeight: 800, color: "var(--foreground)" }}>{meta.price}</span>
                    <span style={{ fontSize: 14, color: "var(--muted)", marginLeft: 6 }}>{meta.period}</span>
                  </div>
                  <div style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 600, padding: "4px 10px", borderRadius: 9999, background: "rgba(56, 189, 248, 0.1)", color: "#38bdf8", marginBottom: 18 }}>
                    <Sparkles size={13} /> {meta.credits}
                  </div>
                  <ul>
                    {plan.items.map((item) => (
                      <li key={item}>
                        <Check size={16} /> {item}
                      </li>
                    ))}
                  </ul>
                  {meta.featured ? (
                    <Link href={meta.actionHref} className="button button-primary" style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6, marginTop: "auto" }}>
                      {meta.actionText} <ArrowRight size={16} />
                    </Link>
                  ) : isEnterprise ? (
                    <a href={meta.actionHref} className="button" style={{ display: "block", textAlign: "center", border: "1px solid var(--border)", marginTop: "auto" }}>
                      {meta.actionText}
                    </a>
                  ) : (
                    <Link href={meta.actionHref} className="button" style={{ display: "block", textAlign: "center", border: "1px solid var(--border)", marginTop: "auto" }}>
                      {meta.actionText}
                    </Link>
                  )}
                </motion.article>
              );
            })}
          </div>

          {/* Credit Packs Section */}
          <div style={{ marginTop: 64, textAlign: "center" }}>
            <span className="section-kicker" style={{ color: "#38bdf8" }}>
              {isFr ? "Recharges flexibles" : "Flexible Top-ups"}
            </span>
            <h2 style={{ fontSize: "clamp(24px, 3vw, 36px)", margin: "10px 0 14px", fontWeight: 700 }}>
              {isFr ? "Packs de crédits IA additionnels" : "Add-on AI Credit Packs"}
            </h2>
            <p style={{ color: "var(--muted)", maxWidth: 580, margin: "0 auto 36px", fontSize: 15 }}>
              {isFr
                ? "Besoin d'un surcroît d'analyses ou d'exécutions d'agents ? Achetez des crédits valables sans expiration."
                : "Need extra analytical capacity or agent executions? Purchase non-expiring credit packs at any time."}
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 20, maxWidth: 960, margin: "0 auto" }}>
              <div style={{ padding: 24, borderRadius: 16, border: "1px solid var(--border)", background: "var(--card-bg, rgba(255,255,255,0.03))", textAlign: "left" }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: "#38bdf8", textTransform: "uppercase", letterSpacing: "0.05em" }}>Starter Pack</span>
                <h4 style={{ fontSize: 20, fontWeight: 700, margin: "8px 0 4px" }}>6 500 {isFr ? "crédits IA" : "AI credits"}</h4>
                <div style={{ fontSize: 28, fontWeight: 800, margin: "12px 0" }}>$10 <span style={{ fontSize: 14, fontWeight: 500, color: "var(--muted)" }}>USD</span></div>
                <p style={{ fontSize: 13, color: "var(--muted)", marginBottom: 16 }}>{isFr ? "Idéal pour compléter un mois actif." : "Great for topping up an active month."}</p>
                <Link href="/billing" className="button" style={{ display: "block", textAlign: "center", border: "1px solid var(--border)", fontSize: 13, padding: "8px 16px" }}>
                  {isFr ? "Recharger" : "Top up"}
                </Link>
              </div>
              <div style={{ padding: 24, borderRadius: 16, border: "1px solid #38bdf8", background: "rgba(56, 189, 248, 0.04)", textAlign: "left", position: "relative" }}>
                <span style={{ position: "absolute", top: -10, right: 20, background: "#38bdf8", color: "#0b1120", fontSize: 11, fontWeight: 700, padding: "2px 10px", borderRadius: 9999 }}>{isFr ? "Populaire" : "Popular"}</span>
                <span style={{ fontSize: 12, fontWeight: 700, color: "#38bdf8", textTransform: "uppercase", letterSpacing: "0.05em" }}>Growth Pack</span>
                <h4 style={{ fontSize: 20, fontWeight: 700, margin: "8px 0 4px" }}>25 000 {isFr ? "crédits IA" : "AI credits"}</h4>
                <div style={{ fontSize: 28, fontWeight: 800, margin: "12px 0" }}>$35 <span style={{ fontSize: 14, fontWeight: 500, color: "var(--muted)" }}>USD</span></div>
                <p style={{ fontSize: 13, color: "var(--muted)", marginBottom: 16 }}>{isFr ? "Pour les campagnes et automatisations intenses." : "For intensive campaigns and workflows."}</p>
                <Link href="/billing" className="button button-primary" style={{ display: "block", textAlign: "center", fontSize: 13, padding: "8px 16px" }}>
                  {isFr ? "Recharger" : "Top up"}
                </Link>
              </div>
              <div style={{ padding: 24, borderRadius: 16, border: "1px solid var(--border)", background: "var(--card-bg, rgba(255,255,255,0.03))", textAlign: "left" }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: "#38bdf8", textTransform: "uppercase", letterSpacing: "0.05em" }}>Scale Pack</span>
                <h4 style={{ fontSize: 20, fontWeight: 700, margin: "8px 0 4px" }}>65 000 {isFr ? "crédits IA" : "AI credits"}</h4>
                <div style={{ fontSize: 28, fontWeight: 800, margin: "12px 0" }}>$80 <span style={{ fontSize: 14, fontWeight: 500, color: "var(--muted)" }}>USD</span></div>
                <p style={{ fontSize: 13, color: "var(--muted)", marginBottom: 16 }}>{isFr ? "Volume maximal avec tarif préférentiel." : "Maximum volume with preferential rate."}</p>
                <Link href="/billing" className="button" style={{ display: "block", textAlign: "center", border: "1px solid var(--border)", fontSize: 13, padding: "8px 16px" }}>
                  {isFr ? "Recharger" : "Top up"}
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="section faq-section" id="faq">
        <div className="page-shell faq-grid">
          <div>
            <span className="section-kicker">{t.faq.kicker}</span>
            <h2>{t.faq.title}</h2>
            <p>{t.faq.subtitle}</p>
            <a href={`mailto:${t.faq.contactCta}`}>
              {t.faq.contactCta} <ArrowRight size={15} />
            </a>
          </div>
          <div className="faq-list">
            {t.faq.items.map(({ question, answer }) => (
              <details key={question}>
                <summary>
                  {question}
                  <span>+</span>
                </summary>
                <p>{answer}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      <section className="final-cta">
        <div className="page-shell final-cta-inner">
          <div>
            <span>{t.finalCta.label}</span>
            <h2>{t.finalCta.title}</h2>
          </div>
          <div>
            <Link className="button white-button" href="/register">
              {t.finalCta.tryFree} <ArrowRight size={17} />
            </Link>
            <Link className="text-link" href="/contact">
              {t.finalCta.scheduleDemo}
            </Link>
          </div>
        </div>
      </section>

      <footer>
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
            <Link href="/#fonctionnement">{isFr ? "Fonctionnement" : "How it works"}</Link>
          </div>
          <div>
            <strong>{t.footer.companyTitle}</strong>
            <Link href="/#entreprise">{t.nav.enterprise}</Link>
            <Link href="/contact">{isFr ? "Contact & Démo" : "Contact & Demo"}</Link>
            <Link href="/#securite">{isFr ? "Sécurité" : "Security"}</Link>
            <Link href="/pricing">{t.nav.pricing}</Link>
          </div>
          <div>
            <strong>{t.footer.resourcesTitle}</strong>
            <Link href="/docs">{t.nav.docs}</Link>
            <Link href="/#faq">FAQ</Link>
            <Link href="/privacy">{isFr ? "Confidentialité" : "Privacy Policy"}</Link>
            <Link href="/terms">{isFr ? "Conditions" : "Terms of Service"}</Link>
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
