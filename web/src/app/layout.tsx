import type { Metadata } from "next";
import { Geist, Manrope } from "next/font/google";
import { LocaleProvider } from "@/lib/i18n/locale-context";
import { StructuredData } from "@/components/structured-data";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const manrope = Manrope({
  variable: "--font-manrope",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  metadataBase: new URL("https://avenqo.ca"),
  title: {
    default: "Avenqo — AI Business Operating System",
    template: "%s | Avenqo",
  },
  description:
    "Plateforme IA modulaire pour les entreprises et PME : Retail Intelligence, intégrations directes, automatisation et décisions stratégiques unifiées.",
  keywords: [
    "Avenqo",
    "AI Business Operating System",
    "Retail Intelligence",
    "Intelligence Artificielle B2B",
    "Plateforme SaaS IA",
    "Commerce connecté",
    "Automatisation PME",
  ],
  authors: [{ name: "PMC Solutions AI", url: "https://avenqo.ca" }],
  creator: "PMC Solutions AI",
  publisher: "PMC Solutions AI",
  formatDetection: {
    email: false,
    address: false,
    telephone: false,
  },
  icons: {
    icon: [
      { url: "/brand/avenqo-icon.png", sizes: "32x32", type: "image/png" },
      { url: "/brand/avenqo-icon.png", sizes: "192x192", type: "image/png" },
    ],
    apple: "/brand/avenqo-icon.png",
  },
  alternates: {
    canonical: "/",
    languages: {
      "fr": "/",
      "x-default": "/",
    },
  },
  openGraph: {
    title: "Avenqo — AI Business Operating System",
    description:
      "Plateforme IA modulaire pour les entreprises et PME : Retail Intelligence, connecteurs commerce et décisions unifiées.",
    url: "https://avenqo.ca",
    siteName: "Avenqo",
    locale: "fr_CA",
    type: "website",
    images: [
      {
        url: "/brand/avenqo-card.png",
        width: 1200,
        height: 630,
        alt: "Avenqo — AI Business Operating System",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Avenqo — AI Business Operating System",
    description:
      "Plateforme IA modulaire pour les entreprises et PME : Retail Intelligence, connecteurs commerce et décisions unifiées.",
    images: ["/brand/avenqo-card.png"],
    creator: "@avenqo",
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-video-preview": -1,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="fr"
      className={`${geistSans.variable} ${manrope.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <StructuredData />
        <LocaleProvider>{children}</LocaleProvider>
      </body>
    </html>
  );
}
