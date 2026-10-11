"use client";

import React, { useState, useEffect, useRef } from "react";
import { apiFetch } from "@/lib/api-request";
import {
  Volume2,
  VolumeX,
  Play,
  Pause,
  Check,
  Sparkles,
  Sliders,
  MessageSquare,
  PhoneOff,
  Plus,
  Trash2,
  Save,
  Loader2,
  Filter,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
} from "lucide-react";

interface VoiceCatalogItem {
  id: string;
  name: string;
  provider: string;
  gender: "male" | "female" | "neutral";
  style?: string;
  style_label?: string;
  personality_traits?: string[];
  description?: string;
  sample_url?: string | null;
  supported_languages: string[];
  latency_tier: string;
}

interface VoiceConfig {
  voice_id: string;
  voice_provider: string;
  speech_speed: number;
  personality_tone: string;
  custom_pronunciation: Record<string, string>;
  greeting_message?: string;
  farewell_message?: string;
}

interface VoiceCustomizationSectionProps {
  tenantId?: string;
}

const PERSONALITY_TONES = [
  { id: "professionnel", label: "Professionnel & Rigoureux", desc: "Clair, précis, courtois, idéal pour services B2B et finances" },
  { id: "chaleureux", label: "Chaleureux & Accueillant", desc: "Empathique, souriant, rassurant, idéal pour hôtellerie et santé" },
  { id: "dynamique", label: "Dynamique & Énergique", desc: "Vif, proactif, stimulant, idéal pour vente au détail et événements" },
  { id: "calme", label: "Calme & Posé", desc: "Apaisant, mesuré, parfait pour consultations et support délicat" },
  { id: "elegant", label: "Élégant & Raffiné", desc: "Distingué, haut de gamme, idéal pour boutiques de luxe et instituts" },
];

