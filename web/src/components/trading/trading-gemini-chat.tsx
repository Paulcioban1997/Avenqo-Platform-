"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { apiFetch } from "@/lib/api-request";
import { TRADING_COPY } from "@/lib/i18n/trading-copy";
import type { LocaleCode } from "@/lib/i18n/types";

interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

interface TradingGeminiChatProps {
  symbol: string;
  interval: string;
  locale: LocaleCode;
}

// Bibliothèque de questions aléatoires hautement spécialisées en analyse technique et trading
const SPECIALIZED_TRADING_QUESTIONS: string[] = [
  // 1. Momentum & Oscillateurs
  "Détectes-tu une divergence haussière ou baissière sur le RSI 14 et les dernières clôtures ?",
  "L'histogramme MACD montre-t-il une décélération ou un renforcement du momentum ?",
  "Le RSI 14 actuel signale-t-il un risque d'essoufflement ou une zone de surchauffe ?",
  "Observe-t-on une divergence cachée de continuation sur le momentum court terme ?",
  "Comment se positionne le RSI par rapport au niveau neutre des 50 sur cet intervalle ?",
  "L'écartement des lignes MACD confirme-t-il la force de l'impulsion en cours ?",

  // 2. Price Action & Niveaux Clés
  "Quels sont les niveaux majeurs de support et de résistance calculés d'après les récents extrêmes ?",
  "Où se situe le niveau d'invalidation critique si l'on prend un biais acheteur sur cet intervalle ?",
  "Y a-t-il un risque de fausse cassure (bull trap ou bear trap) sur la dernière bougie ?",
  "La structure récente forme-t-elle des sommets plus hauts (Higher Highs) ou une compression ?",
  "À quel niveau de cours un retournement de tendance court terme serait-il confirmé ?",
  "Quelles zones de liquidité récentes sont les plus susceptibles d'attirer le prix ?",

  // 3. Volatilité & Bandes de Bollinger
  "Que révèle la contraction actuelle des bandes de Bollinger sur l'imminence d'un breakout ?",
  "Le cours évolue-t-il en sur-extension par rapport à la bande de Bollinger supérieure ou inférieure ?",
  "La volatilité récente est-elle en phase de compression (Squeeze) ou d'expansion directionnelle ?",
  "Quelle distance par rapport aux bandes de Bollinger suggère le placement d'un stop-loss sécurisé ?",
  "Le cours réintègre-t-il la moyenne mobile centrale (SMA 20) après un excès d'amplitude ?",
  "Comment la variation sur 24h se compare-t-elle à la volatilité historique récente ?",

  // 4. Stratégie, Confluences & Moyennes Mobiles
  "Quel est l'alignement entre l'EMA 12, la SMA 20 et la moyenne 26 périodes ?",
  "Quelles sont les confluences techniques (RSI + MACD + MA) observables sur cet intervalle ?",
  "Le marché évolue-t-il actuellement en phase de range (consolidation) ou de tendance nette ?",
  "Quel serait le ratio risque/rendement (R:R) théorique sur le niveau de clôture actuel ?",
  "Quelles conditions techniques précises attendrais-tu pour confirmer un point d'entrée ?",
  "Existe-t-il un signal précoce de retour vers la moyenne mobile 20 périodes ?",
];

function pickRandomQuestions(count: number = 3): string[] {
  const shuffled = [...SPECIALIZED_TRADING_QUESTIONS].sort(() => 0.5 - Math.random());
  return shuffled.slice(0, count);
}

