"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { apiFetch } from "@/lib/api-request";
import { TRADING_COPY } from "@/lib/i18n/trading-copy";
import { getTradingChatStrings, pickRandomTradingQuestions } from "@/lib/i18n/trading-chat-i18n";
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
  const chatStrings = getTradingChatStrings(locale);

  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [voiceActive, setVoiceActive] = useState(false);
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>(() =>
    pickRandomTradingQuestions(locale, 3)
  );
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content: chatStrings.welcome(symbol, interval),
      timestamp: new Date().toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" }),
    },
  ]);

  // Update suggestions and greeting if symbol, interval, or locale changes while conversation hasn't started
  useEffect(() => {
    setSuggestedQuestions(pickRandomTradingQuestions(locale, 3));
    setMessages((prev) => {
      if (prev.length <= 1) {
        return [
          {
            role: "assistant",
            content: chatStrings.welcome(symbol, interval),
            timestamp: new Date().toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" }),
          },
        ];
      }
      return prev;
    });
  }, [locale, symbol, interval, chatStrings]);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading, scrollToBottom]);

  const shuffleQuestions = () => {
    setSuggestedQuestions(pickRandomTradingQuestions(locale, 3));
  };

  const clearChat = () => {
    setMessages([
      {
        role: "assistant",
        content: chatStrings.reset(symbol, interval),
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
        throw new Error(chatStrings.error);
      }

      const body = await response.json();
      const assistantMsg: Message = {
        role: "assistant",
        content: body.text || chatStrings.error,
        timestamp: new Date().toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: chatStrings.error,
          timestamp: new Date().toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const toggleVoice = () => {
    const nextState = !voiceActive;
    setVoiceActive(nextState);
    if (nextState) {
      void sendQuery(chatStrings.voicePrompt(symbol, interval));
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
              <h2 className="text-sm font-bold text-white">{chatStrings.title}</h2>
              <span className="rounded-full bg-cyan-950/80 px-2 py-0.5 text-[9px] font-bold text-cyan-400 border border-cyan-800/60">
                {chatStrings.badge}
              </span>
            </div>
            <p className="text-[10px] text-slate-400">{chatStrings.subtitle}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Bouton pour effacer le chat */}
          <button
            type="button"
            onClick={clearChat}
            className="rounded-lg border border-slate-800 bg-slate-900/60 p-1.5 text-slate-400 hover:text-white hover:border-slate-700 transition"
            title={chatStrings.clearChatTooltip}
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
            title={chatStrings.voiceTooltip}
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
            <span>{chatStrings.loading(symbol)}</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggestions de questions aléatoires et spécialisées */}
      <div className="space-y-1.5 pt-1 border-t border-slate-800/60">
        <div className="flex items-center justify-between text-[11px] text-slate-400">
          <span className="font-semibold text-slate-300">{chatStrings.specializedQuestionsLabel}</span>
          <button
            type="button"
            onClick={shuffleQuestions}
            className="flex items-center gap-1 text-[10px] text-cyan-400 hover:text-cyan-300 transition font-semibold"
          >
            <span>🎲</span>
            <span>{chatStrings.shuffleQuestionsLabel}</span>
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
          placeholder={chatStrings.inputPlaceholder}
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
