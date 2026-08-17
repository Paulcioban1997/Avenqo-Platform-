import type { Metadata } from "next";
import { AuthForm } from "@/components/auth-form";

export const metadata: Metadata = {
  title: "Créer une organisation | Avenqo",
  description: "Créez votre espace professionnel sécurisé sur Avenqo.",
};

export default function RegisterPage() {
  return <AuthForm mode="register" />;
}
