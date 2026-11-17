"use client";

import { useState } from "react";
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

export function TradingGeminiChat({ symbol, interval, locale }: TradingGeminiChatProps) {
  const copy = TRADING_COPY[locale] || TRADING_COPY.fr;

  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [voiceActive, setVoiceActive] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content: `Bonjour ! Je suis l'assistant Avenqo Trading AI propulsé par Google Gemini. Je peux analyser en direct les indicateurs techniques (RSI, MACD, moyennes mobiles, volatilité) pour ${symbol} sur l'intervalle ${interval}. Que souhaitez-vous analyser ?`,
      timestamp: new Date().toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" }),
    },
  ]);

  const sendQuery = async (queryText: string) => {
    if (!queryText.trim() || loading) return;
    const nowStr = new Date().toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });

    const userMsg: Message = { role: "user", content: queryText, timestamp: nowStr };
    setMessages((prev) => [...prev, userMsg]);
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
    } catch (err) {
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
      // Simulation d'une invite vocale rapide
      void sendQuery(`Analyse le ${symbol} et résume les points clés de la tendance sur les dernières bougies ${interval}.`);
    }
  };

  return (
    <div className="flex h-full flex-col justify-between rounded-2xl border border-slate-800 bg-slate-950/80 p-4 backdrop-blur-xl space-y-3">
      {/* En-tête Voice & Chat */}
      <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-tr from-cyan-600 to-purple-600 text-white font-bold text-xs shadow-md">
            AI
          </div>
          <div>
            <h2 className="text-sm font-bold text-white">{copy.aiChatTitle}</h2>
            <p className="text-[10px] text-slate-400">Analyse de marché en langage naturel & audio</p>
          </div>
        </div>

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

      {/* Fil de discussion */}
      <div className="max-h-[220px] min-h-[140px] flex-1 space-y-2.5 overflow-y-auto pr-1 text-xs scrollbar-thin">
        {messages.map((m, idx) => (
          <div
            key={idx}
            className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"}`}
          >
            <div
              className={`max-w-[90%] rounded-xl px-3 py-2 leading-relaxed ${
                m.role === "user"
                  ? "bg-cyan-600/90 text-white shadow-sm"
                  : "bg-slate-900/90 border border-slate-800 text-slate-200"
              }`}
            >
              <p className="whitespace-pre-line">{m.content}</p>
              <span className="mt-1 block text-right text-[9px] opacity-60">{m.timestamp}</span>
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex items-center gap-1.5 text-xs text-slate-400 animate-pulse">
            <span className="h-1.5 w-1.5 rounded-full bg-cyan-400"></span>
            <span>Gemini analyse les indicateurs de {symbol}...</span>
          </div>
        )}
      </div>

      {/* Suggestions de questions rapides */}
      <div className="flex flex-wrap gap-1.5 pt-1">
        <button
          type="button"
          onClick={() => void sendQuery(`Analyse la tendance et la volatilité sur 24h pour ${symbol}.`)}
          className="rounded-full border border-slate-800 bg-slate-900/60 px-2.5 py-1 text-[11px] text-slate-300 hover:border-cyan-500 hover:text-cyan-300 transition"
        >
          📈 {copy.aiQuickTrend}
        </button>
        <button
          type="button"
          onClick={() => void sendQuery(`Explique le RSI (14) et le MACD actuels pour ${symbol}. Sont-ils en surachat ou survente ?`)}
          className="rounded-full border border-slate-800 bg-slate-900/60 px-2.5 py-1 text-[11px] text-slate-300 hover:border-cyan-500 hover:text-cyan-300 transition"
        >
          ⚡ {copy.aiQuickRsi}
        </button>
        <button
          type="button"
          onClick={() => void sendQuery(`Quels sont les niveaux de support et résistance calculés pour ${symbol} ?`)}
          className="rounded-full border border-slate-800 bg-slate-900/60 px-2.5 py-1 text-[11px] text-slate-300 hover:border-cyan-500 hover:text-cyan-300 transition"
        >
          🎯 {copy.aiQuickLevels}
        </button>
      </div>

      {/* Formulaire de saisie */}
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
          placeholder={copy.aiAskPlaceholder}
          className="flex-1 rounded-xl border border-slate-800 bg-slate-900/80 px-3 py-2 text-xs text-white placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="rounded-xl bg-gradient-to-r from-cyan-600 to-blue-600 px-3.5 py-2 text-xs font-bold text-white shadow-md transition disabled:opacity-50"
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
