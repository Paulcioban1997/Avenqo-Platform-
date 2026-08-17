import type { Metadata } from "next";
import Link from "next/link";
import { Header } from "@/components/header";

export const metadata: Metadata = {
  title: "Confidentialité | Avenqo",
  description: "Politique de confidentialité de la plateforme Avenqo.",
};

export default function PrivacyPage() {
  return (
    <main>
      <Header />
      <section className="section">
        <div className="page-shell" style={{ maxWidth: 760 }}>
          <span className="section-kicker">Confidentialité</span>
          <h1 style={{ margin: "12px 0 28px", fontSize: "clamp(32px, 4vw, 44px)" }}>Politique de confidentialité</h1>
          <div style={{ color: "var(--muted)", fontSize: 16, lineHeight: 1.8, display: "flex", flexDirection: "column", gap: 20 }}>
            <p>
              PMC Solutions AI (« Avenqo ») accorde une importance centrale à la protection des données de ses
              clients. Chaque entreprise dispose d&apos;un espace isolé : ses données ne sont jamais partagées avec
              un autre client de la plateforme.
            </p>
            <p>
              <strong>Données collectées.</strong> Nous collectons les informations nécessaires au fonctionnement de
              la plateforme : coordonnées du compte, données métier connectées par vos soins (ventes, clients,
              documents) et journaux d&apos;utilisation à des fins de sécurité et d&apos;amélioration du produit.
            </p>
            <p>
              <strong>Utilisation des données.</strong> Vos données servent uniquement à fournir le service Avenqo :
              exécuter les modules activés, générer des recommandations et assurer le support. Elles ne sont ni
              vendues ni utilisées pour entraîner des modèles partagés avec d&apos;autres clients.
            </p>
            <p>
              <strong>Sécurité.</strong> Accès par rôle, traçabilité complète des actions et hébergement conçu pour
              évoluer avec votre organisation.
            </p>
            <p>
              <strong>Vos droits.</strong> Vous pouvez demander l&apos;accès, la correction ou la suppression de vos
              données à tout moment en écrivant à{" "}
              <a href="mailto:bonjour@avenqo.ca">bonjour@avenqo.ca</a>.
            </p>
            <p><Link href="/">← Retour à l&apos;accueil</Link></p>
          </div>
        </div>
      </section>
    </main>
  );
}
