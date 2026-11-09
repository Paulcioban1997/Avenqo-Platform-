"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  FileText,
  Shield,
  CheckCircle2,
  Lock,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  UserCheck,
} from "lucide-react";
import { OnboardingWizardLayout } from "@/components/onboarding/onboarding-wizard-layout";
import { getAuthHeaders } from "@/lib/api-headers";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";
import { getOnboardingCopy } from "@/lib/i18n/onboarding-multistep-copy";

interface ContractDoc {
  type: string;
  title: string;
  version: string;
  isMandatory: boolean;
  summary: string;
  sampleClauses: string[];
}

const CONTRACT_DOCUMENTS: ContractDoc[] = [
  {
    type: "terms_of_service",
    title: "Conditions Générales d'Utilisation de la Plateforme Avenqo",
    version: "2026.1",
    isMandatory: true,
    summary:
      "Règles d'utilisation des services d'intelligence artificielle, hébergement souverain, sécurité des accès API et disponibilité des services SaaS.",
    sampleClauses: [
      "Article 1 — Propriété des Données Locataires : Le client demeure l'unique et exclusif titulaire de l'ensemble des données brutes, catalogues, commandes et fichiers importés.",
      "Article 2 — Confidentialité et Non-Entraînement Externe : Aucune donnée locataire n'est utilisée pour entraîner des modèles publics ou partagée avec d'autres entreprises.",
      "Article 3 — Niveau de Service & Continuité : Avenqo s'engage sur un taux de disponibilité cible de 99,9% des API opérationnelles.",
    ],
  },
  {
    type: "saas_subscription",
    title: "Contrat d'Abonnement SaaS d'Entreprise PMC Solutions AI",
    version: "2026.1",
    isMandatory: true,
    summary:
      "Conditions commerciales régissant la souscription logicielle, les droits d'accès aux modules autorisés, l'attribution des crédits IA et le renouvellement régulier.",
    sampleClauses: [
      "Article 1 — Octroi de Licence d'Accès : PMC Solutions AI concède au locataire une licence d'accès SaaS mondiale, non exclusive et sécurisée pour ses modules souscrits.",
      "Article 2 — Modalités de Facturation : Les abonnements sont facturés d'avance mensuellement via Stripe. Les crédits IA sont réapprovisionnés à chaque période.",
      "Article 3 — Résiliation sans pénalité : L'abonnement peut être résilié à tout moment depuis l'espace de gestion sans frais de sortie.",
    ],
  },
  {
    type: "privacy_policy",
    title: "Politique de Confidentialité & Addenda Protection des Données (Loi 25 / PIPEDA)",
    version: "2026.1",
    isMandatory: true,
    summary:
      "Conformité rigoureuse avec la Loi 25 du Québec, la LPRPDE (PIPEDA) canadienne et le RGPD européen. Chiffrement au repos et en transit.",
    sampleClauses: [
      "Article 1 — Chiffrement et Cloisonnement Multi-Tenant : Chiffrement AES-256 au repos et TLS 1.3 en transit, avec isolation fail-closed au niveau de la base PostgreSQL.",
      "Article 2 — Délégué à la Protection des Données : Droit d'accès, de rectification et d'effacement intégral sur simple demande depuis les paramètres de l'entreprise.",
    ],
  },
  {
    type: "nda",
    title: "Accord de Confidentialité Mutuel d'Entreprise (Mutual NDA)",
    version: "2026.1",
    isMandatory: false,
    summary:
      "Protection réciproque du secret d'affaires, des algorithmes d'analyse et des secrets industriels échangés entre les parties.",
    sampleClauses: [
      "Article 1 — Réciprocité de Confidentialité : Chacune des parties s'engage à préserver le caractère confidentiel des informations échangées pendant 5 ans.",
    ],
  },
];

