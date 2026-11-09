"use client";

import React, { useState, useEffect, useRef, useMemo } from "react";
import { useRouter } from "next/navigation";
import {
  Sparkles,
  Palette,
  Upload,
  Check,
  RotateCcw,
  Sun,
  Moon,
  Search,
  Filter,
  Layers,
  Eye,
  Sliders,
} from "lucide-react";
import { OnboardingWizardLayout } from "@/components/onboarding/onboarding-wizard-layout";
import {
  ALL_30_THEMES,
  ThemeDefinition,
  DEFAULT_THEME,
  getRecommendedThemes,
} from "@/lib/themes/theme-catalog";
import { getOnboardingCopy } from "@/lib/i18n/onboarding-multistep-copy";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAuthHeaders } from "@/lib/api-headers";
import { apiFetch } from "@/lib/api-request";

export default function OnboardingDesignPage() {
  const router = useRouter();
  const { locale } = useLocale();
  const copy = getOnboardingCopy(locale);

  const [isLoading, setIsLoading] = useState(true);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved">("idle");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isUploadingLogo, setIsUploadingLogo] = useState(false);

  // Filters for the 30 themes
  const [searchQuery, setSearchQuery] = useState("");
  const [modeFilter, setModeFilter] = useState<"all" | "dark" | "light">("all");
  const [categoryFilter, setCategoryFilter] = useState<
    "all" | "corporate" | "luxury" | "tech" | "creative" | "nature"
  >("all");

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
        const headers = getAuthHeaders() as Record<string, string>;
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
              display_name:
                data.design.display_name ||
                data.company_info?.commercial_name ||
                prev.display_name,
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

  const handleFileUpload = async (
    e: React.ChangeEvent<HTMLInputElement>,
    field: "company_logo_url" | "company_emblem_url"
  ) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.size > 5 * 1024 * 1024) {
      setUploadError("Le fichier ne doit pas dépasser 5 Mo.");
      return;
    }
    const allowed = ["image/png", "image/jpeg", "image/webp", "image/svg+xml"];
    if (!allowed.includes(file.type)) {
      setUploadError("Format invalide. Formats acceptés : PNG, JPEG, WebP, SVG.");
      return;
    }

    setUploadError(null);
    if (field === "company_logo_url") setIsUploadingLogo(true);

    try {
      const formData = new FormData();
      formData.append("file", file);
      const headers = getAuthHeaders() as Record<string, string>;
      delete headers["Content-Type"];

      const res = await fetch("/api/v1/onboarding/upload-asset", {
        method: "POST",
        headers,
        body: formData,
      });

      if (!res.ok) throw new Error("Échec de téléversement");
      const data = await res.json();
      setDesignState((prev) => ({ ...prev, [field]: data.asset_url }));
    } catch {
      setUploadError("Impossible de téléverser l'image. Réessayez.");
    } finally {
      if (field === "company_logo_url") setIsUploadingLogo(false);
    }
  };

  const handleResetTheme = () => {
    const current = ALL_30_THEMES.find((t) => t.id === designState.theme_id) || DEFAULT_THEME;
    setDesignState((prev) => ({
      ...prev,
      primary_color: current.primary_color,
      secondary_color: current.secondary_color,
      accent_color: current.accent_color,
      mode: current.mode,
      background_style: current.background_style,
      company_logo_url: "",
      company_emblem_url: "",
    }));
  };

  const handleSaveAndContinue = async () => {
    setSaveStatus("saving");
    try {
      const headers = getAuthHeaders() as Record<string, string>;
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

  // Top 5 Recommended Themes
  const recommendedThemes = useMemo(() => getRecommendedThemes(), []);

  // Filtered 30 Themes
  const filteredThemes = useMemo(() => {
    return ALL_30_THEMES.filter((theme) => {
      if (modeFilter !== "all" && theme.mode !== modeFilter) return false;
      if (categoryFilter !== "all" && theme.category !== categoryFilter) return false;
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase().trim();
        const matchesName = theme.name.toLowerCase().includes(query);
        const matchesDesc = theme.description.toLowerCase().includes(query);
        const matchesNum = theme.number.toString() === query || `#${theme.number}` === query;
        if (!matchesName && !matchesDesc && !matchesNum) return false;
      }
      return true;
    });
  }, [modeFilter, categoryFilter, searchQuery]);

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
      <div className="space-y-10">
        {/* Top 5 Recommended Section */}
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-white/[0.08] pb-3">
            <div className="flex items-center gap-2 text-sm font-bold text-white uppercase tracking-wider">
              <Sparkles className="w-4 h-4 text-[#00D4FF]" />
              <span>{copy.design.approvedPresetsTitle}</span>
              <span className="ml-2 text-[10px] font-mono px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 border border-blue-500/30">
                5 styles recommandés
              </span>
            </div>
            <div className="flex items-center gap-4 text-xs">
              <span className="text-slate-400 font-mono">30 disponibles</span>
              <button
                type="button"
                onClick={handleResetTheme}
                className="text-xs text-slate-400 hover:text-white flex items-center gap-1.5 transition-colors cursor-pointer"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>{copy.design.resetTheme}</span>
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5">
            {recommendedThemes.map((theme) => {
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
                  className={`p-3.5 rounded-2xl border transition-all text-left flex flex-col justify-between cursor-pointer select-none relative overflow-hidden group ${
                    isSelected
                      ? "bg-[#0B132B] border-[#0076FF] shadow-lg shadow-blue-500/20 ring-2 ring-[#0076FF]"
                      : "bg-[#0B132B]/60 border-white/[0.08] hover:border-white/25 hover:bg-[#0B132B]"
                  }`}
                >
                  <div>
                    {/* Visual Theme Palette Swatch */}
                    <div
                      className="h-20 rounded-xl mb-3 p-2.5 flex flex-col justify-between relative overflow-hidden border border-white/10"
                      style={{ background: theme.preview_gradient }}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-bold font-mono px-2 py-0.5 rounded-md bg-black/60 text-white backdrop-blur-xs">
                          #{theme.number}
                        </span>
                        {isSelected && (
                          <span className="w-5 h-5 rounded-full bg-[#0076FF] text-white flex items-center justify-center text-xs shadow-md">
                            <Check className="w-3 h-3 stroke-[3]" />
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-1.5">
                        <span
                          className="w-3 h-3 rounded-full border border-white/40 shadow-xs"
                          style={{ backgroundColor: theme.primary_color }}
                          title="Primaire"
                        />
                        <span
                          className="w-3 h-3 rounded-full border border-white/40 shadow-xs"
                          style={{ backgroundColor: theme.secondary_color }}
                          title="Secondaire"
                        />
                        <span
                          className="w-3 h-3 rounded-full border border-white/40 shadow-xs"
                          style={{ backgroundColor: theme.accent_color }}
                          title="Accent"
                        />
                      </div>
                    </div>

                    <div className="flex items-center justify-between gap-1">
                      <h4 className="font-bold text-white text-xs truncate">{theme.name}</h4>
                      <span className="text-[9px] uppercase px-1.5 py-0.5 rounded bg-white/[0.08] text-slate-300 shrink-0">
                        {theme.mode === "dark" ? "Sombre" : "Clair"}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-400 mt-1 line-clamp-2 leading-relaxed">
                      {theme.description}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Explore All 30 Themes Section */}
        <div className="space-y-4">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-white/[0.08] pb-3">
            <div className="flex items-center gap-2 text-sm font-bold text-white uppercase tracking-wider">
              <Palette className="w-4 h-4 text-purple-400" />
              <span>{copy.design.candidateThemesTitle}</span>
              <span className="text-xs font-mono font-normal text-slate-400">
                ({filteredThemes.length} / 30)
              </span>
            </div>

            {/* Filter controls */}
            <div className="flex flex-wrap items-center gap-2 text-xs">
              {/* Search input */}
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder={copy.design.searchPlaceholder}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-8 pr-3 py-1.5 rounded-xl bg-slate-900 border border-white/10 text-xs text-white placeholder-slate-500 focus:outline-hidden focus:border-[#0076FF] w-48"
                />
              </div>

              {/* Mode filter pills */}
              <div className="inline-flex rounded-xl p-1 bg-slate-900 border border-white/10">
                <button
                  type="button"
                  onClick={() => setModeFilter("all")}
                  className={`px-2.5 py-1 rounded-lg transition-colors ${
                    modeFilter === "all" ? "bg-[#0076FF] text-white" : "text-slate-400 hover:text-white"
                  }`}
                >
                  Tous
                </button>
                <button
                  type="button"
                  onClick={() => setModeFilter("dark")}
                  className={`px-2.5 py-1 rounded-lg transition-colors ${
                    modeFilter === "dark" ? "bg-[#0076FF] text-white" : "text-slate-400 hover:text-white"
                  }`}
                >
                  Sombre
                </button>
                <button
                  type="button"
                  onClick={() => setModeFilter("light")}
                  className={`px-2.5 py-1 rounded-lg transition-colors ${
                    modeFilter === "light" ? "bg-[#0076FF] text-white" : "text-slate-400 hover:text-white"
                  }`}
                >
                  Clair
                </button>
              </div>

              {/* Category filter pills */}
              <div className="hidden lg:inline-flex rounded-xl p-1 bg-slate-900 border border-white/10">
                {(
                  [
                    { id: "all", label: "Toutes" },
                    { id: "corporate", label: "Corporate" },
                    { id: "luxury", label: "Luxe" },
                    { id: "tech", label: "Technologie" },
                    { id: "creative", label: "Créatif" },
                    { id: "nature", label: "Nature" },
                  ] as const
                ).map((cat) => (
                  <button
                    key={cat.id}
                    type="button"
                    onClick={() => setCategoryFilter(cat.id)}
                    className={`px-2.5 py-1 rounded-lg transition-colors ${
                      categoryFilter === cat.id
                        ? "bg-purple-600 text-white font-semibold"
                        : "text-slate-400 hover:text-white"
                    }`}
                  >
                    {cat.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* 30 Themes Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
            {filteredThemes.map((theme) => {
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
                  className={`p-3 rounded-xl border transition-all text-left flex flex-col justify-between cursor-pointer select-none group ${
                    isSelected
                      ? "bg-[#0B132B] border-[#0076FF] ring-2 ring-[#0076FF] shadow-md shadow-blue-500/10"
                      : "bg-[#0B132B]/40 border-white/[0.06] hover:border-white/20 hover:bg-[#0B132B]"
                  }`}
                >
                  <div>
                    <div
                      className="h-16 rounded-lg mb-2 p-2 flex flex-col justify-between border border-white/10 relative overflow-hidden"
                      style={{ background: theme.preview_gradient }}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded bg-black/60 text-white">
                          #{theme.number}
                        </span>
                        {isSelected && (
                          <span className="w-4 h-4 rounded-full bg-[#0076FF] text-white flex items-center justify-center text-[10px]">
                            <Check className="w-2.5 h-2.5 stroke-[3]" />
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-1">
                        <span
                          className="w-2.5 h-2.5 rounded-full border border-white/30"
                          style={{ backgroundColor: theme.primary_color }}
                        />
                        <span
                          className="w-2.5 h-2.5 rounded-full border border-white/30"
                          style={{ backgroundColor: theme.secondary_color }}
                        />
                        <span
                          className="w-2.5 h-2.5 rounded-full border border-white/30"
                          style={{ backgroundColor: theme.accent_color }}
                        />
                      </div>
                    </div>

                    <div className="flex items-center justify-between gap-1">
                      <h5 className="font-bold text-white text-xs truncate">{theme.name}</h5>
                      <span className="text-[8px] font-mono uppercase px-1 py-0.2 rounded bg-white/[0.06] text-slate-300 shrink-0">
                        {theme.mode === "dark" ? "Sombre" : "Clair"}
                      </span>
                    </div>
                    <p className="text-[10px] text-slate-400 line-clamp-1 mt-0.5 leading-tight">
                      {theme.description}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>

          {filteredThemes.length === 0 && (
            <div className="py-12 text-center text-slate-400 bg-[#0B132B]/30 rounded-2xl border border-white/[0.06]">
              Aucun thème ne correspond à vos filtres de recherche.
            </div>
          )}
        </div>

        {/* Live Customization Studio & Real-Time Preview */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 pt-4 border-t border-white/[0.08]">
          {/* Left Column: Controls (8 cols) */}
          <div className="lg:col-span-7 bg-[#0B132B]/80 border border-white/[0.08] rounded-2xl p-6 space-y-6">
            <div className="flex items-center gap-2 text-sm font-bold text-white uppercase tracking-wider">
              <Sliders className="w-4 h-4 text-emerald-400" />
              <span>{copy.design.customColors}</span>
            </div>

            {/* Color Pickers */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label htmlFor="primary_color" className="block text-xs font-semibold text-slate-300 mb-2">
                  {copy.design.primaryColor}
                </label>
                <div className="flex items-center gap-2.5">
                  <input
                    id="primary_color"
                    type="color"
                    value={designState.primary_color}
                    onChange={(e) =>
                      setDesignState((prev) => ({ ...prev, primary_color: e.target.value }))
                    }
                    className="w-9 h-9 rounded-xl bg-transparent border border-white/20 cursor-pointer"
                  />
                  <input
                    type="text"
                    value={designState.primary_color}
                    onChange={(e) =>
                      setDesignState((prev) => ({ ...prev, primary_color: e.target.value }))
                    }
                    className="flex-1 px-3 py-1.5 rounded-xl bg-slate-900 border border-white/10 text-xs text-white font-mono"
                  />
                </div>
              </div>

              <div>
                <label htmlFor="secondary_color" className="block text-xs font-semibold text-slate-300 mb-2">
                  {copy.design.secondaryColor}
                </label>
                <div className="flex items-center gap-2.5">
                  <input
                    id="secondary_color"
                    type="color"
                    value={designState.secondary_color}
                    onChange={(e) =>
                      setDesignState((prev) => ({ ...prev, secondary_color: e.target.value }))
                    }
                    className="w-9 h-9 rounded-xl bg-transparent border border-white/20 cursor-pointer"
                  />
                  <input
                    type="text"
                    value={designState.secondary_color}
                    onChange={(e) =>
                      setDesignState((prev) => ({ ...prev, secondary_color: e.target.value }))
                    }
                    className="flex-1 px-3 py-1.5 rounded-xl bg-slate-900 border border-white/10 text-xs text-white font-mono"
                  />
                </div>
              </div>

              <div>
                <label htmlFor="accent_color" className="block text-xs font-semibold text-slate-300 mb-2">
                  {copy.design.accentColor}
                </label>
                <div className="flex items-center gap-2.5">
                  <input
                    id="accent_color"
                    type="color"
                    value={designState.accent_color}
                    onChange={(e) =>
                      setDesignState((prev) => ({ ...prev, accent_color: e.target.value }))
                    }
                    className="w-9 h-9 rounded-xl bg-transparent border border-white/20 cursor-pointer"
                  />
                  <input
                    type="text"
                    value={designState.accent_color}
                    onChange={(e) =>
                      setDesignState((prev) => ({ ...prev, accent_color: e.target.value }))
                    }
                    className="flex-1 px-3 py-1.5 rounded-xl bg-slate-900 border border-white/10 text-xs text-white font-mono"
                  />
                </div>
              </div>
            </div>

            {/* Mode Switcher */}
            <div className="pt-4 border-t border-white/[0.08] flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-300">Mode d'affichage d'espace :</span>
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

            {/* Uploads (Logo & Emblem) */}
            <div className="pt-4 border-t border-white/[0.08] grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-2">
                  {copy.design.uploadLogo}
                </label>
                <div className="flex items-center gap-3">
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
                    className="px-3.5 py-2 rounded-xl border border-white/10 bg-white/[0.04] hover:bg-white/[0.08] text-xs font-semibold text-white flex items-center gap-2 cursor-pointer transition-colors"
                  >
                    <Upload className="w-4 h-4 text-[#0076FF]" />
                    <span>{isUploadingLogo ? "Téléversement…" : "Choisir un logo"}</span>
                  </button>

                  {designState.company_logo_url && (
                    <div className="w-9 h-9 rounded-xl bg-slate-900 border border-white/15 flex items-center justify-center p-1 overflow-hidden">
                      <img
                        src={designState.company_logo_url}
                        alt="Logo client"
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
                <div className="flex items-center gap-3">
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
                    className="px-3.5 py-2 rounded-xl border border-white/10 bg-white/[0.04] hover:bg-white/[0.08] text-xs font-semibold text-white flex items-center gap-2 cursor-pointer transition-colors"
                  >
                    <Upload className="w-4 h-4 text-purple-400" />
                    <span>Choisir un emblème</span>
                  </button>

                  {designState.company_emblem_url && (
                    <div className="w-9 h-9 rounded-xl bg-slate-900 border border-white/15 flex items-center justify-center p-1 overflow-hidden">
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

          {/* Right Column: Live Interactive Mock Preview (5 cols) */}
          <div className="lg:col-span-5 bg-[#0B132B]/80 border border-white/[0.08] rounded-2xl p-6 flex flex-col justify-between space-y-4">
            <div>
              <div className="flex items-center gap-2 text-sm font-bold text-white uppercase tracking-wider mb-4">
                <Eye className="w-4 h-4 text-cyan-400" />
                <span>Aperçu de votre identité</span>
              </div>

              {/* Mock Dashboard Window */}
              <div
                className={`rounded-xl border p-4 transition-all overflow-hidden ${
                  designState.mode === "dark"
                    ? "bg-[#060B13] border-white/10 text-white"
                    : "bg-white border-slate-200 text-slate-900"
                }`}
              >
                {/* Mock Top Nav */}
                <div className="flex items-center justify-between pb-3 mb-3 border-b border-white/10">
                  <div className="flex items-center gap-2">
                    {designState.company_logo_url ? (
                      <img
                        src={designState.company_logo_url}
                        alt="Logo"
                        className="h-5 object-contain"
                      />
                    ) : (
                      <span
                        className="w-4 h-4 rounded-md flex items-center justify-center text-[10px] font-bold text-white"
                        style={{ backgroundColor: designState.primary_color }}
                      >
                        A
                      </span>
                    )}
                    <span className="text-xs font-bold">
                      {designState.display_name || "Votre Entreprise"}
                    </span>
                  </div>

                  <span
                    className="text-[10px] font-bold px-2 py-0.5 rounded-full text-white"
                    style={{ backgroundColor: designState.accent_color }}
                  >
                    Avenqo IA
                  </span>
                </div>

                {/* Mock Content Row */}
                <div className="grid grid-cols-2 gap-2.5">
                  <div
                    className="p-3 rounded-lg border flex flex-col justify-between"
                    style={{
                      borderColor: designState.primary_color + "40",
                      backgroundColor:
                        designState.mode === "dark" ? "#0B132B" : "#F8FAFC",
                    }}
                  >
                    <span className="text-[10px] text-slate-400 font-semibold">Chiffre d'affaires</span>
                    <span className="text-sm font-bold mt-1">45 820 $</span>
                    <span
                      className="text-[9px] font-bold mt-1"
                      style={{ color: designState.accent_color }}
                    >
                      +18.4% ce mois
                    </span>
                  </div>

                  <div
                    className="p-3 rounded-lg border flex flex-col justify-between"
                    style={{
                      borderColor: designState.primary_color + "40",
                      backgroundColor:
                        designState.mode === "dark" ? "#0B132B" : "#F8FAFC",
                    }}
                  >
                    <span className="text-[10px] text-slate-400 font-semibold">Commandes actives</span>
                    <span className="text-sm font-bold mt-1">342</span>
                    <span
                      className="text-[9px] font-bold mt-1"
                      style={{ color: designState.primary_color }}
                    >
                      Traitées par IA
                    </span>
                  </div>
                </div>

                {/* Mock Active Button */}
                <div className="mt-4 pt-3 border-t border-white/10 flex justify-end">
                  <button
                    type="button"
                    className="px-3 py-1.5 rounded-lg text-xs font-bold text-white shadow-sm"
                    style={{ backgroundColor: designState.primary_color }}
                  >
                    Consulter les prévisions
                  </button>
                </div>
              </div>
            </div>

            <div className="p-3 rounded-xl bg-blue-500/10 border border-blue-500/20 text-[11px] text-blue-300 leading-relaxed">
              Ce thème sera appliqué instantanément à votre tableau de bord, module Retail, CRM et Central AI dès l'activation finale.
            </div>
          </div>
        </div>
      </div>
    </OnboardingWizardLayout>
  );
}
