"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  Building2,
  MapPin,
  Users,
  Briefcase,
  UserCheck,
  Search,
  Check,
  Sparkles,
  ShieldCheck,
  ArrowRight,
  Bookmark,
} from "lucide-react";
import { OnboardingWizardLayout } from "@/components/onboarding/onboarding-wizard-layout";
import { getAuthHeaders } from "@/lib/api-headers";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";
import { getOnboardingCopy } from "@/lib/i18n/onboarding-multistep-copy";
import {
  INDUSTRY_CATALOG,
  INDUSTRY_CATEGORIES,
  IndustryItem,
} from "@/components/voice/voice-industry-catalog";

function getSectorRecommendations(sectorName: string) {
  const s = sectorName.toLowerCase();
  if (s.includes("auto") || s.includes("mécani") || s.includes("garage")) {
    return {
      modules: ["Voice IA", "CRM IA", "OCR IA", "Comptabilité IA", "HR AI"],
      benefits: [
        "Réception d'appels 24/7 et qualification de pannes pendant que les mécaniciens sont sous les ponts",
        "Vérification instantanée de compatibilité des pièces par numéro VIN ou modèle",
        "Numérisation OCR immédiate des factures de pièces fournisseurs et bons de livraison",
      ],
      compliance: "Normes environnementales de recyclage des huiles et pièces usagées, devis écrits obligatoires.",
    };
  }
  if (s.includes("construct") || s.includes("bâtiment") || s.includes("rénov")) {
    return {
      modules: ["Voice IA", "CRM IA", "OCR IA", "Comptabilité IA", "HR AI"],
      benefits: [
        "Ne manquez aucun appel client pendant que vous êtes sur un chantier avec du bruit",
        "Qualification des demandes de devis et planification des visites d'estimation",
        "Extraction OCR immédiate des factures de quincaillerie et matériaux",
      ],
      compliance: "Licences RBQ / CCQ (Québec) et obligations légales sur les soumissions écrites.",
    };
  }
  if (s.includes("beaut") || s.includes("coiff") || s.includes("esthét") || s.includes("spa")) {
    return {
      modules: ["Voice IA", "CRM IA", "Marketing IA", "HR AI"],
      benefits: [
        "Réception d'appels et réservation de soins pendant que les coiffeurs sont occupés",
        "Fiches clientes détaillées avec historique des prestations et formules de coloration",
        "Campagnes automatiques de rappel après 6 à 8 semaines d'intervalle",
      ],
      compliance: "Consentement pour les relances promotionnelles par SMS.",
    };
  }
  if (s.includes("santé") || s.includes("médic") || s.includes("clinique")) {
    return {
      modules: ["Voice IA", "CRM IA", "OCR IA", "HR AI"],
      benefits: [
        "Prise et modification de rendez-vous médicaux sans saturer le standard",
        "Rappels automatiques de rendez-vous pour réduire le taux d'absentéisme",
        "Transfert prioritaire vers le personnel soignant qualifié selon protocole",
      ],
      compliance: "Conformité stricte Loi 25 / HIPAA sur la confidentialité des dossiers médicaux.",
    };
  }
  if (s.includes("restau") || s.includes("traiteur") || s.includes("hôtel")) {
    return {
      modules: ["Voice IA", "CRM IA", "Marketing IA", "HR AI"],
      benefits: [
        "Prise de réservations de tables et gestion des arrivées en plein coup de feu",
        "Gestion automatique des allergies alimentaires et régimes spécifiques",
        "Relance de fidélisation pour événements et banquets privés",
      ],
      compliance: "Normes MAPAQ d'hygiène et salubrité alimentaire.",
    };
  }
  if (s.includes("transport") || s.includes("logist")) {
    return {
      modules: ["Voice IA", "CRM IA", "OCR IA", "Comptabilité IA", "HR AI"],
      benefits: [
        "Suivi des livraisons et statut des expéditions communiqué par téléphone aux clients",
        "Extraction OCR automatique des bordereaux de transport (CMR, connaissements)",
        "Affectation optimisée des tournées et disponibilité des chauffeurs",
      ],
      compliance: "Respect des temps de repos réglementaires et contrôle des licences de transport.",
    };
  }
  return {
    modules: ["Retail IA", "CRM IA", "Voice IA", "Comptabilité IA", "Marketing IA", "HR AI"],
    benefits: [
      "Disponibilité des articles en boutique, suivi de commande et prise de messages",
      "Analyse prédictive des ventes et anticipation des ruptures de stock",
      "Réconciliation bancaire automatisée et relances clients intelligentes",
    ],
    compliance: "Conformité taxes de vente (TPS/TVQ) et protection des données clients (Loi 25 / RGPD).",
  };
}

