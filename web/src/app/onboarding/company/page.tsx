"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Building2, Globe, MapPin, Users, Briefcase, UserCheck, FileText, CheckCircle2 } from "lucide-react";
import { OnboardingWizardLayout } from "@/components/onboarding/onboarding-wizard-layout";
import { getAuthHeaders } from "@/lib/api-headers";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";
import { getOnboardingCopy } from "@/lib/i18n/onboarding-multistep-copy";

export default function OnboardingCompanyPage() {
  const router = useRouter();
  const { locale } = useLocale();
  const copy = getOnboardingCopy(locale);

  const [isLoading, setIsLoading] = useState(true);
  const [saveStatus, setSaveStatus] = useState<"saving" | "saved" | "idle">("idle");
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

  const isFormValid =
    formData.commercial_name.trim().length >= 2 &&
    formData.authorized_rep_first_name.trim().length >= 1 &&
    formData.authorized_rep_last_name.trim().length >= 1;

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
      <div className="bg-[#0B132B]/80 border border-white/[0.08] rounded-2xl p-6 sm:p-8 space-y-6 shadow-xl">
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
                placeholder="Ex. Boutique Royale Inc."
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

        {/* Section: Localisation et secteur */}
        <div className="border-b border-white/[0.08] pb-6 space-y-4">
          <div className="flex items-center gap-2 text-sm font-bold text-white uppercase tracking-wider">
            <MapPin className="w-4 h-4 text-emerald-400" />
            <span>Territoire & Exploitation</span>
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
                <option value="Canada">Canada</option>
                <option value="États-Unis">États-Unis</option>
                <option value="France">France</option>
                <option value="Royaume-Uni">Royaume-Uni</option>
                <option value="International">Autre / International</option>
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

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-5 pt-2">
            <div>
              <label htmlFor="industry" className="block text-xs font-semibold text-slate-300 mb-1.5">
                {copy.company.industry}
              </label>
              <select
                id="industry"
                name="industry"
                value={formData.industry}
                onChange={handleChange}
                className="w-full px-3 py-2.5 rounded-xl bg-slate-900/80 border border-white/10 text-white text-sm focus:outline-none focus:border-[#0076FF]"
              >
                <option value="Commerce & Détail">Commerce & Vente au détail</option>
                <option value="Services Professionnels">Services Professionnels & Conseil</option>
                <option value="Technologies & SaaS">Technologies & Logiciel</option>
                <option value="Santé & Clinique">Santé & Bien-être</option>
                <option value="Manufacture & Distribution">Manufacture & Logistique</option>
                <option value="Autre">Autre secteur</option>
              </select>
            </div>

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
                placeholder="https://entreprise.ca"
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
                placeholder="Ex. Président, Dirigeant"
                className="w-full px-4 py-2.5 rounded-xl bg-slate-900/80 border border-white/10 text-white text-sm focus:outline-none focus:border-[#0076FF]"
              />
            </div>
          </div>
        </div>
      </div>
    </OnboardingWizardLayout>
  );
}
