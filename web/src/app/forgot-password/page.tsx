import type { Metadata } from "next";
import { AuthForm } from "@/components/auth-form";

export const metadata: Metadata = {
  title: "Mot de passe oublié | Avenqo",
  description: "Réinitialisez votre mot de passe pour accéder à votre espace sécurisé Avenqo.",
  robots: {
    index: false,
    follow: true,
  },
  alternates: {
    canonical: "/forgot-password",
  },
};

export default function ForgotPasswordPage() {
  return <AuthForm mode="forgot-password" />;
}
