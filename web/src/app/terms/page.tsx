import type { Metadata } from "next";
import Link from "next/link";
import { Header } from "@/components/header";

export const metadata: Metadata = {
  title: "Conditions | Avenqo",
  description: "Conditions d'utilisation de la plateforme Avenqo.",
};

export default function TermsPage() {
  return (
    <main>
      <Header />
      <section className="section">
        <div className="page-shell" style={{ maxWidth: 760 }}>
          <span className="section-kicker">Conditions</span>
          <h1 style={{ margin: "12px 0 28px", fontSize: "clamp(32px, 4vw, 44px)" }}>Conditions d&apos;utilisation</h1>
          <div style={{ color: "var(--muted)", fontSize: 16, lineHeight: 1.8, display: "flex", flexDirection: "column", gap: 20 }}>
            <p>
              L&apos;utilisation de la plateforme Avenqo, éditée par PMC Solutions AI, implique l&apos;acceptation
              des présentes conditions.
            </p>
            <p>
              <strong>Le service.</strong> Avenqo est une plateforme IA modulaire (vente, relation client, finance,
              documents, opérations). Chaque module est activable indépendamment selon l&apos;offre souscrite.
            </p>
            <p>
              <strong>Compte et espace de travail.</strong> Chaque entreprise dispose de son propre espace isolé.
              Le titulaire du compte est responsable de la gestion des accès accordés à ses utilisateurs.
            </p>
            <p>
              <strong>Facturation.</strong> Les offres Essentiel, Professionnel et Entreprise sont détaillées sur la
              page tarifs. Toute mise à niveau ou changement de plan peut être demandé auprès de notre équipe.
            </p>
            <p>
              <strong>Disponibilité.</strong> Nous nous engageons à maintenir un service fiable et à communiquer
              rapidement en cas d&apos;interruption planifiée ou imprévue.
            </p>
            <p>
              <strong>Contact.</strong> Pour toute question sur ces conditions, écrivez à{" "}
              <a href="mailto:bonjour@avenqo.ca">bonjour@avenqo.ca</a>.
            </p>
            <p><Link href="/">← Retour à l&apos;accueil</Link></p>
          </div>
        </div>
      </section>
    </main>
  );
}
