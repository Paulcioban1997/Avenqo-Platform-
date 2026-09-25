"use client";

import Image from "next/image";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  ArrowRight, BarChart3, Bot, BrainCircuit, Building2, Check,
  CircleDollarSign, FileScan, Headphones, Megaphone, MessagesSquare,
  Mic2, Network, Play, ReceiptText, ShieldCheck, ShoppingBag,
  Sparkles, Workflow, Zap,
} from "lucide-react";
import { DashboardPreview } from "@/components/dashboard-preview";
import { Header } from "@/components/header";
import { useLocale, useTranslations } from "@/lib/i18n/locale-context";

const moduleIcons = [
  ShoppingBag, Network, ReceiptText, FileScan, BarChart3, Megaphone,
  BrainCircuit, Mic2, Workflow, Play, Headphones, MessagesSquare,
];

const usecaseIcons = [Building2, CircleDollarSign, ShoppingBag, Workflow];

const fadeUp = {
  initial: { opacity: 0, y: 24 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: "-80px" },
  transition: { duration: 0.6, ease: "easeOut" as const },
};

const MODULE_SLUGS = [
  "retail",
  "crm",
  "accounting",
  "documents",
  "analytics",
  "marketing",
  "voice",
  "workflow",
  "media",
  "support",
  "chat",
];

const PLATFORM_LINK_HREFS = ["#fonctionnalites", "#modules", "/pricing", "#fonctionnement"];
const COMPANY_LINK_HREFS = ["#entreprise", "/contact", "#securite", "/pricing"];
const RESOURCES_LINK_HREFS = ["/docs", "#faq", "/privacy", "/terms"];

