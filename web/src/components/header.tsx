"use client";

import Image from "next/image";
import Link from "next/link";
import { ArrowRight, Menu, X } from "lucide-react";
import { useState } from "react";
import { useTranslations } from "@/lib/i18n/locale-context";
import { RegionLanguageSelector } from "./region-language-selector";

const APP_BASE_URL = process.env.NEXT_PUBLIC_APP_URL ?? "https://app.avenqo.ca";

export function Header() {
  const [open, setOpen] = useState(false);
  const t = useTranslations();
  const links = [
    [t.nav.features, "#fonctionnalites"],
    [t.nav.modules, "#modules"],
    [t.nav.pricing, "#tarifs"],
    [t.nav.enterprise, "#entreprise"],
    [t.nav.docs, "#faq"],
  ];
  return (
    <header className="site-header">
      <div className="page-shell header-inner">
        <Link href="#accueil" className="header-logo" aria-label="Avenqo, accueil">
          <Image src="/brand/avenqo-logo.png" alt="Avenqo" width={1920} height={864} priority />
        </Link>
        <nav className="desktop-nav">
          {links.map(([label, href]) => <a href={href} key={label}>{label}</a>)}
        </nav>
        <div className="header-actions">
          <RegionLanguageSelector />
          <a href={`${APP_BASE_URL}/login`}>{t.common.login}</a>
          <a className="header-cta" href={`${APP_BASE_URL}/register`}>{t.common.tryFree} <ArrowRight size={14} /></a>
        </div>
        <button className="menu-button" onClick={() => setOpen(!open)} aria-label={open ? "Fermer le menu" : "Ouvrir le menu"}>{open ? <X /> : <Menu />}</button>
      </div>
      {open && (
        <div className="mobile-nav">
          {links.map(([label, href]) => <a href={href} key={label} onClick={() => setOpen(false)}>{label}</a>)}
          <RegionLanguageSelector />
          <a href={`${APP_BASE_URL}/login`}>{t.common.login}</a>
          <a className="header-cta" href={`${APP_BASE_URL}/register`}>{t.common.tryFree}</a>
        </div>
      )}
    </header>
  );
}
