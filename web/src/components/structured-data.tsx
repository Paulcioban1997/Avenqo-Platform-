export function StructuredData() {
  const organizationSchema = {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: "PMC Solutions AI",
    alternateName: "Avenqo",
    url: "https://avenqo.ca",
    logo: "https://avenqo.ca/brand/avenqo-logo.png",
    description:
      "Éditeur de la plateforme Avenqo — AI Business Operating System pour PME et entreprises.",
    contactPoint: {
      "@type": "ContactPoint",
      contactType: "customer service",
      email: "bonjour@avenqo.ca",
      availableLanguage: ["French", "English"],
    },
    sameAs: [],
  };

  const softwareApplicationSchema = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "Avenqo",
    applicationCategory: "BusinessApplication",
    operatingSystem: "Web Browser",
    url: "https://avenqo.ca",
    description:
      "Plateforme SaaS B2B modulaire combinant Retail Intelligence, intégrations directes (Shopify, WooCommerce), automatisations et décisions stratégiques unifiées.",
    author: {
      "@type": "Organization",
      name: "PMC Solutions AI",
      url: "https://avenqo.ca",
    },
    offers: {
      "@type": "AggregateOffer",
      offerCount: "3",
      offers: [
        {
          "@type": "Offer",
          name: "Demo",
          price: "28.00",
          priceCurrency: "USD",
          description: "Offre Demo : 28 USD / mois avec 6 500 crédits IA inclus, accès Retail Intelligence et découverte de la plateforme IA Avenqo",
          url: "https://avenqo.ca/pricing",
        },
        {
          "@type": "Offer",
          name: "Professional",
          price: "49.00",
          priceCurrency: "USD",
          description:
            "Offre Professional : 49 USD / mois avec 25 000 crédits IA inclus, connecteurs commerce et automatisation avancée",
          url: "https://avenqo.ca/pricing",
        },
        {
          "@type": "Offer",
          name: "Enterprise",
          priceCurrency: "USD",
          description:
            "Offre Enterprise : sur mesure (Contact / Custom quote) avec intégrations dédiées, gouvernance et accompagnement personnalisé",
          url: "https://avenqo.ca/pricing",
        },
      ],
    },
  };

  const webSiteSchema = {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: "Avenqo",
    url: "https://avenqo.ca",
    publisher: {
      "@type": "Organization",
      name: "PMC Solutions AI",
    },
    inLanguage: "fr",
  };

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(organizationSchema) }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(softwareApplicationSchema),
        }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(webSiteSchema) }}
      />
    </>
  );
}
