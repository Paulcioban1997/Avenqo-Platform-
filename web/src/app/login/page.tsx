import type { Metadata } from "next";
import { AuthForm } from "@/components/auth-form";

export const metadata: Metadata = {
  title: "Connexion",
  description: "Connectez-vous à votre espace sécurisé Avenqo.",
  robots: {
    index: false,
    follow: true,
  },
  alternates: {
    canonical: "/login",
  },
};

export default function LoginPage() {
  return <AuthForm mode="login" />;
}

