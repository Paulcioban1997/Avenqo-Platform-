"use client";

import React, { useState, useEffect, useRef, useMemo } from "react";
import {
  Palette,
  Upload,
  RotateCcw,
  Sparkles,
  Check,
  Moon,
  Sun,
  Save,
  CheckCircle2,
  Building2,
  Shield,
  Search,
  Filter,
} from "lucide-react";
import {
  ALL_30_THEMES,
  getRecommendedThemes,
  DEFAULT_THEME,
  ThemeDefinition,
} from "@/lib/themes/theme-catalog";
import { getAuthHeaders } from "@/lib/api-headers";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";

export function BrandingSettingsView() {
  const { locale } = useLocale();
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [modeFilter, setModeFilter] = useState<"all" | "dark" | "light">("all");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");

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

  const fetchBranding = async () => {
    try {
      const headers = getAuthHeaders();
      const res = await apiFetch("/api/v1/onboarding/branding", { headers });
      if (res.ok) {
        const data = await res.json();
        setDesignState({
          theme_id: data.theme_id || DEFAULT_THEME.id,
          primary_color: data.primary_color || DEFAULT_THEME.primary_color,
          secondary_color: data.secondary_color || DEFAULT_THEME.secondary_color,
          accent_color: data.accent_color || DEFAULT_THEME.accent_color,
          mode: data.mode || DEFAULT_THEME.mode,
          background_style: data.background_style || DEFAULT_THEME.background_style,
          company_logo_url: data.company_logo_url || "",
          company_emblem_url: data.company_emblem_url || "",
          display_name: data.display_name || "",
        });
      }
    } catch (err) {
      console.error("Erreur de chargement de la marque:", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void fetchBranding();
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
      setErrorMessage("L'image ne doit pas dépasser 5 Mo.");
      return;
    }

    setErrorMessage(null);
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
        throw new Error("Échec du téléversement");
      }

      const resData = await res.json();
      setDesignState((prev) => ({
        ...prev,
        [field]: resData.asset_url,
      }));
    } catch (err: any) {
      setErrorMessage(err.message || "Erreur de téléversement");
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    setSaveSuccess(false);
    setErrorMessage(null);
    try {
      const headers = getAuthHeaders();
      const res = await apiFetch("/api/v1/onboarding/branding", {
        method: "PUT",
        headers,
        body: JSON.stringify(designState),
      });
      if (res.ok) {
        setSaveSuccess(true);
        setTimeout(() => setSaveSuccess(false), 3000);
      } else {
        throw new Error("Erreur lors de l'enregistrement de l'apparence.");
      }
    } catch (err: any) {
      setErrorMessage(err.message || "Erreur d'enregistrement.");
    } finally {
      setIsSaving(false);
    }
  };

  const handleReset = async () => {
    setIsSaving(true);
    setErrorMessage(null);
    try {
      const headers = getAuthHeaders();
      const res = await apiFetch("/api/v1/onboarding/branding", {
        method: "PUT",
        headers,
        body: JSON.stringify({ reset: true }),
      });
      if (res.ok) {
        await fetchBranding();
        setSaveSuccess(true);
        setTimeout(() => setSaveSuccess(false), 3000);
      }
    } catch (err: any) {
      setErrorMessage(err.message || "Erreur lors de la réinitialisation.");
    } finally {
      setIsSaving(false);
    }
  };

  const recommendedThemes = useMemo(() => getRecommendedThemes(), []);

  const filteredThemes = useMemo(() => {
    return ALL_30_THEMES.filter((theme) => {
      const matchesSearch =
        searchQuery.trim() === "" ||
        theme.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        theme.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
        `#${theme.number}`.includes(searchQuery.trim()) ||
        `${theme.number}` === searchQuery.trim();

      const matchesMode = modeFilter === "all" || theme.mode === modeFilter;
      const matchesCategory = categoryFilter === "all" || theme.category === categoryFilter;

      return matchesSearch && matchesMode && matchesCategory;
    });
  }, [searchQuery, modeFilter, categoryFilter]);

  if (isLoading) {
    return <div className="text-xs text-slate-400 p-4">Chargement de la personnalisation…</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <Palette className="w-5 h-5 text-[#0076FF]" />
            <span>Apparence et Identité de Marque</span>
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Personnalisez le thème (30 univers officiels), les couleurs et les logos de votre espace locataire exclusif.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => void handleReset()}
            disabled={isSaving}
            className="px-3 py-1.5 rounded-xl border border-slate-200 dark:border-white/10 hover:bg-slate-100 dark:hover:bg-white/[0.04] text-xs font-semibold text-slate-600 dark:text-slate-300 flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Réinitialiser</span>
          </button>

          <button
            type="button"
            onClick={() => void handleSave()}
            disabled={isSaving}
            className="px-4 py-1.5 rounded-xl bg-[#0076FF] hover:bg-blue-600 text-xs font-bold text-white shadow-xs flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50"
          >
            <Save className="w-3.5 h-3.5" />
            <span>{isSaving ? "Enregistrement…" : "Enregistrer"}</span>
          </button>
        </div>
      </div>

      {saveSuccess && (
        <div className="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/40 text-xs text-emerald-800 dark:text-emerald-300 flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>Apparence mise à jour et appliquée avec succès à votre espace entreprise.</span>
        </div>
      )}

      {errorMessage && (
        <div className="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-800/40 text-xs text-rose-800 dark:text-rose-300">
          {errorMessage}
        </div>
      )}

      {/* Top 5 Recommended Section */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
            <Sparkles className="w-3.5 h-3.5 text-amber-400" />
            <span>Top 5 Recommandés</span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-500/10 text-[#0076FF] font-semibold border border-blue-500/20">
              Diversité & Prestige
            </span>
          </span>
          <span className="text-xs text-slate-400">5 styles recommandés</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
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
                className={`p-3 rounded-xl border transition-all text-left flex flex-col justify-between cursor-pointer ${
                  isSelected
                    ? "bg-slate-50 dark:bg-[#111D3D] border-[#0076FF] shadow-sm ring-2 ring-[#0076FF]"
                    : "bg-white dark:bg-[#0B132B]/60 border-slate-200 dark:border-white/[0.08] hover:border-slate-300"
                }`}
              >
                <div>
                  <div
                    className="h-14 rounded-lg mb-2 p-1.5 flex items-start justify-between border border-white/10"
                    style={{ background: theme.preview_gradient }}
                  >
                    <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-black/50 text-white">
                      #{theme.number} {theme.mode === "dark" ? "Sombre" : "Clair"}
                    </span>
                    {isSelected && <Check className="w-3.5 h-3.5 text-white" />}
                  </div>
                  <h4 className="font-bold text-slate-900 dark:text-white text-xs">{theme.name}</h4>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400 line-clamp-1 mt-0.5">
                    {theme.description}
                  </p>
                </div>
                <div className="flex items-center gap-1 mt-2">
                  <span className="w-2.5 h-2.5 rounded-full border border-black/20" style={{ background: theme.primary_color }} />
                  <span className="w-2.5 h-2.5 rounded-full border border-black/20" style={{ background: theme.secondary_color }} />
                  <span className="w-2.5 h-2.5 rounded-full border border-black/20" style={{ background: theme.accent_color }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Explorer: All 30 Themes with Search and Filters */}
      <div className="space-y-3 pt-4 border-t border-slate-200 dark:border-white/[0.08]">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Explorer les 30 univers Avenqo
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Accès illimité à l'intégralité du catalogue officiel (30 disponibles).
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Rechercher nom, #..."
                className="pl-8 pr-3 py-1.5 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-white/10 text-xs text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-[#0076FF] w-40"
              />
            </div>

            <div className="flex items-center rounded-lg bg-slate-100 dark:bg-slate-900/60 p-0.5 border border-slate-200 dark:border-white/10 text-[11px]">
              <button
                type="button"
                onClick={() => setModeFilter("all")}
                className={`px-2 py-1 rounded-md font-medium cursor-pointer ${
                  modeFilter === "all" ? "bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-xs" : "text-slate-400"
                }`}
              >
                Tous
              </button>
              <button
                type="button"
                onClick={() => setModeFilter("dark")}
                className={`px-2 py-1 rounded-md font-medium cursor-pointer ${
                  modeFilter === "dark" ? "bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-xs" : "text-slate-400"
                }`}
              >
                Sombre
              </button>
              <button
                type="button"
                onClick={() => setModeFilter("light")}
                className={`px-2 py-1 rounded-md font-medium cursor-pointer ${
                  modeFilter === "light" ? "bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-xs" : "text-slate-400"
                }`}
              >
                Clair
              </button>
            </div>
          </div>
        </div>

        {/* 30 Themes Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2.5 max-h-[380px] overflow-y-auto pr-1">
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
                className={`p-2.5 rounded-xl border transition-all text-left flex flex-col justify-between cursor-pointer ${
                  isSelected
                    ? "bg-slate-50 dark:bg-[#111D3D] border-[#0076FF] shadow-xs ring-2 ring-[#0076FF]"
                    : "bg-white dark:bg-[#0B132B]/50 border-slate-200 dark:border-white/[0.08] hover:border-slate-300"
                }`}
              >
                <div>
                  <div
                    className="h-10 rounded-lg mb-1.5 p-1 flex items-start justify-between border border-white/10"
                    style={{ background: theme.preview_gradient }}
                  >
                    <span className="text-[9px] font-bold uppercase px-1 py-0.5 rounded bg-black/60 text-white">
                      #{theme.number}
                    </span>
                    {isSelected && <Check className="w-3 h-3 text-white" />}
                  </div>
                  <h4 className="font-semibold text-slate-900 dark:text-white text-[11px] truncate">
                    {theme.name}
                  </h4>
                  <p className="text-[10px] text-slate-400 truncate">
                    {theme.mode === "dark" ? "Sombre" : "Clair"} • {theme.category}
                  </p>
                </div>
                <div className="flex items-center gap-1 mt-1.5">
                  <span className="w-2 h-2 rounded-full border border-black/20" style={{ background: theme.primary_color }} />
                  <span className="w-2 h-2 rounded-full border border-black/20" style={{ background: theme.secondary_color }} />
                  <span className="w-2 h-2 rounded-full border border-black/20" style={{ background: theme.accent_color }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Colors & Logo Controls */}
      <div className="bg-slate-50 dark:bg-[#0B132B]/60 border border-slate-200 dark:border-white/[0.08] rounded-2xl p-5 space-y-5">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label htmlFor="branding_primary_color" className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
              Couleur Principale
            </label>
            <div className="flex items-center gap-2">
              <input
                id="branding_primary_color"
                type="color"
                value={designState.primary_color}
                onChange={(e) => setDesignState((prev) => ({ ...prev, primary_color: e.target.value }))}
                className="w-8 h-8 rounded-lg bg-transparent border border-slate-300 dark:border-white/20 cursor-pointer"
              />
              <input
                type="text"
                value={designState.primary_color}
                onChange={(e) => setDesignState((prev) => ({ ...prev, primary_color: e.target.value }))}
                className="flex-1 px-3 py-1.5 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-white/10 text-xs text-slate-900 dark:text-white font-mono"
              />
            </div>
          </div>

          <div>
            <label htmlFor="branding_secondary_color" className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
              Couleur Secondaire
            </label>
            <div className="flex items-center gap-2">
              <input
                id="branding_secondary_color"
                type="color"
                value={designState.secondary_color}
                onChange={(e) => setDesignState((prev) => ({ ...prev, secondary_color: e.target.value }))}
                className="w-8 h-8 rounded-lg bg-transparent border border-slate-300 dark:border-white/20 cursor-pointer"
              />
              <input
                type="text"
                value={designState.secondary_color}
                onChange={(e) => setDesignState((prev) => ({ ...prev, secondary_color: e.target.value }))}
                className="flex-1 px-3 py-1.5 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-white/10 text-xs text-slate-900 dark:text-white font-mono"
              />
            </div>
          </div>

          <div>
            <label htmlFor="branding_accent_color" className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
              Couleur d'Accent
            </label>
            <div className="flex items-center gap-2">
              <input
                id="branding_accent_color"
                type="color"
                value={designState.accent_color}
                onChange={(e) => setDesignState((prev) => ({ ...prev, accent_color: e.target.value }))}
                className="w-8 h-8 rounded-lg bg-transparent border border-slate-300 dark:border-white/20 cursor-pointer"
              />
              <input
                type="text"
                value={designState.accent_color}
                onChange={(e) => setDesignState((prev) => ({ ...prev, accent_color: e.target.value }))}
                className="flex-1 px-3 py-1.5 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-white/10 text-xs text-slate-900 dark:text-white font-mono"
              />
            </div>
          </div>
        </div>

        {/* Logo and Emblem upload */}
        <div className="pt-4 border-t border-slate-200 dark:border-white/[0.08] grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
              Logo de l'entreprise
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
                className="px-3 py-2 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.04] text-xs font-semibold text-slate-700 dark:text-white flex items-center gap-2 cursor-pointer"
              >
                <Upload className="w-3.5 h-3.5 text-[#0076FF]" />
                <span>Téléverser logo</span>
              </button>
              {designState.company_logo_url && (
                <img
                  src={designState.company_logo_url}
                  alt="Logo"
                  className="w-8 h-8 rounded-lg object-contain border border-slate-200 dark:border-white/10 p-0.5"
                />
              )}
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
              Emblème / Favicon
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
                className="px-3 py-2 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.04] text-xs font-semibold text-slate-700 dark:text-white flex items-center gap-2 cursor-pointer"
              >
                <Upload className="w-3.5 h-3.5 text-purple-400" />
                <span>Téléverser emblème</span>
              </button>
              {designState.company_emblem_url && (
                <img
                  src={designState.company_emblem_url}
                  alt="Emblème"
                  className="w-8 h-8 rounded-lg object-contain border border-slate-200 dark:border-white/10 p-0.5"
                />
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