export function TradingGeminiChat({ symbol, interval, locale }: TradingGeminiChatProps) {
  const copy = TRADING_COPY[locale] || TRADING_COPY.fr;

  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [voiceActive, setVoiceActive] = useState(false);
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>(() => pickRandomQuestions(3));
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content: `Bonjour ! Je suis l'analyste de marché Avenqo Trading AI propulsé par Google Gemini. Je suis spécialisé dans l'analyse quantitative en temps réel (Price Action, RSI 14, histogramme MACD, Bandes de Bollinger, moyennes mobiles et invalidations) pour **${symbol}** (${interval}).\n\nPosez-moi vos questions techniques ou choisissez une question aléatoire ci-dessous pour démarrer une conversation fluide.`,
      timestamp: new Date().toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" }),
    },
  ]);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading, scrollToBottom]);

  const shuffleQuestions = () => {
    setSuggestedQuestions(pickRandomQuestions(3));
  };

  const clearChat = () => {
    setMessages([
      {
        role: "assistant",
        content: `Conversation réinitialisée. Prêt pour une nouvelle analyse technique de **${symbol}** sur l'intervalle ${interval}. Que souhaitez-vous analyser ?`,
        timestamp: new Date().toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" }),
      },
    ]);
  };

  const sendQuery = async (queryText: string) => {
    if (!queryText.trim() || loading) return;
    const nowStr = new Date().toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });

    const userMsg: Message = { role: "user", content: queryText, timestamp: nowStr };
    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);
    setInput("");
    setLoading(true);

    try {
      const response = await apiFetch("/api/v1/trading/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol,
          interval,
          locale,
          question: queryText,
          conversation_history: nextMessages.slice(-6).map((m) => ({
            role: m.role,
            content: m.content,
          })),
        }),
      });

      if (!response.ok) {
        throw new Error("Erreur de communication avec l'assistant");
      }

      const body = await response.json();
      const assistantMsg: Message = {
        role: "assistant",
        content: body.text || "Analyse indisponible pour le moment.",
        timestamp: new Date().toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Désolé, impossible d'effectuer l'analyse en direct actuellement. Vérifiez la connexion aux flux de marché.",
          timestamp: new Date().toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const toggleVoice = () => {
    setVoiceActive(!voiceActive);
    if (!voiceActive) {
      void sendQuery(`Analyse le ${symbol} et résume les confluences techniques majeures sur l'intervalle ${interval}.`);
    }
  };

  // Helper de rendu de texte avec markdown simple (gras, puces, titres)
  const renderFormattedText = (content: string) => {
    return content.split("\n").map((line, idx) => {
      const trimmed = line.trim();
      if (!trimmed) {
        return <div key={idx} className="h-2" />;
      }
      if (trimmed.startsWith("### ")) {
        return (
          <h4 key={idx} className="font-bold text-cyan-300 text-xs mt-2 mb-1">
            {trimmed.replace("### ", "")}
          </h4>
        );
      }
      if (trimmed.startsWith("- ")) {
        const bulletText = trimmed.replace("- ", "");
        return (
          <div key={idx} className="flex items-start gap-1.5 pl-1 my-0.5">
            <span className="text-cyan-400 leading-tight select-none">•</span>
            <span className="flex-1 leading-relaxed">{renderBoldSegments(bulletText)}</span>
          </div>
        );
      }
      return (
        <p key={idx} className="leading-relaxed my-0.5">
          {renderBoldSegments(line)}
        </p>
      );
    });
  };

  const renderBoldSegments = (text: string) => {
    const parts = text.split(/(\*\*[^*]+\*\*)/g);
    return parts.map((part, i) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        return (
          <strong key={i} className="font-bold text-white">
            {part.slice(2, -2)}
          </strong>
        );
      }
      if (part.startsWith("*") && part.endsWith("*")) {
        return (
          <em key={i} className="italic text-slate-300">
            {part.slice(1, -1)}
          </em>
        );
      }
      return <span key={i}>{part}</span>;
    });
  };

  return (
    <div className="flex h-full flex-col justify-between rounded-2xl border border-slate-800 bg-slate-950/85 p-4 backdrop-blur-xl space-y-3 shadow-xl">
      {/* En-tête Voice & Chat */}
      <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-tr from-cyan-600 to-purple-600 text-white font-black text-xs shadow-md">
            AI
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-white">{copy.aiChatTitle}</h2>
              <span className="rounded-full bg-cyan-950/80 px-2 py-0.5 text-[9px] font-bold text-cyan-400 border border-cyan-800/60">
                Gemini Pro Live
              </span>
            </div>
            <p className="text-[10px] text-slate-400">Dialogue fluide & analyse technique quantifiée</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Bouton pour effacer le chat */}
          <button
            type="button"
            onClick={clearChat}
            className="rounded-lg border border-slate-800 bg-slate-900/60 p-1.5 text-slate-400 hover:text-white hover:border-slate-700 transition"
            title="Effacer la conversation"
          >
            🧹
          </button>

          {/* Bouton Voice Trading Simulation */}
          <button
            type="button"
            onClick={toggleVoice}
            className={`flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold transition-all ${
              voiceActive
                ? "bg-rose-500 text-white animate-pulse shadow-lg shadow-rose-950"
                : "bg-slate-900 border border-slate-700 text-slate-300 hover:text-white hover:border-slate-600"
            }`}
            title="Activer le mode vocal"
          >
            {voiceActive ? (
              <>
                <span className="flex gap-0.5 items-center">
                  <span className="h-2 w-0.5 bg-white animate-bounce"></span>
                  <span className="h-3 w-0.5 bg-white animate-bounce delay-75"></span>
                  <span className="h-2 w-0.5 bg-white animate-bounce delay-150"></span>
                </span>
                <span>{copy.aiListening}</span>
              </>
            ) : (
              <>
                <span>🎙️</span>
                <span>{copy.aiVoiceTrading}</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Fil de discussion fluide avec auto-scroll */}
      <div className="min-h-[200px] max-h-[300px] flex-1 space-y-3 overflow-y-auto pr-1 text-xs scrollbar-thin">
        {messages.map((m, idx) => (
          <div
            key={idx}
            className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"}`}
          >
            <div
              className={`max-w-[92%] rounded-2xl px-3.5 py-2.5 leading-relaxed text-xs shadow-sm ${
                m.role === "user"
                  ? "bg-gradient-to-r from-cyan-600 to-blue-600 text-white font-medium shadow-cyan-950/40"
                  : "bg-slate-900/90 border border-slate-800/90 text-slate-200"
              }`}
            >
              {m.role === "assistant" ? renderFormattedText(m.content) : <p className="whitespace-pre-line">{m.content}</p>}
              <span className="mt-1 block text-right text-[9px] opacity-60 font-mono">{m.timestamp}</span>
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex items-center gap-2 rounded-xl bg-slate-900/60 border border-slate-800/80 px-3 py-2 text-xs text-slate-400 animate-pulse w-fit">
            <span className="h-2 w-2 rounded-full bg-cyan-400 animate-ping"></span>
            <span>Gemini analyse les indicateurs et la structure de {symbol}...</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggestions de questions aléatoires et spécialisées */}
      <div className="space-y-1.5 pt-1 border-t border-slate-800/60">
        <div className="flex items-center justify-between text-[11px] text-slate-400">
          <span className="font-semibold text-slate-300">Questions spécialisées :</span>
          <button
            type="button"
            onClick={shuffleQuestions}
            className="flex items-center gap-1 text-[10px] text-cyan-400 hover:text-cyan-300 transition font-semibold"
          >
            <span>🎲</span>
            <span>Nouvelles questions</span>
          </button>
        </div>

        <div className="flex flex-col gap-1.5">
          {suggestedQuestions.map((q, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => void sendQuery(q)}
              className="text-left rounded-xl border border-slate-800/90 bg-slate-900/60 hover:bg-slate-900 px-3 py-1.5 text-[11px] text-slate-300 hover:text-cyan-300 hover:border-cyan-500/60 transition leading-snug flex items-center justify-between gap-2 group"
            >
              <span className="line-clamp-2">💬 {q}</span>
              <span className="text-slate-600 group-hover:text-cyan-400 transition select-none text-[10px]">➜</span>
            </button>
          ))}
        </div>
      </div>

      {/* Formulaire de saisie directe */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void sendQuery(input);
        }}
        className="flex gap-2 pt-1 border-t border-slate-800/60"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Posez votre question technique à Gemini..."
          className="flex-1 rounded-xl border border-slate-800 bg-slate-900/90 px-3 py-2 text-xs text-white placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="rounded-xl bg-gradient-to-r from-cyan-600 to-blue-600 px-4 py-2 text-xs font-bold text-white shadow-md transition disabled:opacity-50 hover:brightness-110"
        >
          {copy.aiSubmit}
        </button>
      </form>

      {/* Avertissement de non-conseil financier */}
      <p className="text-[9px] text-slate-500 leading-tight">
        ⚖️ {copy.aiDisclaimer}
      </p>
    </div>
  );
}
