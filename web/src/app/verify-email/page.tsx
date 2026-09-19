import type { Metadata } from "next";
import { Suspense } from "react";
import { VerifyEmailView } from "@/components/auth/verify-email-view";

export const metadata: Metadata = {
  title: "Vérification de l'adresse email",
  description: "Vérifiez votre adresse email pour activer votre compte Avenqo.",
  robots: {
    index: false,
    follow: true,
  },
  alternates: {
    canonical: "/verify-email",
  },
};

export default function VerifyEmailPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        </div>
      }
    >
      <VerifyEmailView />
    </Suspense>
  );
}