export default function OnboardingContractsPage() {
  const router = useRouter();
  const { locale } = useLocale();
  const copy = getOnboardingCopy(locale);

  const [isLoading, setIsLoading] = useState(true);
  const [saveStatus, setSaveStatus] = useState<"saving" | "saved" | "idle">("idle");
  const [expandedDoc, setExpandedDoc] = useState<string | null>("terms_of_service");

  const [acceptedContracts, setAcceptedContracts] = useState<string[]>([]);
  const [marketingConsent, setMarketingConsent] = useState(false);
  const [signatoryName, setSignatoryName] = useState("");
  const [signatoryTitle, setSignatoryTitle] = useState("Président");

  useEffect(() => {
    async function fetchState() {
      try {
        const headers = getAuthHeaders();
        const res = await apiFetch("/api/v1/onboarding/state", { headers });
        if (res.ok) {
          const data = await res.json();
          if (data.company_info?.authorized_rep_first_name) {
            setSignatoryName(
              `${data.company_info.authorized_rep_first_name} ${data.company_info.authorized_rep_last_name || ""}`.trim()
            );
            if (data.company_info.authorized_rep_title) {
              setSignatoryTitle(data.company_info.authorized_rep_title);
            }
          }
          if (data.contracts?.accepted_contract_types) {
            setAcceptedContracts(data.contracts.accepted_contract_types);
          }
        }
      } catch (err) {
        console.error("Erreur de chargement contrats:", err);
      } finally {
        setIsLoading(false);
      }
    }
    void fetchState();
  }, []);

  const toggleContract = (type: string) => {
    setAcceptedContracts((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    );
  };

  const handleSaveAndContinue = async () => {
    setSaveStatus("saving");
    try {
      const headers = getAuthHeaders();
      const res = await apiFetch("/api/v1/onboarding/step/contracts", {
        method: "PUT",
        headers,
        body: JSON.stringify({
          accepted_contract_types: acceptedContracts,
          accepted_by_name: signatoryName,
          accepted_by_title: signatoryTitle,
          marketing_consent: marketingConsent,
        }),
      });
      if (res.ok) {
        setSaveStatus("saved");
        router.push("/onboarding/subscription");
      }
    } catch (err) {
      console.error("Erreur d'acceptation des contrats:", err);
      setSaveStatus("idle");
    }
  };

  const mandatoryTypes = CONTRACT_DOCUMENTS.filter((c) => c.isMandatory).map((c) => c.type);
  const allMandatoryAccepted = mandatoryTypes.every((t) => acceptedContracts.includes(t));
  const isFormValid = allMandatoryAccepted && signatoryName.trim().length >= 2;

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#060B13] flex items-center justify-center text-slate-400">
        Chargement des documents juridiques…
      </div>
    );
  }

  return (
    <OnboardingWizardLayout
      currentStepIndex={5}
      title={copy.contracts.title}
      subtitle={copy.contracts.subtitle}
      onNext={() => void handleSaveAndContinue()}
      nextLabel="Valider & Choisir l'Abonnement"
      isNextDisabled={!isFormValid}
      saveStatus={saveStatus}
    >
      <div className="space-y-6">
        {/* Security badge */}
        <div className="p-4 rounded-2xl bg-[#0B132B]/80 border border-white/[0.08] flex items-center gap-3">
          <Shield className="w-5 h-5 text-emerald-400 shrink-0" />
          <p className="text-xs text-slate-300">
            Conformité juridique vérifiée selon les lois applicables au Québec et au Canada (Loi 25,
            LPRPDE / PIPEDA). Vos consentements sont horodatés en UTC et associés à votre identifiant
            locataire.
          </p>
        </div>

        {/* Documents List */}
        <div className="space-y-4">
          {CONTRACT_DOCUMENTS.map((doc) => {
            const isAccepted = acceptedContracts.includes(doc.type);
            const isExpanded = expandedDoc === doc.type;

            return (
              <div
                key={doc.type}
                className={`rounded-2xl border transition-all ${
                  isAccepted
                    ? "bg-[#0B132B] border-emerald-500/40 shadow-sm"
                    : "bg-[#0B132B]/60 border-white/[0.08]"
                }`}
              >
                <div className="p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="flex items-start gap-3.5">
                    <div
                      className={`p-2.5 rounded-xl shrink-0 mt-0.5 ${
                        isAccepted
                          ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                          : "bg-white/[0.04] text-slate-400 border border-white/[0.06]"
                      }`}
                    >
                      <FileText className="w-5 h-5" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-bold text-white text-sm">{doc.title}</h3>
                        {doc.isMandatory ? (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-500/15 text-blue-400 border border-blue-500/25 font-semibold uppercase">
                            Obligatoire
                          </span>
                        ) : (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-white/10 font-semibold uppercase">
                            Facultatif
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-slate-400 mt-1 max-w-2xl">{doc.summary}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 shrink-0 self-end sm:self-center">
                    <button
                      type="button"
                      onClick={() => setExpandedDoc(isExpanded ? null : doc.type)}
                      className="px-3 py-1.5 rounded-lg border border-white/10 text-xs text-slate-300 hover:text-white flex items-center gap-1.5 transition-colors cursor-pointer"
                    >
                      <span>{isExpanded ? "Masquer" : "Consulter"}</span>
                      {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    </button>

                    <label className="flex items-center gap-2 cursor-pointer select-none">
                      <input
                        type="checkbox"
                        checked={isAccepted}
                        onChange={() => toggleContract(doc.type)}
                        className="w-4 h-4 rounded text-[#0076FF] bg-slate-900 border-white/20 focus:ring-0 focus:ring-offset-0 cursor-pointer"
                      />
                      <span className="text-xs font-semibold text-slate-200">
                        Accepter
                      </span>
                    </label>
                  </div>
                </div>

                {/* Expanded Document Viewer */}
                {isExpanded && (
                  <div className="px-5 pb-5 pt-2 border-t border-white/[0.06] bg-black/20 text-xs text-slate-300 space-y-3">
                    <div className="text-[11px] font-mono text-slate-400">
                      Version officielle : {doc.version} · Juridiction : Québec / Canada · Entité légale : PMC Solutions AI Inc.
                    </div>
                    <div className="space-y-2 bg-slate-900/60 p-4 rounded-xl border border-white/[0.06] font-mono text-[11px] leading-relaxed">
                      {doc.sampleClauses.map((clause, idx) => (
                        <p key={idx} className="text-slate-300">
                          {clause}
                        </p>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Marketing Consent Checkbox */}
        <div className="p-4 rounded-xl bg-white/[0.02] border border-white/[0.06]">
          <label className="flex items-start gap-3 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={marketingConsent}
              onChange={(e) => setMarketingConsent(e.target.checked)}
              className="w-4 h-4 rounded text-[#0076FF] bg-slate-900 border-white/20 focus:ring-0 mt-0.5 cursor-pointer"
            />
            <span className="text-xs text-slate-400 leading-relaxed">
              {copy.contracts.marketingConsent}
            </span>
          </label>
        </div>

        {/* Signatory Confirmation Box */}
        <div className="p-6 rounded-2xl bg-[#0B132B]/80 border border-white/[0.08] space-y-4">
          <div className="flex items-center gap-2 text-sm font-bold text-white uppercase tracking-wider">
            <UserCheck className="w-4 h-4 text-purple-400" />
            <span>Confirmation du Signataire Autorisé</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label htmlFor="signatory_name" className="block text-xs font-semibold text-slate-300 mb-1.5">
                Nom complet du signataire *
              </label>
              <input
                id="signatory_name"
                type="text"
                required
                value={signatoryName}
                onChange={(e) => setSignatoryName(e.target.value)}
                className="w-full px-4 py-2.5 rounded-xl bg-slate-900 border border-white/10 text-white text-sm focus:outline-none focus:border-[#0076FF]"
              />
            </div>

            <div>
              <label htmlFor="signatory_title" className="block text-xs font-semibold text-slate-300 mb-1.5">
                Fonction légale *
              </label>
              <input
                id="signatory_title"
                type="text"
                required
                value={signatoryTitle}
                onChange={(e) => setSignatoryTitle(e.target.value)}
                className="w-full px-4 py-2.5 rounded-xl bg-slate-900 border border-white/10 text-white text-sm focus:outline-none focus:border-[#0076FF]"
              />
            </div>
          </div>
        </div>
      </div>
    </OnboardingWizardLayout>
  );
}

