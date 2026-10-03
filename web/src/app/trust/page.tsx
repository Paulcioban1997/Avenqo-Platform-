import type { Metadata } from "next";
import { Header } from "@/components/header";
import { SiteFooter } from "@/components/site-footer";
import { TrustCenterContent } from "@/components/trust-sections";

export const metadata: Metadata = {
  title: "Avenqo",
  alternates: { canonical: "/trust" },
};

export default function TrustPage() {
  return <main><Header /><TrustCenterContent /><SiteFooter /></main>;
}