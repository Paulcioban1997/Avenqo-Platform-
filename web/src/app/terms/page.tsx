import type { Metadata } from "next";
import Link from "next/link";
import Image from "next/image";
import { Header } from "@/components/header";

export const metadata: Metadata = {
  title: "Conditions d'utilisation",
  description: "Conditions d'utilisation et de prestation de services de la plateforme Avenqo par PMC Solutions AI Inc. Référence contractuelle pour les abonnements d'entreprise.",
  alternates: {
    canonical: "/terms",
  },
  openGraph: {
    title: "Conditions d'utilisation | Avenqo",
    description: "Conditions générales d'utilisation de la plateforme Avenqo par PMC Solutions AI Inc.",
    url: "https://avenqo.ca/terms",
    images: ["/brand/avenqo-card.png"],
  },
};

export default function TermsPage() {
  return (
    <main className="min-h-screen flex flex-col bg-background text-foreground">
      <Header />
      <section className="section" style={{ paddingTop: 140, paddingBottom: 80 }}>
        <div className="page-shell" style={{ maxWidth: 840, margin: "0 auto" }}>
          <span className="section-kicker">Cadre contractuel & Abonnements</span>
          <h1 style={{ margin: "12px 0 10px", fontSize: "clamp(32px, 4vw, 44px)", fontWeight: 800 }}>
            Conditions d&apos;utilisation
          </h1>
          <p style={{ color: "var(--muted)", fontSize: 14, marginBottom: 36 }}>
            Dernière mise à jour : 19 septembre 2026 • Droit applicable : Québec et Canada
          </p>

          <div style={{ color: "var(--foreground)", opacity: 0.9, fontSize: 15, lineHeight: 1.8, display: "flex", flexDirection: "column", gap: 24 }}>
            <p>
              Les présentes Conditions Générales d&apos;Utilisation (ci-après « Conditions ») régissent l&apos;accès et l&apos;utilisation de la plateforme logicielle Avenqo, éditée et exploitée par <strong>PMC Solutions AI Inc.</strong> (« Avenqo », « nous »), société constituée en vertu des lois de la province de Québec, Canada.
            </p>

            <div>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: 8 }}>1. Objet du service SaaS</h2>
              <p>
                Avenqo est une plateforme modulaire d&apos;intelligence d&apos;affaires (AI Business Operating System) conçue pour unifier les décisions, prévisions et automatisations d&apos;entreprises (commerce omnicanal, relation client, préparation comptable, OCR de documents, agents vocaux). Chaque organisation dispose d&apos;un espace locataire (tenant) strictement cloisonné.
              </p>
            </div>

            <div>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: 8 }}>2. Inscription, vérification et sécurité des accès</h2>
              <p>
                L&apos;accès au service requiert la création d&apos;un compte professionnel et la validation obligatoire de l&apos;adresse courriel d&apos;entreprise via un jeton d&apos;activation cryptographique valide 24 heures. Le client est seul responsable du maintien de la confidentialité de ses identifiants et de toutes les activités réalisées sous ses comptes utilisateurs.
              </p>
            </div>

            <div>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: 8 }}>3. Forfaits, période d&apos;essai et facturation</h2>
              <ul style={{ listStyleType: "disc", paddingLeft: 24, marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}>
                <li><strong>Période d&apos;essai gratuit :</strong> Sauf disposition contractuelle contraire, l&apos;inscription inclut un essai d&apos;évaluation de 14 jours avec crédits IA initiaux, sans obligation d&apos;enregistrement de carte de crédit.</li>
                <li><strong>Tarification des abonnements :</strong> Les offres récurrentes (Demo à $28 USD/mois pour 3 modules et 6 500 crédits IA ; Professional à $49 USD/mois pour 6 modules et 25 000 crédits IA) sont facturées d&apos;avance mensuellement via le processeur de paiement Stripe. Les conversions bancaires vers d&apos;autres devises (notamment CAD) sont gérées automatiquement par l&apos;institution financière de l&apos;acheteur.</li>
                <li><strong>Formule Entreprise :</strong> Les déploiements Enterprise font l&apos;objet d&apos;un bon de commande dédié précisant le périmètre des modules, les quotas de crédits IA et les niveaux de service personnalisés.</li>
                <li><strong>Recharges de crédits IA :</strong> L&apos;utilisation des agents IA est régie par un solde de crédits. Des recharges peuvent être ajoutées au forfait en cours de cycle.</li>
              </ul>
            </div>

            <div>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: 8 }}>4. Propriété intellectuelle et intégrité des données</h2>
              <p>
                Le client conserve la propriété pleine et entière de toutes les données, transactions, documents et fichiers téléversés ou synchronisés dans son espace Avenqo. PMC Solutions AI Inc. s&apos;interdit formellement d&apos;exploiter les données du client à des fins d&apos;entraînement de modèles d&apos;intelligence artificielle publics ou mutualisés.
              </p>
            </div>

            <div>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: 8 }}>5. Résiliation et exportabilité</h2>
              <p>
                Le client peut résilier son abonnement mensuel à tout moment depuis son tableau de bord de facturation avec prise d&apos;effet à la fin de la période en cours. Avant la fermeture définitive de son compte, le client peut exporter l&apos;intégralité de ses jeux de données préparés au format CSV ou JSON standard.
              </p>
            </div>

            <div>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: 8 }}>6. Loi applicable et tribunal compétent</h2>
              <p>
                Les présentes Conditions sont régies et interprétées selon les lois de la province de Québec et les lois fédérales du Canada qui s&apos;y appliquent. Tout litige relatif à leur validité, interprétation ou exécution relèvera de la compétence exclusive des tribunaux du district judiciaire de Montréal, Québec.
              </p>
            </div>

            <div style={{ paddingTop: 16 }}>
              <Link href="/" className="button button-secondary" style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                ← Retour à l&apos;accueil
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Full Footer */}
      <footer style={{ marginTop: "auto" }}>
        <div className="page-shell footer-grid">
          <div className="footer-brand">
            <Image src="/brand/avenqo-logo.png" alt="Avenqo" width={1920} height={864} />
            <p>Plateforme d&apos;intelligence d&apos;affaires par PMC Solutions AI</p>
          </div>
          <div>
            <strong>Plateforme</strong>
            <Link href="/#fonctionnalites">Fonctionnalités</Link>
            <Link href="/#modules">Modules</Link>
            <Link href="/pricing">Tarifs</Link>
            <Link href="/#fonctionnement">Fonctionnement</Link>
          </div>
          <div>
            <strong>Entreprise</strong>
            <Link href="/#entreprise">Entreprise</Link>
            <Link href="/contact">Contact & Démo</Link>
            <Link href="/#securite">Sécurité</Link>
            <Link href="/pricing">Tarifs</Link>
          </div>
          <div>
            <strong>Ressources</strong>
            <Link href="/docs">Documentation</Link>
            <Link href="/#faq">FAQ</Link>
            <Link href="/privacy">Confidentialité</Link>
            <Link href="/terms">Conditions</Link>
          </div>
        </div>
        <div className="page-shell footer-bottom">
          <span>© 2026 PMC Solutions AI Inc. Tous droits réservés.</span>
          <a href="https://avenqo.ca">avenqo.ca</a>
        </div>
      </footer>
    </main>
  );
}
