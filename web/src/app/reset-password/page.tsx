import type { Metadata } from "next";
import { AuthForm } from "@/components/auth-form";

export const metadata: Metadata = {
  title: "Réinitialisation du mot de passe | Avenqo",
  description: "Définissez un nouveau mot de passe sécurisé pour votre compte Avenqo.",
  robots: {
    index: false,
    follow: true,
  },
  alternates: {
    canonical: "/reset-password",
  },
};

export default function ResetPasswordPage() {
  return <AuthForm mode="reset-password" />;
}
