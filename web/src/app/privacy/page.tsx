import type { Metadata } from "next";
import Link from "next/link";
import Image from "next/image";
import { Header } from "@/components/header";

export const metadata: Metadata = {
  title: "Politique de confidentialité",
  description: "Politique de protection des renseignements personnels et de confidentialité de la plateforme Avenqo par PMC Solutions AI, conforme à la Loi 25 du Québec et à la LPRPDE canadienne.",
  alternates: {
    canonical: "/privacy",
  },
  openGraph: {
    title: "Politique de confidentialité | Avenqo",
    description: "Politique de protection des renseignements personnels de la plateforme Avenqo par PMC Solutions AI.",
    url: "https://avenqo.ca/privacy",
    images: ["/brand/avenqo-card.png"],
  },
};

export default function PrivacyPage() {
  return (
    <main className="min-h-screen flex flex-col bg-background text-foreground">
      <Header />
      <section className="section" style={{ paddingTop: 140, paddingBottom: 80 }}>
        <div className="page-shell" style={{ maxWidth: 840, margin: "0 auto" }}>
          <span className="section-kicker">Cadre juridique & Protection des données</span>
          <h1 style={{ margin: "12px 0 10px", fontSize: "clamp(32px, 4vw, 44px)", fontWeight: 800 }}>
            Politique de confidentialité
          </h1>
          <p style={{ color: "var(--muted)", fontSize: 14, marginBottom: 36 }}>
            Dernière mise à jour : 19 septembre 2026 • Conforme à la Loi 25 (Québec) et à la LPRPDE (Canada)
          </p>

          <div style={{ color: "var(--foreground)", opacity: 0.9, fontSize: 15, lineHeight: 1.8, display: "flex", flexDirection: "column", gap: 24 }}>
            <p>
              <strong>PMC Solutions AI Inc.</strong> (ci-après « Avenqo », « nous » ou « notre »), entreprise de technologies établie au Québec, Canada, accorde la plus haute priorité à la protection des renseignements personnels et à la sécurité des données d&apos;affaires de ses clients.
            </p>

            <div>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: 8 }}>1. Responsable de la protection des renseignements personnels</h2>
              <p>
                Conformément aux exigences de la <em>Loi sur la protection des renseignements personnels dans le secteur privé</em> (Loi 25 du Québec), le responsable désigné de la protection des renseignements personnels pour Avenqo peut être contacté directement aux coordonnées suivantes :
              </p>
              <ul style={{ listStyleType: "disc", paddingLeft: 24, marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                <li><strong>Entité :</strong> PMC Solutions AI Inc.</li>
                <li><strong>Responsable :</strong> Direction de la conformité et de la sécurité des données</li>
                <li><strong>Courriel dédié :</strong> <a href="mailto:confidentialite@avenqo.ca" style={{ color: "#38bdf8" }}>confidentialite@avenqo.ca</a> (ou <a href="mailto:bonjour@avenqo.ca" style={{ color: "#38bdf8" }}>bonjour@avenqo.ca</a>)</li>
                <li><strong>Adresse :</strong> Montréal, Québec, Canada</li>
              </ul>
            </div>

            <div>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: 8 }}>2. Renseignements collectés et finalités</h2>
              <p>
                Nous recueillons uniquement les renseignements nécessaires aux fins légitimes de prestation de nos services SaaS d&apos;intelligence d&apos;affaires :
              </p>
              <ul style={{ listStyleType: "disc", paddingLeft: 24, marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}>
                <li><strong>Données de compte et d&apos;identité :</strong> prénom, nom, adresse courriel professionnelle, nom d&apos;entreprise, coordonnées de facturation, rôle dans l&apos;organisation.</li>
                <li><strong>Données opérationnelles connectées :</strong> métriques de ventes, catalogues de produits, factures déposées, informations clients synchronisées depuis vos boutiques (Shopify, WooCommerce, Etsy) selon vos autorisations explicites.</li>
                <li><strong>Journaux de sécurité :</strong> adresses IP, empreintes d&apos;accès chiffrées, journaux d&apos;audit pour prévenir les fraudes et assurer la traçabilité exigée par les normes SOC.</li>
              </ul>
            </div>

            <div>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: 8 }}>3. Utilisation des modèles d&apos;intelligence artificielle</h2>
              <p>
                <strong>Principe de non-réutilisation :</strong> Les données, documents et transactions traités pour le compte de votre entreprise ne sont <strong>JAMAIS</strong> utilisés pour entraîner ou affiner des modèles d&apos;intelligence artificielle publics ou partagés avec d&apos;autres clients. Votre propriété intellectuelle et vos données d&apos;affaires demeurent votre propriété exclusive et sont strictement cantonnées à votre environnement d&apos;exécution dédié.
              </p>
            </div>

            <div>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: 8 }}>4. Cloisonnement multi-locataire et mesures de sécurité</h2>
              <p>
                Avenqo implémente une isolation stricte des locataires (multi-tenant data isolation) :
              </p>
              <ul style={{ listStyleType: "disc", paddingLeft: 24, marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}>
                <li><strong>Isolation logique des bases de données :</strong> chaque requête est validée cryptographiquement contre l&apos;identifiant d&apos;organisation (tenant ID) de la session active.</li>
                <li><strong>Chiffrement de bout en bout :</strong> données chiffrées en transit (TLS 1.3 avec HSTS) et données chiffrées au repos (AES-256).</li>
                <li><strong>Protection des accès :</strong> hachage des mots de passe avec l&apos;algorithme résistant Argon2id, jetons de session rotatifs et contrôle d&apos;accès basé sur les rôles (RBAC).</li>
              </ul>
            </div>

            <div>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: 8 }}>5. Vos droits (Loi 25 et LPRPDE)</h2>
              <p>
                Vous bénéficiez des droits légaux suivants sur vos renseignements personnels :
              </p>
              <ul style={{ listStyleType: "disc", paddingLeft: 24, marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}>
                <li>Droit d&apos;accès à vos renseignements et d&apos;obtenir confirmation de leur traitement.</li>
                <li>Droit de rectification si un renseignement est inexact, incomplet ou équivoque.</li>
                <li>Droit à la suppression (« droit à l&apos;oubli ») et à la désindexation sous réserve des obligations fiscales et légales de conservation.</li>
                <li>Droit à la portabilité de vos données dans un format technologique structuré et couramment utilisé (CSV, JSON).</li>
                <li>Droit de retirer votre consentement au traitement à tout moment.</li>
              </ul>
              <p style={{ marginTop: 8 }}>
                Pour exercer l&apos;un de ces droits, transmettez votre demande écrite à <a href="mailto:confidentialite@avenqo.ca" style={{ color: "#38bdf8" }}>confidentialite@avenqo.ca</a>. Une réponse motivée vous sera communiquée dans un délai maximal de 30 jours.
              </p>
            </div>

            <div>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: 8 }}>6. Conservation et destruction des données</h2>
              <p>
                Les renseignements personnels ne sont conservés que le temps nécessaire aux fins prévues au contrat ou prescrit par la législation applicable (notamment les règles fiscales canadiennes prévoyant une conservation de 6 ans pour les pièces comptables). À l&apos;expiration de ces délais, les données sont détruites ou anonymisées selon des protocoles certifiés.
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
