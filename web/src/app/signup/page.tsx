import type { Metadata } from "next";
import { AuthForm } from "@/components/auth-form";

export const metadata: Metadata = {
  title: "Inscription",
  description: "Créez votre compte entreprise sur la plateforme Avenqo.",
  robots: {
    index: false,
    follow: true,
  },
  alternates: {
    canonical: "/signup",
  },
};

export default function SignupPage() {
  return <AuthForm mode="register" />;
}