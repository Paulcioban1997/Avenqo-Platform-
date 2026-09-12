"use client";

import Link from "next/link";
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
      tier: "Demo",
      price: "$28",
      period: isFr ? "USD / mois" : "USD / month",
      credits: isFr ? "6 500 crédits IA inclus / mois" : "6,500 AI credits included / mo",
      creditExtra: isFr ? "Supplément : +6 500 crédits pour 10 USD" : "Add-on: +6,500 credits for $10 USD",
      actionHref: "/register?plan=demo",
      actionText: isFr ? "Choisir Demo" : "Select Demo",
      featured: false,
    },
    {
      tier: "Professional",
      price: "$49",
      period: isFr ? "USD / mois" : "USD / month",
      credits: isFr ? "25 000 crédits IA inclus / mois" : "25,000 AI credits included / mo",
      creditExtra: isFr ? "Supplément : +25 000 crédits pour 25 USD" : "Add-on: +25,000 credits for $25 USD",
      actionHref: "/register?plan=professional",
      actionText: isFr ? "Choisir Professional" : "Select Professional",
      featured: true,
    },
    {
      tier: "Enterprise",
      price: isFr ? "Sur mesure" : "Custom quote",
      period: isFr ? "Devis personnalisé" : "Tailored solution",
      credits: isFr ? "Crédits IA sur mesure" : "Custom AI credit volume",
      creditExtra: isFr ? "Accompagnement et SLA dédiés" : "Dedicated SLA & onboarding",
      actionHref: "mailto:bonjour@avenqo.ca",
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
            <Link className="text-link" href="mailto:bonjour@avenqo.ca">
              {t.finalCta.scheduleDemo}
            </Link>
          </div>
        </div>
      </section>

      <footer>
        <div className="page-shell footer-bottom">
          <span>{t.footer.copyright}</span>
          <a href="https://avenqo.ca">avenqo.ca</a>
        </div>
      </footer>
    </main>
  );
}
