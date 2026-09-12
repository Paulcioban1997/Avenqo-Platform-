import type { Metadata } from "next";
import { PricingContent } from "@/components/pricing-content";

export const metadata: Metadata = {
  title: "Tarifs & Offres",
  description:
    "Découvrez les offres Demo, Professional et Enterprise d'Avenqo. Solutions IA modulaires avec Retail Intelligence et intégrations directes.",
  alternates: {
    canonical: "/pricing",
  },
  openGraph: {
    title: "Tarifs & Offres | Avenqo",
    description:
      "Découvrez les offres Demo, Professional et Enterprise d'Avenqo. Solutions IA modulaires pour entreprises et PME.",
    url: "https://avenqo.ca/pricing",
    images: [
      {
        url: "/brand/avenqo-card.png",
        width: 1200,
        height: 630,
        alt: "Avenqo Tarifs & Offres",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Tarifs & Offres | Avenqo",
    description:
      "Découvrez les offres Demo, Professional et Enterprise d'Avenqo. Solutions IA modulaires pour entreprises et PME.",
    images: ["/brand/avenqo-card.png"],
  },
};

export default function PricingPage() {
  return <PricingContent />;
}