export function VoiceCustomizationSection({ tenantId }: VoiceCustomizationSectionProps) {
  const [catalog, setCatalog] = useState<VoiceCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Configuration state
  const [selectedVoiceId, setSelectedVoiceId] = useState<string>("shimmer");
  const [speechSpeed, setSpeechSpeed] = useState<number>(1.0);
  const [personalityTone, setPersonalityTone] = useState<string>("professionnel");
  const [greetingMessage, setGreetingMessage] = useState<string>("");
  const [farewellMessage, setFarewellMessage] = useState<string>("");
  const [pronunciations, setPronunciations] = useState<{ term: string; replaceWith: string }[]>([]);
  const [newTerm, setNewTerm] = useState("");
  const [newReplacement, setNewReplacement] = useState("");

  // Filter state
  const [genderFilter, setGenderFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Audio preview state
  const [playingVoiceId, setPlayingVoiceId] = useState<string | null>(null);
  const [audioLoadingVoiceId, setAudioLoadingVoiceId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const applyConfig = (config: VoiceConfig) => {
    setSelectedVoiceId(config.voice_id);
    setSpeechSpeed(config.speech_speed);
    setPersonalityTone(config.personality_tone);
    setGreetingMessage(config.greeting_message ?? "");
    setFarewellMessage(config.farewell_message ?? "");
    setPronunciations(Object.entries(config.custom_pronunciation ?? {}).map(([term, replaceWith]) => ({ term, replaceWith: String(replaceWith) })));
  };

  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => {
      if (controller.signal.aborted) return;
      setLoading(true); setLoaded(false); setSaveSuccess(false); setCatalog([]); setErrorMessage(null);
    });
    async function loadData() {
      try {
        const [catalogRes, configRes] = await Promise.all([
          apiFetch("/api/v1/voice/voices", { signal: controller.signal }),
          apiFetch("/api/v1/voice/customization", { signal: controller.signal }),
        ]);
        const [items, config] = await Promise.all([catalogRes.json(), configRes.json()]);
        if (controller.signal.aborted) return;
        if (!Array.isArray(items) || typeof config.voice_id !== "string" || typeof config.speech_speed !== "number") {
          throw new Error("Invalid voice configuration response");
        }
        setCatalog(items);
        applyConfig(config);
        setLoaded(true);
      } catch {
        if (!controller.signal.aborted) setErrorMessage("Impossible de charger les réglages vocaux. Rechargez la page pour réessayer.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void loadData();
    return () => {
      controller.abort();
      audioRef.current?.pause();
      audioRef.current = null;
    };
  }, [tenantId]);

  const handlePlayPreview = async (voice: VoiceCatalogItem) => {
    if (playingVoiceId === voice.id) {
      if (audioRef.current) {
        audioRef.current.pause();
      }
      setPlayingVoiceId(null);
      return;
    }

    if (audioRef.current) {
      audioRef.current.pause();
    }

    setAudioLoadingVoiceId(voice.id);
    setErrorMessage(null);

    try {
      const response = await apiFetch("/api/v1/voice/voices/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          voice_id: voice.id,
          text: `Bonjour, je suis votre assistant vocal Avenqo. Comment puis-je vous aider aujourd'hui ?`,
        }),
      });

      if (!response.ok) {
        throw new Error("Impossible de générer l'extrait audio");
      }

      const blob = await response.blob();
      if (!response.headers.get("Content-Type")?.startsWith("audio/") || blob.size === 0) {
        throw new Error("Le service n’a pas retourné d’extrait audio valide. Réessayez.");
      }
      const audioUrl = URL.createObjectURL(blob);
      const audio = new Audio(audioUrl);
      audioRef.current = audio;

      audio.onended = () => {
        setPlayingVoiceId(null);
        URL.revokeObjectURL(audioUrl);
      };

      audio.onerror = () => {
        setPlayingVoiceId(null);
        setErrorMessage("Erreur lors de la lecture audio");
        URL.revokeObjectURL(audioUrl);
      };

      await audio.play();
      setPlayingVoiceId(voice.id);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : "Erreur de prévisualisation");
    } finally {
      setAudioLoadingVoiceId(null);
    }
  };

  const handleAddPronunciation = () => {
    if (!newTerm.trim() || !newReplacement.trim()) return;
    setPronunciations([...pronunciations, { term: newTerm.trim(), replaceWith: newReplacement.trim() }]);
    setNewTerm("");
    setNewReplacement("");
  };

  const handleRemovePronunciation = (index: number) => {
    setPronunciations(pronunciations.filter((_, i) => i !== index));
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveSuccess(false);
    setErrorMessage(null);

    const customPronunciationRecord: Record<string, string> = {};
    for (const item of pronunciations) {
      customPronunciationRecord[item.term] = item.replaceWith;
    }

    try {
      const payload = {
        voice_id: selectedVoiceId,
        voice_provider: "openai",
        speech_speed: speechSpeed,
        personality_tone: personalityTone,
        greeting_message: greetingMessage,
        farewell_message: farewellMessage,
        custom_pronunciation: customPronunciationRecord,
      };

      await apiFetch("/api/v1/voice/customization", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const persisted = await apiFetch("/api/v1/voice/customization");
      applyConfig(await persisted.json());

      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 4000);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : "Erreur de sauvegarde");
    } finally {
      setSaving(false);
    }
  };

  const filteredVoices = catalog.filter((voice) => {
    if (genderFilter !== "all" && voice.gender !== genderFilter) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchName = voice.name.toLowerCase().includes(q) || voice.id.toLowerCase().includes(q);
      const traits = voice.personality_traits || (voice.style_label ? [voice.style_label] : []);
      const matchTraits = traits.some((t) => t.toLowerCase().includes(q));
      return matchName || matchTraits;
    }
    return true;
  });

  return (
    <div className="space-y-8 rounded-2xl border border-slate-200/80 bg-white/80 p-6 shadow-sm backdrop-blur-md dark:border-white/[0.08] dark:bg-[#0B132B]/80 dark:shadow-[0_8px_32px_rgba(0,0,0,0.36)]">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200/60 pb-5 dark:border-white/[0.08]">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-[#0076FF] to-[#7B2CBF] text-white shadow-md shadow-blue-500/20">
              <Sparkles size={18} />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-900 dark:text-white">
                Personnalisation Vocale & Comportement de l&apos;Agent
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Définissez la voix, la diction, le ton et les règles de politesse téléphoniques pour votre entreprise
              </p>
            </div>
          </div>
        </div>

        <button
          type="button"
          disabled={saving || loading || !loaded || !catalog.some((voice) => voice.id === selectedVoiceId)}
          onClick={handleSave}
          className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-[#0076FF] to-[#0052CC] px-4 py-2.5 text-xs font-semibold text-white shadow-sm transition hover:brightness-110 disabled:opacity-50 dark:shadow-[0_0_16px_rgba(0,118,255,0.35)]"
        >
          {saving ? (
            <>
              <Loader2 size={15} className="animate-spin" />
              <span>Sauvegarde...</span>
            </>
          ) : saveSuccess ? (
            <>
              <CheckCircle2 size={15} className="text-emerald-300" />
              <span>Enregistré avec succès !</span>
            </>
          ) : (
            <>
              <Save size={15} />
              <span>Enregistrer les réglages</span>
            </>
          )}
        </button>
      </div>

      {errorMessage && (
        <div className="flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-600 dark:text-red-400">
          <AlertCircle size={16} />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* 1. Voice Catalog Grid */}
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
              Catalogue de Voix Réelles Haute Fidélité
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Voix disponibles pour le modèle de synthèse configuré. Les extraits sont générés par une IA.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 text-xs dark:border-white/10 dark:bg-white/5">
              <Filter size={13} className="mr-1.5 text-slate-400" />
              <select
                value={genderFilter}
                onChange={(e) => setGenderFilter(e.target.value)}
                className="bg-transparent text-xs text-slate-700 outline-none dark:text-slate-200"
              >
                <option value="all">Tous les genres</option>
                <option value="female">Voix Féminines</option>
                <option value="male">Voix Masculines</option>
                <option value="neutral">Voix Neutres</option>
              </select>
            </div>
            <input
              type="text"
              placeholder="Rechercher une voix..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-800 placeholder-slate-400 outline-none focus:border-[#0076FF] dark:border-white/10 dark:bg-white/5 dark:text-white"
            />
          </div>
        </div>

        {loading ? (
          <div className="flex h-40 items-center justify-center">
            <Loader2 className="animate-spin text-[#0076FF]" size={28} />
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
            {filteredVoices.map((voice) => {
              const isSelected = selectedVoiceId === voice.id;
              const isPlaying = playingVoiceId === voice.id;
              const isAudioLoading = audioLoadingVoiceId === voice.id;

              return (
                <div
                  key={voice.id}
                  onClick={() => setSelectedVoiceId(voice.id)}
                  className={`group relative cursor-pointer rounded-xl border p-4 transition-all duration-200 ${
                    isSelected
                      ? "border-[#0076FF] bg-blue-50/50 shadow-[0_0_20px_rgba(0,118,255,0.18)] dark:border-[#0076FF] dark:bg-[#111D3D]"
                      : "border-slate-200/80 bg-slate-50/50 hover:border-slate-300 dark:border-white/[0.08] dark:bg-white/[0.02] dark:hover:border-white/20"
                  }`}
                >
                  {/* Top Bar: Name & Selection Indicator */}
                  <div className="flex items-start justify-between">
                    <div>
                      <span className="font-semibold text-slate-900 dark:text-white">
                        {voice.name}
                      </span>
                      <span className="ml-2 rounded bg-slate-200/70 px-1.5 py-0.5 font-mono text-[10px] text-slate-600 dark:bg-white/10 dark:text-slate-300">
                        {voice.gender === "female" ? "Féminin" : voice.gender === "male" ? "Masculin" : "Neutre"}
                      </span>
                    </div>

                    <div
                      className={`flex h-5 w-5 items-center justify-center rounded-full transition ${
                        isSelected
                          ? "bg-[#0076FF] text-white"
                          : "border border-slate-300 dark:border-white/20"
                      }`}
                    >
                      {isSelected && <Check size={12} strokeWidth={3} />}
                    </div>
                  </div>

                  {/* Badges / Traits */}
                  <div className="mt-2.5 flex flex-wrap gap-1">
                    {(voice.personality_traits || (voice.style_label ? [voice.style_label] : [])).map((trait) => (
                      <span
                        key={trait}
                        className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600 dark:bg-white/5 dark:text-slate-400"
                      >
                        {trait}
                      </span>
                    ))}
                    <span className="rounded-md bg-emerald-500/10 px-1.5 py-0.5 text-[10px] text-emerald-600 dark:text-emerald-400">
                      Synthèse IA
                    </span>
                  </div>

                  {/* Audio Preview Button */}
                  <div className="mt-3.5 border-t border-slate-200/50 pt-2.5 dark:border-white/[0.06]">
                    <button
                      type="button"
                      disabled={isAudioLoading}
                      onClick={(e) => {
                        e.stopPropagation();
                        handlePlayPreview(voice);
                      }}
                      className={`flex w-full items-center justify-center gap-1.5 rounded-lg py-1.5 text-xs font-medium transition ${
                        isPlaying
                          ? "bg-purple-600 text-white shadow-sm"
                          : "bg-slate-200/60 text-slate-700 hover:bg-slate-200 dark:bg-white/10 dark:text-slate-200 dark:hover:bg-white/15"
                      }`}
                    >
                      {isAudioLoading ? (
                        <>
                          <Loader2 size={13} className="animate-spin" />
                          <span>Génération...</span>
                        </>
                      ) : isPlaying ? (
                        <>
                          <Pause size={13} />
                          <span>Lecture de l&apos;extrait...</span>
                        </>
                      ) : (
                        <>
                          <Play size={13} fill="currentColor" />
                          <span>Écouter un extrait</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 2. Tone & Speed Controls */}
      <div className="grid grid-cols-1 gap-6 border-t border-slate-200/60 pt-6 sm:grid-cols-2 dark:border-white/[0.08]">
        {/* Speed Slider */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-1.5 text-xs font-semibold text-slate-900 dark:text-white">
              <Sliders size={14} className="text-[#0076FF]" />
              <span>Vitesse d&apos;élocution</span>
            </label>
            <span className="font-mono text-xs font-bold text-[#0076FF]">
              {speechSpeed.toFixed(2)}x
            </span>
          </div>

          <input
            type="range"
            min="0.80"
            max="1.20"
            step="0.05"
            value={speechSpeed}
            onChange={(e) => setSpeechSpeed(parseFloat(e.target.value))}
            className="h-2 w-full cursor-pointer appearance-none rounded-lg bg-slate-200 accent-[#0076FF] dark:bg-white/10"
          />

          <div className="flex justify-between text-[10px] text-slate-400">
            <button
              type="button"
              onClick={() => setSpeechSpeed(0.85)}
              className="hover:text-slate-600 dark:hover:text-slate-200"
            >
              0.85x (Posé)
            </button>
            <button
              type="button"
              onClick={() => setSpeechSpeed(1.0)}
              className="font-bold text-[#0076FF]"
            >
              1.00x (Naturel)
            </button>
            <button
              type="button"
              onClick={() => setSpeechSpeed(1.15)}
              className="hover:text-slate-600 dark:hover:text-slate-200"
            >
              1.15x (Dynamique)
            </button>
          </div>
        </div>

        {/* Personality Tone */}
        <div className="space-y-3">
          <label className="flex items-center gap-1.5 text-xs font-semibold text-slate-900 dark:text-white">
            <Sparkles size={14} className="text-purple-500" />
            <span>Ton & Posture de l&apos;Agent</span>
          </label>

          <select
            value={personalityTone}
            onChange={(e) => setPersonalityTone(e.target.value)}
            className="w-full rounded-xl border border-slate-200 bg-slate-50 p-2.5 text-xs text-slate-800 outline-none focus:border-[#0076FF] dark:border-white/10 dark:bg-[#111D3D] dark:text-white"
          >
            {PERSONALITY_TONES.map((tone) => (
              <option key={tone.id} value={tone.id}>
                {tone.label} — {tone.desc}
              </option>
            ))}
          </select>
          <p className="text-[11px] text-slate-500 dark:text-slate-400">
            Module la courtoisie, le vocabulaire et les tournures de phrases générées par l&apos;IA.
          </p>
        </div>
      </div>

      {/* 3. Greeting and Hangup Messages */}
      <div className="grid grid-cols-1 gap-6 border-t border-slate-200/60 pt-6 sm:grid-cols-2 dark:border-white/[0.08]">
        {/* Custom Greeting */}
        <div className="space-y-2">
          <label className="flex items-center gap-1.5 text-xs font-semibold text-slate-900 dark:text-white">
            <MessageSquare size={14} className="text-[#0076FF]" />
            <span>Message d&apos;accueil téléphonique</span>
          </label>
          <textarea
            rows={2}
            value={greetingMessage}
            onChange={(e) => setGreetingMessage(e.target.value)}
            placeholder="Ex: Bonjour et bienvenue chez [Entreprise] ! Comment puis-je vous renseigner aujourd'hui ?"
            className="w-full rounded-xl border border-slate-200 bg-slate-50 p-2.5 text-xs text-slate-800 placeholder-slate-400 outline-none focus:border-[#0076FF] dark:border-white/10 dark:bg-[#111D3D] dark:text-white"
          />
          <p className="text-[10px] text-slate-400">
            Prononcé dès que le correspondant décroche l&apos;appel.
          </p>
        </div>

        {/* Custom Farewell / Hangup */}
        <div className="space-y-2">
          <label className="flex items-center gap-1.5 text-xs font-semibold text-slate-900 dark:text-white">
            <PhoneOff size={14} className="text-red-400" />
            <span>Courtoisie avant raccrochage naturel</span>
          </label>
          <textarea
            rows={2}
            value={farewellMessage}
            onChange={(e) => setFarewellMessage(e.target.value)}
            placeholder="Ex: Avec grand plaisir ! Merci d'avoir contacté [Entreprise], passez une excellente journée. Au revoir !"
            className="w-full rounded-xl border border-slate-200 bg-slate-50 p-2.5 text-xs text-slate-800 placeholder-slate-400 outline-none focus:border-[#0076FF] dark:border-white/10 dark:bg-[#111D3D] dark:text-white"
          />
          <p className="text-[10px] text-slate-400">
            L&apos;IA détecte automatiquement quand le client termine (&quot;merci au revoir&quot;, &quot;c&apos;est tout&quot;) et prononce cette formule avant de couper la ligne.
          </p>
        </div>
      </div>

      {/* 4. Custom Pronunciation Dictionary */}
      <div className="space-y-3 border-t border-slate-200/60 pt-6 dark:border-white/[0.08]">
        <div>
          <h4 className="flex items-center gap-1.5 text-xs font-semibold text-slate-900 dark:text-white">
            <HelpCircle size={14} className="text-amber-500" />
            <span>Dictionnaire de Prononciation & Acronymes Métier</span>
          </h4>
          <p className="text-[11px] text-slate-500 dark:text-slate-400">
            Forcez la façon dont l&apos;IA prononce des noms d&apos;entreprises, marques ou termes techniques complexes.
          </p>
        </div>

        {pronunciations.length > 0 && (
          <div className="space-y-1.5">
            {pronunciations.map((item, index) => (
              <div
                key={index}
                className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-1.5 text-xs dark:border-white/10 dark:bg-white/[0.02]"
              >
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-slate-800 dark:text-slate-200">{item.term}</span>
                  <span className="text-slate-400">➔</span>
                  <span className="font-mono text-[#0076FF] dark:text-blue-400">{item.replaceWith}</span>
                </div>
                <button
                  type="button"
                  onClick={() => handleRemovePronunciation(index)}
                  className="text-slate-400 transition hover:text-red-500"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            placeholder="Terme ou Acronyme (ex: Avenqo)"
            value={newTerm}
            onChange={(e) => setNewTerm(e.target.value)}
            className="flex-1 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs text-slate-800 placeholder-slate-400 outline-none focus:border-[#0076FF] dark:border-white/10 dark:bg-[#111D3D] dark:text-white"
          />
          <input
            type="text"
            placeholder="Prononciation phonétique (ex: A-vène-ko)"
            value={newReplacement}
            onChange={(e) => setNewReplacement(e.target.value)}
            className="flex-1 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs text-slate-800 placeholder-slate-400 outline-none focus:border-[#0076FF] dark:border-white/10 dark:bg-[#111D3D] dark:text-white"
          />
          <button
            type="button"
            onClick={handleAddPronunciation}
            disabled={!newTerm.trim() || !newReplacement.trim()}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-xs hover:bg-slate-50 disabled:opacity-40 dark:border-white/20 dark:bg-white/10 dark:text-white dark:hover:bg-white/15"
          >
            <Plus size={13} />
            <span>Ajouter</span>
          </button>
        </div>
      </div>
    </div>
  );
}