export default function OnboardingCompanyPage() {
  const router = useRouter();
  const { locale } = useLocale();
  const copy = getOnboardingCopy(locale);
  const isFr = locale?.startsWith("fr") ?? true;

  const [isLoading, setIsLoading] = useState(true);
  const [saveStatus, setSaveStatus] = useState<"saving" | "saved" | "idle">("idle");
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [industrySearch, setIndustrySearch] = useState<string>("");
  const [failedImages, setFailedImages] = useState<Record<string, boolean>>({});

  const [formData, setFormData] = useState({
    commercial_name: "",
    legal_name: "",
    country: "Canada",
    region: "Québec",
    timezone: "America/Montreal",
    industry: "Commerce & Détail",
    team_size: "1-10",
    website: "",
    description: "",
    authorized_rep_first_name: "",
    authorized_rep_last_name: "",
    authorized_rep_title: "Président",
  });

  useEffect(() => {
    async function fetchState() {
      try {
        const headers = getAuthHeaders();
        const res = await apiFetch("/api/v1/onboarding/state", { headers });
        if (res.ok) {
          const data = await res.json();
          if (data.company_info) {
            setFormData((prev) => ({
              ...prev,
              commercial_name: data.company_info.commercial_name || prev.commercial_name,
              legal_name: data.company_info.legal_name || prev.legal_name,
              country: data.company_info.country || prev.country,
              region: data.company_info.region || prev.region,
              timezone: data.company_info.timezone || prev.timezone,
              industry: data.company_info.industry || prev.industry,
              team_size: data.company_info.team_size || prev.team_size,
              website: data.company_info.website || prev.website,
              description: data.company_info.description || prev.description,
              authorized_rep_first_name: data.company_info.authorized_rep_first_name || prev.authorized_rep_first_name,
              authorized_rep_last_name: data.company_info.authorized_rep_last_name || prev.authorized_rep_last_name,
              authorized_rep_title: data.company_info.authorized_rep_title || prev.authorized_rep_title,
            }));
          }
        }
      } catch (err) {
        console.error("Erreur de chargement état onboarding:", err);
      } finally {
        setIsLoading(false);
      }
    }
    void fetchState();
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSelectSector = (item: IndustryItem) => {
    setFormData((prev) => ({
      ...prev,
      industry: isFr ? item.nameFr : item.nameEn,
    }));
  };

  const handleSaveAndContinue = async () => {
    setSaveStatus("saving");
    try {
      const headers = getAuthHeaders();
      const res = await apiFetch("/api/v1/onboarding/step/company", {
        method: "PUT",
        headers,
        body: JSON.stringify(formData),
      });
      if (res.ok) {
        setSaveStatus("saved");
        router.push("/onboarding/modules");
      }
    } catch (err) {
      console.error("Erreur lors de la sauvegarde de l'étape:", err);
      setSaveStatus("idle");
    }
  };

  const filteredIndustries = INDUSTRY_CATALOG.filter((item) => {
    if (selectedCategory !== "all" && item.category !== selectedCategory) {
      return false;
    }
    if (industrySearch.trim()) {
      const q = industrySearch.trim().toLowerCase();
      return (
        item.nameFr.toLowerCase().includes(q) ||
        item.nameEn.toLowerCase().includes(q) ||
        item.descFr.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const activeSector =
    INDUSTRY_CATALOG.find(
      (item) =>
        item.nameFr.toLowerCase() === formData.industry.toLowerCase() ||
        item.nameEn.toLowerCase() === formData.industry.toLowerCase() ||
        formData.industry.toLowerCase().includes(item.id.toLowerCase())
    ) || INDUSTRY_CATALOG[3]; // default to Retail

  const recommendations = getSectorRecommendations(formData.industry);

  const isFormValid =
    formData.commercial_name.trim().length >= 2 &&
    formData.authorized_rep_first_name.trim().length >= 1 &&
    formData.authorized_rep_last_name.trim().length >= 1 &&
    formData.industry.trim().length >= 2;

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#060B13] flex items-center justify-center text-slate-400">
        Chargement de l'environnement…
      </div>
    );
  }

  return (
    <OnboardingWizardLayout
      currentStepIndex={1}
      title={copy.company.title}
      subtitle={copy.company.subtitle}
      onNext={() => void handleSaveAndContinue()}
      isNextDisabled={!isFormValid}
      saveStatus={saveStatus}
    >
      <div className="bg-[#0B132B]/80 border border-white/[0.08] rounded-2xl p-6 sm:p-8 space-y-8 shadow-xl">
        {/* Section: Identité commerciale & légale */}
        <div className="border-b border-white/[0.08] pb-6 space-y-4">
          <div className="flex items-center gap-2 text-sm font-bold text-white uppercase tracking-wider">
            <Building2 className="w-4 h-4 text-[#0076FF]" />
            <span>Identité de l'Organisation</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div>
              <label htmlFor="commercial_name" className="block text-xs font-semibold text-slate-300 mb-1.5">
                {copy.company.commercialName} *
              </label>
              <input
                id="commercial_name"
                name="commercial_name"
                type="text"
                required
                value={formData.commercial_name}
                onChange={handleChange}
                placeholder="Ex. Produits Ero Inc."
                className="w-full px-4 py-2.5 rounded-xl bg-slate-900/80 border border-white/10 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-[#0076FF] transition-colors"
              />
            </div>

            <div>
              <label htmlFor="legal_name" className="block text-xs font-semibold text-slate-300 mb-1.5">
                {copy.company.legalName}
              </label>
              <input
                id="legal_name"
                name="legal_name"
                type="text"
                value={formData.legal_name}
                onChange={handleChange}
                placeholder="Ex. 9488-0000 Québec Inc."
                className="w-full px-4 py-2.5 rounded-xl bg-slate-900/80 border border-white/10 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-[#0076FF] transition-colors"
              />
            </div>
          </div>
        </div>

        {/* Section: Territoire & Emplacement */}
        <div className="border-b border-white/[0.08] pb-6 space-y-4">
          <div className="flex items-center gap-2 text-sm font-bold text-white uppercase tracking-wider">
            <MapPin className="w-4 h-4 text-emerald-400" />
            <span>Territoire & Fuseau Horaire</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
            <div>
              <label htmlFor="country" className="block text-xs font-semibold text-slate-300 mb-1.5">
                {copy.company.country}
              </label>
              <select
                id="country"
                name="country"
                value={formData.country}
                onChange={handleChange}
                className="w-full px-3 py-2.5 rounded-xl bg-slate-900/80 border border-white/10 text-white text-sm focus:outline-none focus:border-[#0076FF]"
              >
                <option value="Canada">Canada 🇨🇦</option>
                <option value="États-Unis">États-Unis 🇺🇸</option>
                <option value="France">France 🇫🇷</option>
                <option value="Royaume-Uni">Royaume-Uni 🇬🇧</option>
                <option value="International">Autre / International 🌐</option>
              </select>
            </div>

            <div>
              <label htmlFor="region" className="block text-xs font-semibold text-slate-300 mb-1.5">
                {copy.company.region}
              </label>
              <input
                id="region"
                name="region"
                type="text"
                value={formData.region}
                onChange={handleChange}
                placeholder="Québec, Ontario, etc."
                className="w-full px-4 py-2.5 rounded-xl bg-slate-900/80 border border-white/10 text-white text-sm focus:outline-none focus:border-[#0076FF]"
              />
            </div>

            <div>
              <label htmlFor="timezone" className="block text-xs font-semibold text-slate-300 mb-1.5">
                {copy.company.timezone}
              </label>
              <select
                id="timezone"
                name="timezone"
                value={formData.timezone}
                onChange={handleChange}
                className="w-full px-3 py-2.5 rounded-xl bg-slate-900/80 border border-white/10 text-white text-sm focus:outline-none focus:border-[#0076FF]"
              >
                <option value="America/Montreal">Amérique/Montréal (EST/EDT)</option>
                <option value="America/Toronto">Amérique/Toronto (EST/EDT)</option>
                <option value="America/Vancouver">Amérique/Vancouver (PST/PDT)</option>
                <option value="America/New_York">Amérique/New York (EST/EDT)</option>
                <option value="Europe/Paris">Europe/Paris (CET/CEST)</option>
                <option value="UTC">UTC</option>
              </select>
            </div>
          </div>
        </div>

        {/* ========================================================
            SECTION: CATALOGUE VISUEL DES SECTEURS D'ACTIVITÉ MONDE
            ======================================================== */}
        <div className="border-b border-white/[0.08] pb-8 space-y-5">
          <div className="space-y-1">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <span className="text-lg">🏢</span>
                <h3 className="text-sm font-extrabold text-white uppercase tracking-wider">
                  Secteur d'Activité & Métier (Universel pour le monde entier)
                </h3>
              </div>
              <span className="text-xs font-bold text-[#0076FF] bg-blue-500/10 px-3 py-1 rounded-full border border-blue-500/20">
                Secteur sélectionné : {formData.industry}
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Choisissez votre domaine d'activité. Avenqo adapte automatiquement le vocabulaire, les
              standards opératoires (SOP), le Voice Coach et les recommandations de modules.
            </p>
          </div>

          {/* Search & Category Filter Pills */}
          <div className="space-y-3">
            <div className="relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                type="text"
                value={industrySearch}
                onChange={(e) => setIndustrySearch(e.target.value)}
                placeholder="Rechercher une industrie, mot-clé ou profession (ex: Automobile, Plomberie, Coiffure, Clinique)..."
                className="w-full pl-10 pr-4 py-2.5 rounded-xl text-xs bg-slate-900 border border-white/10 text-white placeholder-slate-500 focus:outline-none focus:border-[#0076FF]"
              />
            </div>

            <div className="flex flex-wrap items-center gap-2 overflow-x-auto pb-1">
              {INDUSTRY_CATEGORIES.map((cat) => (
                <button
                  key={cat.id}
                  type="button"
                  onClick={() => setSelectedCategory(cat.id)}
                  className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition shrink-0 ${
                    selectedCategory === cat.id
                      ? "bg-[#0076FF] text-white shadow-sm shadow-blue-500/30"
                      : "bg-slate-900 text-slate-400 hover:text-white border border-white/[0.06] hover:border-white/20"
                  }`}
                >
                  {isFr ? cat.labelFr : cat.labelEn}
                </button>
              ))}
            </div>
          </div>

          {/* Responsive 16-Cards Photography Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 max-h-[480px] overflow-y-auto pr-1">
            {filteredIndustries.map((ind) => {
              const title = isFr ? ind.nameFr : ind.nameEn;
              const desc = isFr ? ind.descFr : ind.descEn;
              const isSelected =
                formData.industry.toLowerCase() === title.toLowerCase() ||
                formData.industry.toLowerCase().includes(ind.id.toLowerCase());
              const isImgFailed = failedImages[ind.id] || false;

              return (
                <div
                  key={ind.id}
                  onClick={() => handleSelectSector(ind)}
                  className={`group relative rounded-2xl overflow-hidden border cursor-pointer transition flex flex-col justify-between ${
                    isSelected
                      ? "border-[#0076FF] ring-2 ring-blue-500/40 bg-slate-900/90 shadow-lg shadow-blue-500/10"
                      : "border-white/10 bg-slate-900/50 hover:border-white/20 hover:bg-slate-900"
                  }`}
                >
                  <div className="relative h-28 w-full overflow-hidden bg-slate-950">
                    <img
                      src={isImgFailed ? ind.fallbackSvg : ind.image}
                      alt={title}
                      onError={(e) => {
                        const target = e.currentTarget as HTMLImageElement;
                        target.onerror = null;
                        setFailedImages((prev) => ({ ...prev, [ind.id]: true }));
                        target.src = ind.fallbackSvg;
                      }}
                      className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent" />
                    {isSelected ? (
                      <div className="absolute top-2.5 right-2.5 p-1 rounded-md bg-[#0076FF] text-white shadow-md">
                        <Check className="w-4 h-4" />
                      </div>
                    ) : (
                      <div className="absolute top-2.5 right-2.5 p-1 rounded-md bg-black/60 text-white/80">
                        <Bookmark className="w-3.5 h-3.5" />
                      </div>
                    )}
                  </div>
                  <div className="p-3.5 space-y-1">
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm shrink-0">{ind.icon}</span>
                      <h4 className="font-bold text-xs text-white truncate">{title}</h4>
                    </div>
                    <p className="text-[11px] text-slate-400 leading-snug line-clamp-2">
                      {desc}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>

          {/* ACTIVE SECTOR REASSURANCE & RECOMMENDED MODULES PANEL */}
          <div className="p-5 rounded-2xl bg-gradient-to-br from-[#0B1536] to-[#0A1026] border border-blue-500/20 space-y-4 shadow-lg">
            <div className="flex items-start justify-between flex-wrap gap-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-blue-600/20 border border-blue-500/30 text-white flex items-center justify-center text-xl shrink-0">
                  {activeSector.icon}
                </div>
                <div>
                  <h4 className="text-sm font-bold text-white flex items-center gap-2">
                    <span>{formData.industry}</span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold uppercase bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      Vérifié
                    </span>
                  </h4>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {isFr ? activeSector.descFr : activeSector.descEn}
                  </p>
                </div>
              </div>

              {/* Badges Modules recommandés */}
              <div className="space-y-1.5 sm:text-right">
                <span className="text-[10px] uppercase font-extrabold tracking-wider text-slate-400 block">
                  Modules Recommandés pour votre secteur
                </span>
                <div className="flex flex-wrap sm:justify-end gap-1.5">
                  {recommendations.modules.map((m) => (
                    <span
                      key={m}
                      className="px-2.5 py-1 rounded-lg text-xs font-bold bg-[#0076FF]/20 text-blue-300 border border-[#0076FF]/40"
                    >
                      {m}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Bénéfices métiers concrets */}
            <div className="border-t border-white/[0.06] pt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
              {recommendations.benefits.map((benefit, idx) => (
                <div key={idx} className="flex items-start gap-2 text-xs text-slate-300">
                  <Check className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                  <span className="leading-snug">{benefit}</span>
                </div>
              ))}
            </div>

            {/* Conformité & Sécurité */}
            <div className="border-t border-white/[0.06] pt-3 flex items-center gap-2 text-xs text-emerald-400/90 font-medium">
              <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
              <span>Conformité & Sécurité : {recommendations.compliance}</span>
            </div>
          </div>
        </div>

        {/* Section: Taille d'équipe, site et description */}
        <div className="border-b border-white/[0.08] pb-6 space-y-4">
          <div className="flex items-center gap-2 text-sm font-bold text-white uppercase tracking-wider">
            <Users className="w-4 h-4 text-amber-400" />
            <span>Équipe & Présentation</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            <div>
              <label htmlFor="team_size" className="block text-xs font-semibold text-slate-300 mb-1.5">
                {copy.company.teamSize}
              </label>
              <select
                id="team_size"
                name="team_size"
                value={formData.team_size}
                onChange={handleChange}
                className="w-full px-3 py-2.5 rounded-xl bg-slate-900/80 border border-white/10 text-white text-sm focus:outline-none focus:border-[#0076FF]"
              >
                <option value="1-5">1 à 5 employés</option>
                <option value="6-20">6 à 20 employés</option>
                <option value="21-50">21 à 50 employés</option>
                <option value="50+">Plus de 50 employés</option>
              </select>
            </div>

            <div>
              <label htmlFor="website" className="block text-xs font-semibold text-slate-300 mb-1.5">
                {copy.company.website}
              </label>
              <input
                id="website"
                name="website"
                type="url"
                value={formData.website}
                onChange={handleChange}
                placeholder="https://eroproduits.com"
                className="w-full px-4 py-2.5 rounded-xl bg-slate-900/80 border border-white/10 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-[#0076FF]"
              />
            </div>
          </div>

          <div>
            <label htmlFor="description" className="block text-xs font-semibold text-slate-300 mb-1.5">
              {copy.company.description}
            </label>
            <textarea
              id="description"
              name="description"
              rows={2}
              value={formData.description}
              onChange={handleChange}
              placeholder="Présentez brièvement vos activités et les processus que vous souhaitez accélérer avec Avenqo IA."
              className="w-full px-4 py-2.5 rounded-xl bg-slate-900/80 border border-white/10 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-[#0076FF] resize-none"
            />
          </div>
        </div>

        {/* Section: Représentant légal autorisé */}
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-sm font-bold text-white uppercase tracking-wider">
            <UserCheck className="w-4 h-4 text-purple-400" />
            <span>Responsable Autorisé (Signataire)</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
            <div>
              <label htmlFor="authorized_rep_first_name" className="block text-xs font-semibold text-slate-300 mb-1.5">
                {copy.company.repFirstName} *
              </label>
              <input
                id="authorized_rep_first_name"
                name="authorized_rep_first_name"
                type="text"
                required
                value={formData.authorized_rep_first_name}
                onChange={handleChange}
                placeholder="Prénom"
                className="w-full px-4 py-2.5 rounded-xl bg-slate-900/80 border border-white/10 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-[#0076FF]"
              />
            </div>

            <div>
              <label htmlFor="authorized_rep_last_name" className="block text-xs font-semibold text-slate-300 mb-1.5">
                {copy.company.repLastName} *
              </label>
              <input
                id="authorized_rep_last_name"
                name="authorized_rep_last_name"
                type="text"
                required
                value={formData.authorized_rep_last_name}
                onChange={handleChange}
                placeholder="Nom"
                className="w-full px-4 py-2.5 rounded-xl bg-slate-900/80 border border-white/10 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-[#0076FF]"
              />
            </div>

            <div>
              <label htmlFor="authorized_rep_title" className="block text-xs font-semibold text-slate-300 mb-1.5">
                {copy.company.repTitle}
              </label>
              <input
                id="authorized_rep_title"
                name="authorized_rep_title"
                type="text"
                value={formData.authorized_rep_title}
                onChange={handleChange}
                placeholder="Ex. Président, Propriétaire"
                className="w-full px-4 py-2.5 rounded-xl bg-slate-900/80 border border-white/10 text-white text-sm focus:outline-none focus:border-[#0076FF]"
              />
            </div>
          </div>
        </div>
      </div>
    </OnboardingWizardLayout>
  );
}