export function LandingPage() {
  const t = useTranslations();
  const { locale } = useLocale();
  const isEn = locale === "en";
  const usecaseEntries = [t.usecases.direction, t.usecases.finance, t.usecases.commerce, t.usecases.operations];

  const planTiers = [
    {
      tier: "Base",
      price: "$29.99 USD",
      period: isEn ? "/ month" : "/ mois",
      credits: isEn ? "6,500 AI credits included" : "6 500 crédits IA inclus",
      action: isEn ? "Choose Base" : "Choisir Base",
      href: "/register?plan=base",
      featured: false,
    },
    {
      tier: "Professional",
      price: "$49.99 USD",
      period: isEn ? "/ month" : "/ mois",
      credits: isEn ? "25,000 AI credits included" : "25 000 crédits IA inclus",
      action: isEn ? "Choose Professional" : "Choisir Professional",
      href: "/register?plan=professional",
      featured: true,
    },
    {
      tier: "Enterprise",
      price: isEn ? "Custom quote" : "Sur mesure",
      period: isEn ? "Tailored plan" : "Devis personnalisé",
      credits: isEn ? "Custom AI credit volume" : "Crédits IA sur mesure",
      action: isEn ? "Contact Sales" : "Contacter les ventes",
      href: "/contact",
      featured: false,
    },
  ];

  return (
    <main>
      <Header />
      <section className="hero" id="accueil">
        <div className="hero-grid page-shell">
          <motion.div className="hero-copy" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, ease: "easeOut" }}>
            <div className="eyebrow"><span /> {t.hero.eyebrow}</div>
            <h1>{t.hero.titleLine1}<br /><span>{t.hero.titleLine2}</span></h1>
            <p>{t.hero.subtitle}</p>
            <div className="hero-actions">
              <Link className="button button-primary" href="/register">{t.common.tryFree} <ArrowRight size={17} /></Link>
              <Link className="button button-secondary" href="#demonstration"><Play size={16} /> {t.common.watchDemo}</Link>
            </div>
            <div className="hero-proof"><span><Check size={14} /> {t.common.noCreditCard}</span><span><Check size={14} /> {t.common.guidedSetup}</span><span><ShieldCheck size={14} /> {t.common.isolatedData}</span></div>
          </motion.div>
          <motion.div className="hero-product" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.12, ease: "easeOut" }}>
            <DashboardPreview />
          </motion.div>
        </div>
        <div className="trust-strip page-shell"><span>{t.hero.trustLabel}</span><strong>{t.hero.trustSell}</strong><i /><strong>{t.hero.trustUnderstand}</strong><i /><strong>{t.hero.trustAutomate}</strong><i /><strong>{t.hero.trustDecide}</strong></div>
      </section>

      <section className="section feature-section" id="fonctionnalites">
        <div className="page-shell">
          <motion.div className="section-heading center" {...fadeUp}><span className="section-kicker">{t.features.kicker}</span><h2>{t.features.title}</h2><p>{t.features.subtitle}</p></motion.div>
          <div className="feature-grid">
            <motion.article className="feature-large assistant-feature" id="demonstration" {...fadeUp}>
              <div className="feature-label"><Bot size={18} /> {t.features.assistantLabel}</div><h3>{t.features.assistantTitle}</h3><p>{t.features.assistantText}</p>
              <div className="chat-demo"><div className="question">{t.features.demoQuestion}</div><div className="answer"><span><Sparkles size={15} /></span><p>{t.features.demoAnswer}</p></div><div className="chat-actions"><Link href="/register">{t.features.demoAction1}</Link><Link href="#modules">{t.features.demoAction2}</Link></div></div>
            </motion.article>
            <motion.article className="feature-small dark-feature" {...fadeUp} whileHover={{ y: -4 }}><Zap size={24} /><h3>{t.features.actionsTitle}</h3><p>{t.features.actionsText}</p><div className="action-line"><span>{t.features.actionsPriority}</span><strong>{t.features.actionsLine}</strong><ArrowRight size={17} /></div></motion.article>
            <motion.article className="feature-small" id="securite" {...fadeUp} whileHover={{ y: -4 }}><ShieldCheck size={24} /><h3>{t.features.securityTitle}</h3><p>{t.features.securityText}</p><div className="security-list"><span><Check /> {t.features.securityItem1}</span><span><Check /> {t.features.securityItem2}</span><span><Check /> {t.features.securityItem3}</span></div></motion.article>
          </div>
        </div>
      </section>

      <section className="section modules-section" id="modules">
        <div className="page-shell">
          <motion.div className="section-heading split" {...fadeUp}><div><span className="section-kicker">{t.modulesSection.kicker}</span><h2>{t.modulesSection.title}</h2></div><p>{t.modulesSection.subtitle}</p></motion.div>
          <div className="module-grid">
            {t.modulesSection.items.map(({ name, description }, index) => {
              const Icon = moduleIcons[index] ?? ShoppingBag;
              const slug = MODULE_SLUGS[index] ?? "retail";
              return (
                <motion.article
                  className="module-card"
                  key={name}
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: "-60px" }}
                  transition={{ duration: 0.5, delay: (index % 3) * 0.08, ease: "easeOut" }}
                  whileHover={{ y: -6 }}
                >
                  <div className="module-icon"><Icon size={21} /></div><h3>{name}</h3><p>{description}</p>
                  <Link href={`/modules/${slug}`} aria-label={`${t.modulesSection.discover} ${name}`}>{t.modulesSection.discover} <ArrowRight size={15} /></Link>
                </motion.article>
              );
            })}
          </div>
        </div>
      </section>

      <section className="section steps-section" id="fonctionnement">
        <div className="page-shell">
          <motion.div className="section-heading center light" {...fadeUp}><span className="section-kicker">{t.steps.kicker}</span><h2>{t.steps.title}</h2></motion.div>
          <div className="steps-grid">
            {t.steps.items.map(({ number, title, text }, index) => (
              <motion.article key={number} initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-60px" }} transition={{ duration: 0.5, delay: index * 0.08, ease: "easeOut" }}>
                <span>{number}</span><h3>{title}</h3><p>{text}</p>
              </motion.article>
            ))}
          </div>
          <div className="steps-cta"><span>{t.steps.ctaLabel}</span><Link href="/register">{t.steps.ctaButton} <ArrowRight size={16} /></Link></div>
        </div>
      </section>

      <section className="section usecases-section" id="entreprise">
        <div className="page-shell usecases-grid">
          <motion.div className="usecases-copy" {...fadeUp}>
            <span className="section-kicker">{t.usecases.kicker}</span><h2>{t.usecases.title}</h2><p>{t.usecases.subtitle}</p>
            <div className="usecase-tabs">
              {usecaseEntries.map(({ title, text }, index) => {
                const Icon = usecaseIcons[index];
                return (
                  <article key={title}>
                    <Icon /><div><strong>{title}</strong><span>{text}</span></div>
                  </article>
                );
              })}
            </div>
          </motion.div>
          <motion.div className="brand-card-wrap" initial={{ opacity: 0, scale: 0.97 }} whileInView={{ opacity: 1, scale: 1 }} viewport={{ once: true }} transition={{ duration: 0.6, ease: "easeOut" }}>
            <Image src="/brand/avenqo-card.png" alt="Carte officielle Avenqo, plateforme IA tout-en-un" width={1536} height={864} />
          </motion.div>
        </div>
      </section>

      <section className="section why-section">
        <div className="page-shell">
          <motion.div className="section-heading center" {...fadeUp}><span className="section-kicker">{t.why.kicker}</span><h2>{t.why.title}</h2></motion.div>
          <div className="why-grid">
            {t.why.items.map(({ number, title, text }, index) => (
              <motion.article key={number} initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-60px" }} transition={{ duration: 0.5, delay: index * 0.08, ease: "easeOut" }}>
                <span>{number}</span><h3>{title}</h3><p>{text}</p>
              </motion.article>
            ))}
          </div>
        </div>
      </section>

      <section className="section pricing-section" id="tarifs">
        <div className="page-shell">
          <motion.div className="section-heading center" {...fadeUp}><span className="section-kicker">{t.pricing.kicker}</span><h2>{t.pricing.title}</h2><p>{t.pricing.subtitle}</p></motion.div>
          <div className="pricing-grid">
            {t.pricing.plans.map((plan, index) => {
              const meta = planTiers[index] || planTiers[0];
              return (
                <PriceCard
                  key={plan.tier}
                  tier={meta.tier}
                  title={plan.title}
                  price={meta.price}
                  period={meta.period}
                  credits={meta.credits}
                  items={plan.items}
                  action={meta.action}
                  href={meta.href}
                  popularLabel={t.pricing.popular}
                  featured={meta.featured}
                />
              );
            })}
          </div>

          <div style={{ textAlign: "center", marginTop: 32, fontSize: "0.9rem", color: "var(--muted)" }}>
            <p>
              {isEn
                ? "✨ All plans include a 14-day free trial. No credit card required to explore. AI evaluation credits included."
                : "✨ Tous les forfaits incluent un essai gratuit de 14 jours. Aucune carte de crédit requise. Crédits d'évaluation IA inclus."}
            </p>
          </div>
        </div>
      </section>

      <section className="section faq-section" id="faq">
        <div className="page-shell faq-grid">
          <motion.div {...fadeUp}><span className="section-kicker">{t.faq.kicker}</span><h2>{t.faq.title}</h2><p>{t.faq.subtitle}</p><Link href="/contact" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>{isEn ? "Contact our specialists" : "Parler à un conseiller"} <ArrowRight size={15} /></Link></motion.div>
          <motion.div className="faq-list" {...fadeUp}>
            {t.faq.items.map(({ question, answer }) => <details key={question}><summary>{question}<span>+</span></summary><p>{answer}</p></details>)}
          </motion.div>
        </div>
      </section>

      <section className="final-cta" id="contact">
        <div className="page-shell final-cta-inner">
          <div><span>{t.finalCta.label}</span><h2>{t.finalCta.title}</h2></div>
          <div><Link className="button white-button" href="/register">{t.finalCta.tryFree} <ArrowRight size={17} /></Link><Link className="text-link" href="/contact">{t.finalCta.scheduleDemo}</Link></div>
        </div>
      </section>

      <footer>
        <div className="page-shell footer-grid">
          <div className="footer-brand"><Image src="/brand/avenqo-logo.png" alt="Avenqo" width={1920} height={864} /><p>{t.footer.tagline}</p></div>
          <FooterColumn title={t.footer.platformTitle} links={t.footer.platformLinks} hrefs={PLATFORM_LINK_HREFS} />
          <FooterColumn title={t.footer.companyTitle} links={t.footer.companyLinks} hrefs={COMPANY_LINK_HREFS} />
          <FooterColumn title={t.footer.resourcesTitle} links={t.footer.resourcesLinks} hrefs={RESOURCES_LINK_HREFS} />
        </div>
        <div className="page-shell footer-bottom"><span>{t.footer.copyright}</span><a href="https://avenqo.ca">avenqo.ca</a></div>
      </footer>
    </main>
  );
}

