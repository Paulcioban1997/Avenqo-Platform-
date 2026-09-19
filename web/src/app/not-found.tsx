"use client";

import Link from "next/link";
import Image from "next/image";
import { ArrowLeft, Home, LogIn, Mail } from "lucide-react";
import { useLocale } from "@/lib/i18n/locale-context";

export default function NotFound() {
  const { locale } = useLocale();
  const isEn = locale === "en";

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-6 bg-background text-foreground relative overflow-hidden">
      {/* Background glow effects */}
      <div
        className="absolute w-[500px] h-[500px] rounded-full blur-3xl opacity-15 pointer-events-none"
        style={{
          background: "radial-gradient(circle, #38bdf8 0%, rgba(99, 102, 241, 0.4) 50%, transparent 70%)",
          top: "20%",
          left: "50%",
          transform: "translateX(-50%)",
        }}
      />

      <div className="max-w-md w-full text-center space-y-8 relative z-10">
        <Link href="/" className="inline-block mx-auto transition-transform hover:scale-105">
          <Image src="/brand/avenqo-logo.png" alt="Avenqo" width={220} height={100} priority className="h-10 w-auto mx-auto" />
        </Link>

        <div className="space-y-3">
          <span className="inline-block px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider bg-primary/10 text-primary border border-primary/20">
            404 — {isEn ? "Error" : "Erreur"}
          </span>
          <h1 className="text-4xl font-extrabold tracking-tight sm:text-5xl">
            {isEn ? "Page Not Found" : "Page introuvable"}
          </h1>
          <p className="text-muted-foreground text-sm sm:text-base leading-relaxed">
            {isEn
              ? "The resource or page you requested could not be located. It might have been moved or updated."
              : "La ressource ou la page que vous recherchez est introuvable. Elle a peut-être été déplacée ou mise à jour."}
          </p>
        </div>

        <div className="flex flex-col sm:flex-row gap-3 justify-center pt-2">
          <Link
            href="/"
            className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg bg-primary text-primary-foreground font-medium text-sm transition-all hover:opacity-90 shadow-sm"
          >
            <Home size={16} /> {isEn ? "Back to Homepage" : "Retour à l'accueil"}
          </Link>
          <Link
            href="/login"
            className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg border border-border bg-card/50 text-foreground font-medium text-sm transition-all hover:bg-muted"
          >
            <LogIn size={16} /> {isEn ? "Sign In" : "Se connecter"}
          </Link>
        </div>

        <div className="pt-6 border-t border-border/50 text-xs text-muted-foreground">
          <p>
            {isEn ? "Need assistance?" : "Besoin d'assistance ?"}{" "}
            <Link href="/contact" className="text-primary hover:underline inline-flex items-center gap-1">
              <Mail size={12} /> {isEn ? "Contact our team" : "Contacter notre équipe"}
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
