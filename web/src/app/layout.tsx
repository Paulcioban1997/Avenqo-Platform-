import type { Metadata } from "next";
import { Geist, Manrope } from "next/font/google";
import { LocaleProvider } from "@/lib/i18n/locale-context";
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
  title: "Avenqo | Une plateforme. Toutes vos solutions IA.",
  description:
    "Automatisez votre entreprise grâce à la plateforme IA modulaire Avenqo, conçue pour les PME et les entreprises.",
  icons: {
    icon: "/brand/avenqo-icon.png",
    apple: "/brand/avenqo-icon.png",
  },
  openGraph: {
    title: "Avenqo",
    description: "Une plateforme. Toutes vos solutions IA.",
    url: "https://avenqo.ca",
    siteName: "Avenqo",
    locale: "fr_CA",
    type: "website",
    images: ["/brand/avenqo-card.png"],
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="fr"
      className={`${geistSans.variable} ${manrope.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <LocaleProvider>{children}</LocaleProvider>
      </body>
    </html>
  );
}