function PriceCard({
  tier,
  title,
  price,
  period,
  credits,
  items,
  action,
  href,
  popularLabel,
  featured = false,
}: {
  tier: string;
  title: string;
  price: string;
  period: string;
  credits: string;
  items: string[];
  action: string;
  href: string;
  popularLabel: string;
  featured?: boolean;
}) {
  return (
    <motion.article
      className={`price-card ${featured ? "featured-price" : ""}`}
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.5, ease: "easeOut" }}
      whileHover={{ y: -4 }}
    >
      {featured && <div className="popular">{popularLabel}</div>}
      <span>{tier}</span>
      <h3>{title}</h3>
      <div style={{ margin: "14px 0 6px" }}>
        <span style={{ fontSize: 34, fontWeight: 800, color: "var(--foreground)" }}>{price}</span>
        <span style={{ fontSize: 14, color: "var(--muted)", marginLeft: 6 }}>{period}</span>
      </div>
      <div style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 600, padding: "3px 10px", borderRadius: 9999, background: "rgba(56, 189, 248, 0.1)", color: "#38bdf8", marginBottom: 16 }}>
        <Sparkles size={13} /> {credits}
      </div>
      <ul>
        {items.map((item) => (
          <li key={item}>
            <Check size={16} /> {item}
          </li>
        ))}
      </ul>
      <Link href={href} className={featured ? "button button-primary" : "button"} style={{ display: "block", textAlign: "center", marginTop: "auto" }}>
        {action}
      </Link>
    </motion.article>
  );
}

function FooterColumn({ title, links, hrefs }: { title: string; links: string[]; hrefs: string[] }) {
  return <div><strong>{title}</strong>{links.map((link, index) => <Link href={hrefs[index] ?? "/contact"} key={link}>{link}</Link>)}</div>;
}
