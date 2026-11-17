import type { Metadata } from "next";
import { Suspense } from "react";
import { ConfirmEmailView } from "@/components/auth/confirm-email-view";

export const metadata: Metadata = {
  title: "Confirmer l'adresse",
  description: "Confirmez la nouvelle adresse d'un accès Avenqo existant.",
  robots: { index: false, follow: false },
};

export default function ConfirmEmailPage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-[#070B16]" />}>
      <ConfirmEmailView />
    </Suspense>
  );
}
