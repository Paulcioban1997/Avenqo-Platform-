"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowUpRight, Fingerprint, Hand, Layers3, LockKeyhole, ScanLine, ShieldCheck } from "lucide-react";
import { useTranslations } from "@/lib/i18n/locale-context";

const icons = [Layers3, Hand, ScanLine, Fingerprint, ShieldCheck, LockKeyhole];
const principleIndexes = [1, 2, 4, 2];

export function TrustSections() {
  const { trust } = useTranslations();
  const reducedMotion = useReducedMotion();
  const reveal = {
    initial: { opacity: 0, y: reducedMotion ? 0 : 12 },
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: true },
    transition: { duration: reducedMotion ? 0 : 0.35 },
  };

  return (
    <>
      <section className="section trust-section" id="trust" aria-labelledby="trust-heading">
        <div className="page-shell">
          <motion.div className="section-heading trust-heading" {...reveal}>
            <h2 id="trust-heading">{trust.heading}</h2>
            <Link className="trust-text-link" href="/trust">{trust.center}<ArrowUpRight size={18} /></Link>
          </motion.div>
          <div className="trust-grid">
            {trust.cards.map(([title, text], index) => {
              const Icon = icons[index];
              return (
                <motion.article key={title} className="trust-card" {...reveal}>
                  <span className="trust-icon"><Icon size={22} aria-hidden="true" /></span>
                  <h3>{title}</h3><p>{text}</p>
                </motion.article>
              );
            })}
          </div>
        </div>
      </section>
      <section className="section responsible-section" aria-labelledby="responsible-heading">
        <div className="page-shell">
          <motion.div className="section-heading" {...reveal}><h2 id="responsible-heading">{trust.responsible}</h2></motion.div>
          <div className="principle-grid">
            {trust.principles.map((title, index) => (
              <motion.article className="trust-card principle-card" key={title} {...reveal}>
                <span className="principle-number" aria-hidden="true">0{index + 1}</span>
                <h3>{title}</h3><p>{trust.cards[principleIndexes[index]][1]}</p>
              </motion.article>
            ))}
          </div>
          <motion.aside className="research-note" {...reveal}>
            <div><h3>{trust.research[0]}</h3><p>{trust.research[1]}</p></div>
            <a className="trust-text-link" href="https://lawzero.org/" target="_blank" rel="noopener noreferrer">LawZero<ArrowUpRight size={16} /></a>
            <p className="research-disclosure">{trust.research[2]}</p>
          </motion.aside>
        </div>
      </section>
    </>
  );
}

export function TrustCenterContent() {
  const { trust } = useTranslations();
  return (
    <>
      <section className="section trust-page-intro"><div className="page-shell">
        <span className="section-kicker">Avenqo</span><h1>{trust.center}</h1>
        <nav className="trust-page-links"><Link href="/privacy">{trust.privacy}</Link><Link href="/contact">{trust.contact}</Link></nav>
      </div></section>
      <TrustSections />
      <section className="section trust-practices"><div className="page-shell privacy-sections">
        {[2, 3, 4, 6].map((index) => <article key={trust.data[index][0]}><h2>{trust.data[index][0]}</h2><p>{trust.data[index][1]}</p></article>)}
      </div></section>
    </>
  );
}

export function PrivacyContent() {
  const { trust } = useTranslations();
  return <section className="section trust-page-intro"><div className="page-shell privacy-shell">
    <span className="section-kicker">Avenqo</span><h1>{trust.privacy}</h1>
    <div className="privacy-sections">{trust.data.map(([title, text]) => <article key={title}><h2>{title}</h2><p>{text}</p></article>)}</div>
    <nav className="trust-page-links"><Link href="/contact">{trust.contact}</Link><Link href="/trust">{trust.center}</Link></nav>
  </div></section>;
}