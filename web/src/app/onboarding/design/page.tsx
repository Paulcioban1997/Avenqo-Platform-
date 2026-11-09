"use client";

import React, { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  Palette,
  Upload,
  Image as ImageIcon,
  RotateCcw,
  Sparkles,
  Check,
  Moon,
  Sun,
  Layers,
  ShoppingBag,
  TrendingUp,
  Bot,
  Building2,
} from "lucide-react";
import { OnboardingWizardLayout } from "@/components/onboarding/onboarding-wizard-layout";
import { CANDIDATE_THEMES, DEFAULT_THEME, ThemeDefinition } from "@/lib/themes/theme-catalog";
import { getAuthHeaders } from "@/lib/api-headers";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";
import { getOnboardingCopy } from "@/lib/i18n/onboarding-multistep-copy";

export default function OnboardingDesignPage() {
  const router = useRouter();
  const { locale } = useLocale();
  const copy = getOnboardingCopy(locale);

  const [isLoading, setIsLoading] = useState(true);
  const [saveStatus, setSaveStatus] = useState<"saving" | "saved" | "idle">("idle");
  const [isUploadingLogo, setIsUploadingLogo] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const logoInputRef = useRef<HTMLInputElement>(null);
  const emblemInputRef = useRef<HTMLInputElement>(null);

  const [designState, setDesignState] = useState({
    theme_id: DEFAULT_THEME.id,
    primary_color: DEFAULT_THEME.primary_color,
    secondary_color: DEFAULT_THEME.secondary_color,
    accent_color: DEFAULT_THEME.accent_color,
    mode: DEFAULT_THEME.mode as "dark" | "light",
    background_style: DEFAULT_THEME.background_style,
    company_logo_url: "",
    company_emblem_url: "",
    display_name: "",
  });

  useEffect(() => {
    async function fetchState() {
      try {
        const headers = getAuthHeaders();
        const res = await apiFetch("/api/v1/onboarding/state", { headers });
        if (res.ok) {
          const data = await res.json();
          if (data.design) {
            setDesignState((prev) => ({
              ...prev,
              theme_id: data.design.theme_id || prev.theme_id,
              primary_color: data.design.primary_color || prev.primary_color,
              secondary_color: data.design.secondary_color || prev.secondary_color,
              accent_color: data.design.accent_color || prev.accent_color,
              mode: data.design.mode || prev.mode,
              background_style: data.design.background_style || prev.background_style,
              company_logo_url: data.design.company_logo_url || prev.company_logo_url,
              company_emblem_url: data.design.company_emblem_url || prev.company_emblem_url,
              display_name: data.design.display_name || data.company_info?.commercial_name || prev.display_name,
            }));
          }
        }
      } catch (err) {
        console.error("Erreur de chargement design:", err);
      } finally {
        setIsLoading(false);
      }
    }
    void fetchState();
  }, []);

  const handleSelectTheme = (theme: ThemeDefinition) => {
    setDesignState((prev) => ({
      ...prev,
      theme_id: theme.id,
      primary_color: theme.primary_color,
      secondary_color: theme.secondary_color,
      accent_color: theme.accent_color,
      mode: theme.mode,
      background_style: theme.background_style,
    }));
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>, field: "company_logo_url" | "company_emblem_url") => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.size > 5 * 1024 * 1024) {
      setUploadError("Le fichier ne doit pas dépasser 5 Mo.");
      return;
    }

    setUploadError(null);
    setIsUploadingLogo(true);
    try {
      const headers = getAuthHeaders() as Record<string, string>;
      const body = new FormData();
      body.append("file", file);

      const res = await fetch("/api/v1/onboarding/upload-asset", {
        method: "POST",
        headers: {
          Authorization: headers["Authorization"] || headers["authorization"] || "",
        },
        body,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Échec du téléversement");
      }

      const resData = await res.json();
      setDesignState((prev) => ({
        ...prev,
        [field]: resData.asset_url,
      }));
    } catch (err: any) {
      setUploadError(err.message || "Erreur de téléversement");
    } finally {
      setIsUploadingLogo(false);
    }
  };

  const handleResetTheme = () => {
    setDesignState((prev) => ({
      ...prev,
      theme_id: DEFAULT_THEME.id,
      primary_color: DEFAULT_THEME.primary_color,
      secondary_color: DEFAULT_THEME.secondary_color,
      accent_color: DEFAULT_THEME.accent_color,
      mode: DEFAULT_THEME.mode,
      background_style: DEFAULT_THEME.background_style,
    }));
  };

  const handleSaveAndContinue = async () => {
    setSaveStatus("saving");
    try {
      const headers = getAuthHeaders();
      const res = await apiFetch("/api/v1/onboarding/step/design", {
        method: "PUT",
        headers,
        body: JSON.stringify(designState),
      });
      if (res.ok) {
        setSaveStatus("saved");
        router.push("/onboarding/preview");
      }
    } catch (err) {
      console.error("Erreur de sauvegarde design:", err);
      setSaveStatus("idle");
    }
  };

  const approvedPresets = CANDIDATE_THEMES.filter((t) => t.is_active_preset);
  const otherThemes = CANDIDATE_THEMES.filter((t) => !t.is_active_preset);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#060B13] flex items-center justify-center text-slate-400">
        Chargement du studio de personnalisation…
      </div>
    );
  }

  return (
    <OnboardingWizardLayout
      currentStepIndex={3}
      title={copy.design.title}
      subtitle={copy.design.subtitle}
      onNext={() => void handleSaveAndContinue()}
      nextLabel="Voir l'Aperçu Interactif"
      saveStatus={saveStatus}
    >
      <div className="space-y-8">
        {/* Approved Presets Section */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm font-bold text-white uppercase tracking-wider">
              <Sparkles className="w-4 h-4 text-[#00D4FF]" />
              <span>{copy.design.approvedPresetsTitle}</span>
            </div>
            <button
              type="button"
              onClick={handleResetTheme}
              className="text-xs text-slate-400 hover:text-white flex items-center gap-1.5 transition-colors cursor-pointer"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>{copy.design.resetTheme}</span>
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {approvedPresets.map((theme) => {
              const isSelected = designState.theme_id === theme.id;
              return (
                <div
                  key={theme.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => handleSelectTheme(theme)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      handleSelectTheme(theme);
                    }
                  }}
                  className={`p-4 rounded-2xl border transition-all text-left flex flex-col justify-between cursor-pointer select-none ${
                    isSelected
                      ? "bg-[#0B132B] border-[#0076FF] shadow-lg shadow-blue-500/20 ring-2 ring-[#0076FF]"
                      : "bg-[#0B132B]/60 border-white/[0.08] hover:border-white/20 hover:bg-[#0B132B]"
                  }`}
                >
                  <div>
                    {/* Visual Theme Palette Swatch */}
                    <div
                      className="h-20 rounded-xl mb-3 p-3 flex flex-col justify-between relative overflow-hidden border border-white/10"
                      style={{ background: theme.preview_gradient }}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-black/40 backdrop-blur-sm text-white">
                          {theme.mode === "dark" ? "Sombre" : "Clair"}
                        </span>
                        {isSelected && (
                          <span className="w-5 h-5 rounded-full bg-[#0076FF] text-white flex items-center justify-center text-xs">
                            <Check className="w-3 h-3 stroke-[3]" />
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-1.5">
                        <span
                          className="w-3.5 h-3.5 rounded-full border border-white/30"
                          style={{ backgroundColor: theme.primary_color }}
                          title="Primaire"
                        />
                        <span
                          className="w-3.5 h-3.5 rounded-full border border-white/30"
                          style={{ backgroundColor: theme.secondary_color }}
                          title="Secondaire"
                        />
                        <span
                          className="w-3.5 h-3.5 rounded-full border border-white/30"
                          style={{ backgroundColor: theme.accent_color }}
                          title="Accent"
                        />
                      </div>
                    </div>

                    <h4 className="font-bold text-white text-sm">{theme.name}</h4>
                    <p className="text-xs text-slate-400 mt-1 line-clamp-2 leading-relaxed">
                      {theme.description}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* 10 Additional Candidate Themes (Collapsible / Expandable) */}
        <details className="group border border-white/[0.08] rounded-2xl bg-[#0B132B]/40 p-5">
          <summary className="flex items-center justify-between text-xs font-semibold text-slate-300 hover:text-white cursor-pointer select-none">
            <span className="flex items-center gap-2">
              <Palette className="w-4 h-4 text-purple-400" />
              <span>{copy.design.candidateThemesTitle}</span>
            </span>
            <span className="text-blue-400 text-[11px] group-open:hidden">
              Afficher les 10 autres styles
            </span>
          </summary>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5 pt-4">
            {otherThemes.map((theme) => {
              const isSelected = designState.theme_id === theme.id;
              return (
                <div
                  key={theme.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => handleSelectTheme(theme)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      handleSelectTheme(theme);
                    }
                  }}
                  className={`p-3.5 rounded-xl border transition-all text-left flex flex-col justify-between cursor-pointer ${
                    isSelected
                      ? "bg-[#0B132B] border-[#0076FF] shadow-sm ring-1 ring-[#0076FF]"
                      : "bg-white/[0.02] border-white/[0.06] hover:border-white/20"
                  }`}
                >
                  <div
                    className="h-14 rounded-lg mb-2 p-2 flex items-start justify-between border border-white/10"
                    style={{ background: theme.preview_gradient }}
                  >
                    <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-black/40 text-white">
                      {theme.mode}
                    </span>
                    {isSelected && <Check className="w-3.5 h-3.5 text-white" />}
                  </div>
                  <div>
                    <h5 className="font-bold text-white text-xs">{theme.name}</h5>
                    <p className="text-[10px] text-slate-400 line-clamp-1 mt-0.5">{theme.description}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </details>

        {/* Fine-Tuning Colors & Logos */}
        <div className="bg-[#0B132B]/80 border border-white/[0.08] rounded-2xl p-6 sm:p-8 space-y-6">
          <div className="flex items-center gap-2 text-sm font-bold text-white uppercase tracking-wider">
            <Palette className="w-4 h-4 text-emerald-400" />
            <span>{copy.design.customColors}</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
            <div>
              <label htmlFor="primary_color" className="block text-xs font-semibold text-slate-300 mb-2">
                {copy.design.primaryColor}
              </label>
              <div className="flex items-center gap-3">
                <input
                  id="primary_color"
                  type="color"
                  value={designState.primary_color}
                  onChange={(e) =>
                    setDesignState((prev) => ({ ...prev, primary_color: e.target.value }))
                  }
                  className="w-10 h-10 rounded-xl bg-transparent border border-white/20 cursor-pointer"
                />
                <input
                  type="text"
                  value={designState.primary_color}
                  onChange={(e) =>
                    setDesignState((prev) => ({ ...prev, primary_color: e.target.value }))
                  }
                  className="flex-1 px-3 py-2 rounded-xl bg-slate-900 border border-white/10 text-xs text-white font-mono"
                />
              </div>
            </div>

            <div>
              <label htmlFor="secondary_color" className="block text-xs font-semibold text-slate-300 mb-2">
                {copy.design.secondaryColor}
              </label>
              <div className="flex items-center gap-3">
                <input
                  id="secondary_color"
                  type="color"
                  value={designState.secondary_color}
                  onChange={(e) =>
                    setDesignState((prev) => ({ ...prev, secondary_color: e.target.value }))
                  }
                  className="w-10 h-10 rounded-xl bg-transparent border border-white/20 cursor-pointer"
                />
                <input
                  type="text"
                  value={designState.secondary_color}
                  onChange={(e) =>
                    setDesignState((prev) => ({ ...prev, secondary_color: e.target.value }))
                  }
                  className="flex-1 px-3 py-2 rounded-xl bg-slate-900 border border-white/10 text-xs text-white font-mono"
                />
              </div>
            </div>

            <div>
              <label htmlFor="accent_color" className="block text-xs font-semibold text-slate-300 mb-2">
                {copy.design.accentColor}
              </label>
              <div className="flex items-center gap-3">
                <input
                  id="accent_color"
                  type="color"
                  value={designState.accent_color}
                  onChange={(e) =>
                    setDesignState((prev) => ({ ...prev, accent_color: e.target.value }))
                  }
                  className="w-10 h-10 rounded-xl bg-transparent border border-white/20 cursor-pointer"
                />
                <input
                  type="text"
                  value={designState.accent_color}
                  onChange={(e) =>
                    setDesignState((prev) => ({ ...prev, accent_color: e.target.value }))
                  }
                  className="flex-1 px-3 py-2 rounded-xl bg-slate-900 border border-white/10 text-xs text-white font-mono"
                />
              </div>
            </div>
          </div>

          {/* Mode Sombre / Clair */}
          <div className="pt-4 border-t border-white/[0.08] flex items-center gap-4">
            <span className="text-xs font-semibold text-slate-300">Mode d'affichage :</span>
            <div className="flex items-center gap-2 bg-slate-900/80 p-1 rounded-xl border border-white/10">
              <button
                type="button"
                onClick={() => setDesignState((prev) => ({ ...prev, mode: "dark" }))}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors ${
                  designState.mode === "dark"
                    ? "bg-[#0076FF] text-white"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                <Moon className="w-3.5 h-3.5" />
                <span>{copy.design.modeDark}</span>
              </button>

              <button
                type="button"
                onClick={() => setDesignState((prev) => ({ ...prev, mode: "light" }))}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors ${
                  designState.mode === "light"
                    ? "bg-[#0076FF] text-white"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                <Sun className="w-3.5 h-3.5" />
                <span>{copy.design.modeLight}</span>
              </button>
            </div>
          </div>

          {/* Logo & Emblème Upload */}
          <div className="pt-4 border-t border-white/[0.08] grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-2">
                {copy.design.uploadLogo}
              </label>
              <div className="flex items-center gap-4">
                <input
                  type="file"
                  ref={logoInputRef}
                  accept="image/png,image/jpeg,image/webp,image/svg+xml"
                  onChange={(e) => void handleFileUpload(e, "company_logo_url")}
                  className="hidden"
                />
                <button
                  type="button"
                  onClick={() => logoInputRef.current?.click()}
                  disabled={isUploadingLogo}
                  className="px-4 py-2.5 rounded-xl border border-white/10 bg-white/[0.04] hover:bg-white/[0.08] text-xs font-semibold text-white flex items-center gap-2 cursor-pointer transition-colors"
                >
                  <Upload className="w-4 h-4 text-[#0076FF]" />
                  <span>{isUploadingLogo ? "Téléversement…" : "Choisir un logo"}</span>
                </button>

                {designState.company_logo_url && (
                  <div className="w-10 h-10 rounded-xl bg-slate-900 border border-white/15 flex items-center justify-center p-1 overflow-hidden">
                    <img
                      src={designState.company_logo_url}
                      alt="Logo prévisualisé"
                      className="w-full h-full object-contain"
                    />
                  </div>
                )}
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-2">
                {copy.design.uploadEmblem}
              </label>
              <div className="flex items-center gap-4">
                <input
                  type="file"
                  ref={emblemInputRef}
                  accept="image/png,image/jpeg,image/webp,image/svg+xml"
                  onChange={(e) => void handleFileUpload(e, "company_emblem_url")}
                  className="hidden"
                />
                <button
                  type="button"
                  onClick={() => emblemInputRef.current?.click()}
                  className="px-4 py-2.5 rounded-xl border border-white/10 bg-white/[0.04] hover:bg-white/[0.08] text-xs font-semibold text-white flex items-center gap-2 cursor-pointer transition-colors"
                >
                  <Upload className="w-4 h-4 text-purple-400" />
                  <span>Choisir un emblème</span>
                </button>

                {designState.company_emblem_url && (
                  <div className="w-10 h-10 rounded-xl bg-slate-900 border border-white/15 flex items-center justify-center p-1 overflow-hidden">
                    <img
                      src={designState.company_emblem_url}
                      alt="Emblème"
                      className="w-full h-full object-contain"
                    />
                  </div>
                )}
              </div>
            </div>
          </div>

          {uploadError && (
            <div className="text-xs text-rose-400 bg-rose-500/10 border border-rose-500/20 p-3 rounded-xl">
              {uploadError}
            </div>
          )}
        </div>
      </div>
    </OnboardingWizardLayout>
  );
}
