import type { Metadata } from "next";
import { Header } from "@/components/header";
import { SiteFooter } from "@/components/site-footer";
import { PrivacyContent } from "@/components/trust-sections";

export const metadata: Metadata = {
  title: "Avenqo",
  alternates: { canonical: "/privacy" },
};

export default function PrivacyPage() {
  return <main><Header /><PrivacyContent /><SiteFooter /></main>;
}