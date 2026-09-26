"use client";

import Image from "next/image";
import Link from "next/link";
import { useTranslations } from "@/lib/i18n/locale-context";

export function SiteFooter() {
  const t = useTranslations();
  const columns = [
    {
      title: t.footer.platformTitle,
      links: [t.nav.features, t.nav.modules, t.nav.pricing],
      hrefs: ["/#fonctionnalites", "/#modules", "/pricing"],
    },
    {
      title: t.footer.companyTitle,
      links: [t.nav.enterprise, t.footer.companyLinks[1]],
      hrefs: ["/#entreprise", "/contact"],
    },
    {
      title: t.footer.resourcesTitle,
      links: [t.nav.docs, t.footer.resourcesLinks[1], t.footer.resourcesLinks[2], t.footer.resourcesLinks[3]],
      hrefs: ["/docs", "/#faq", "/privacy", "/terms"],
    },
  ];

  return (
    <footer style={{ marginTop: "auto" }}>
      <div className="page-shell footer-grid">
        <div className="footer-brand">
          <Image src="/brand/avenqo-logo.png" alt="Avenqo" width={1920} height={864} />
          <p>{t.footer.tagline}</p>
        </div>
        {columns.map((column) => (
          <div key={column.title}>
            <strong>{column.title}</strong>
            {column.links.map((label, index) => (
              <Link href={column.hrefs[index]} key={column.hrefs[index]}>{label}</Link>
            ))}
          </div>
        ))}
      </div>
      <div className="page-shell footer-bottom">
        <span>{t.footer.copyright}</span>
        <a href="https://avenqo.ca">avenqo.ca</a>
      </div>
    </footer>
  );
}