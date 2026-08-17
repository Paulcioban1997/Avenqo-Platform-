import type { Metadata } from "next";
import { AuthForm } from "@/components/auth-form";

export const metadata: Metadata = {
  title: "Connexion | Avenqo",
  description: "Connectez-vous à votre espace sécurisé Avenqo.",
};

export default function LoginPage() {
  return <AuthForm mode="login" />;
}
