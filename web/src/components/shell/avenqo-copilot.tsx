"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  Sparkles,
  X,
  Send,
  Bot,
  User,
  ShieldCheck,
  TrendingUp,
  AlertTriangle,
  RefreshCw,
  FileSpreadsheet,
  ChevronRight,
  Mic,
  MicOff,
} from "lucide-react";
import type { AppTranslations } from "@/lib/i18n/app-dictionary";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAuthHeaders } from "@/lib/api-headers";

export interface AvenqoCopilotProps {
  isOpen: boolean;
  onClose: () => void;
  activeRoute: string; // e.g. "/dashboard", "/retail", "/integrations"
  tenantName?: string;
  t: AppTranslations;
}

interface ChatMessage {
  id: string;
  sender: "user" | "copilot";
  content: string;
  timestamp: string;
  isStreaming?: boolean;
  grounded?: boolean;
}

interface EnabledSource {
  source_id: string;
  display_name: string;
  enabled: boolean;
}

export function AvenqoCopilot({
  isOpen,
  onClose,
  activeRoute,
  t,
}: AvenqoCopilotProps) {
  const { locale } = useLocale();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isThinking, setIsThinking] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [activeSources, setActiveSources] = useState<EnabledSource[]>([]);
  const [isListening, setIsListening] = useState(false);
  const [voiceSessionId, setVoiceSessionId] = useState<string | null>(null);
  const recognitionRef = useRef<any>(null);
  const voiceSocketRef = useRef<WebSocket | null>(null);
  const captureRef = useRef<{ stream: MediaStream; context: AudioContext; source: MediaStreamAudioSourceNode; processor: ScriptProcessorNode } | null>(null);
  const playbackRef = useRef<{ context: AudioContext; nextTime: number } | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const pendingRequestRef = useRef<{ content: string; key: string } | null>(null);

  // Auto-scroll on message change
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isThinking]);

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    void fetch("/api/v1/retail/sources", { headers: getAuthHeaders() })
      .then(async (response) => response.ok ? response.json() : [])
      .then((sources: unknown) => {
        if (!cancelled && Array.isArray(sources)) {
          setActiveSources(
            sources.filter(
              (source): source is EnabledSource =>
                typeof source === "object" && source !== null &&
                (source as EnabledSource).enabled === true,
            ),
          );
        }
      })
      .catch(() => {
        if (!cancelled) setActiveSources([]);
      });
    return () => { cancelled = true; };
  }, [isOpen]);

  const handleSend = async (textToSend?: string, voiceSessionOverride?: string | null) => {
    const query = (textToSend || input).trim();
    if (!query || isThinking) return;
    const pendingRequest = pendingRequestRef.current?.content === query
      ? pendingRequestRef.current
      : { content: query, key: crypto.randomUUID() };
    pendingRequestRef.current = pendingRequest;

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      sender: "user",
      content: query,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsThinking(true);

    try {
      const headers = {
        "Content-Type": "application/json",
        ...(typeof window !== "undefined" ? (await import("@/lib/api-headers")).getAuthHeaders() : {}),
      };

      let activeConversationId = conversationId;
      if (activeConversationId === null) {
        const conversationResponse = await fetch("/api/v1/ai/chat/conversations", {
          method: "POST",
          headers,
          body: JSON.stringify({ title: query.slice(0, 54) }),
        });
        if (!conversationResponse.ok) throw new Error("Conversation creation failed");
        const conversation = await conversationResponse.json();
        activeConversationId = conversation.id;
        setConversationId(activeConversationId);
      }

      const voiceSession = voiceSessionOverride ?? voiceSessionId;
      const res = voiceSession
        ? await fetch(`/api/v1/ai/voice/sessions/${voiceSession}/turn`, {
          method: "POST",
          headers: {
            ...headers,
            "Idempotency-Key": pendingRequest.key,
          },
          body: JSON.stringify({ transcript: query, request_id: pendingRequest.key }),
        })
        : await fetch(
        `/api/v1/ai/central/conversations/${activeConversationId}/messages`,
        {
        method: "POST",
        headers: {
          ...headers,
          "Idempotency-Key": pendingRequest.key,
        },
        body: JSON.stringify({
          content: query,
          locale,
          page_context: activeRoute,
        }),
        },
      );

      if (res.ok) {
        const data = await res.json();
        pendingRequestRef.current = null;
        window.dispatchEvent(new Event("avenqo:ai-credits-updated"));
        const copilotMsg: ChatMessage = {
          id: `c-${Date.now()}`,
          sender: "copilot",
          content: data.answer || t.copilot.errorPrompt,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          grounded: Boolean(data.grounded_source && data.status === "success"),
        };
        setMessages((prev) => [...prev, copilotMsg]);
      } else {
        const errorMsg: ChatMessage = {
          id: `c-${Date.now()}`,
          sender: "copilot",
          content: t.copilot.errorPrompt,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          grounded: false,
        };
        setMessages((prev) => [...prev, errorMsg]);
      }
    } catch {
      const errorMsg: ChatMessage = {
        id: `err-${Date.now()}`,
        sender: "copilot",
        content: t.copilot.errorPrompt,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        grounded: false,
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsThinking(false);
    }
  };

  const stopVoice = () => {
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    const capture = captureRef.current;
    captureRef.current = null;
    if (capture) {
      capture.processor.disconnect();
      capture.source.disconnect();
      capture.stream.getTracks().forEach((track) => track.stop());
      void capture.context.close();
    }
    voiceSocketRef.current?.close();
    voiceSocketRef.current = null;
    void playbackRef.current?.context.close();
    playbackRef.current = null;
    setIsListening(false);
  };

  const startFallbackRecognition = (sessionId: string | null) => {
    const Recognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!Recognition) {
      setMessages((prev) => [...prev, {
        id: `voice-${Date.now()}`, sender: "copilot",
        content: "Voice input is not available in this browser. You can continue with text.",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      }]);
      return;
    }
    const recognition = new Recognition();
    recognition.interimResults = true;
    recognition.continuous = false;
    let transcript = "";
    recognition.onresult = (event: any) => {
      transcript = Array.from(event.results as ArrayLike<any>)
        .map((result: any) => result[0]?.transcript || "").join(" ");
      setInput(transcript);
    };
    recognition.onerror = () => setIsListening(false);
    recognition.onend = () => {
      setIsListening(false);
      recognitionRef.current = null;
      if (transcript.trim()) void handleSend(transcript, sessionId);
    };
    recognitionRef.current = recognition;
    setIsListening(true);
    recognition.start();
  };

  const toggleListening = () => {
    if (isListening) {
      stopVoice();
      return;
    }
    const playbackContext = new AudioContext({ sampleRate: 24000 });
    void playbackContext.resume();
    playbackRef.current = { context: playbackContext, nextTime: 0 };
    const startVoice = async () => {
      let sessionId = voiceSessionId;
      let activeConversationId = conversationId;
      if (!activeConversationId) {
        const conversationResponse = await fetch("/api/v1/ai/chat/conversations", {
          method: "POST",
          headers: { "Content-Type": "application/json", ...getAuthHeaders() },
          body: JSON.stringify({ title: "Voice Central" }),
        });
        if (conversationResponse.ok) {
          activeConversationId = (await conversationResponse.json()).id;
          setConversationId(activeConversationId);
        }
      }
      if (!sessionId && activeConversationId) {
        const response = await fetch("/api/v1/ai/voice/sessions", {
          method: "POST",
          headers: { "Content-Type": "application/json", ...getAuthHeaders() },
          body: JSON.stringify({ conversation_id: activeConversationId, locale, request_id: crypto.randomUUID() }),
        });
        if (response.ok) {
          const session = await response.json();
          sessionId = session.id;
          setVoiceSessionId(sessionId);
        }
      }
      if (!sessionId || !navigator.mediaDevices?.getUserMedia) {
        void playbackRef.current?.context.close();
        playbackRef.current = null;
        startFallbackRecognition(sessionId);
        return;
      }
      const ticketResponse = await fetch(`/api/v1/ai/voice/sessions/${sessionId}/stream-ticket`, {
        method: "POST", headers: getAuthHeaders(),
      });
      if (!ticketResponse.ok) throw new Error("Voice ticket unavailable");
      const { ticket, realtime: available } = await ticketResponse.json();
      if (!available) {
        void playbackRef.current?.context.close();
        playbackRef.current = null;
        startFallbackRecognition(sessionId);
        return;
      }
      const host = ["localhost", "127.0.0.1"].includes(window.location.hostname)
        ? `${window.location.hostname}:8000` : "api.avenqo.ca";
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const socket = new WebSocket(`${protocol}//${host}/api/v1/ai/voice/sessions/${sessionId}/stream`, ["avenqo.voice", `ticket.${ticket}`]);
      voiceSocketRef.current = socket;
      let sequence = -1;
      socket.onmessage = (message) => {
        const event = JSON.parse(message.data);
        if (event.type === "lifecycle" && Number.isInteger(event.next_audio_sequence)) {
          sequence = Math.max(sequence, event.next_audio_sequence);
        }
        if (event.type === "error" && event.status === "text_fallback") {
          stopVoice();
          startFallbackRecognition(sessionId);
          return;
        }
        if (event.type === "lifecycle" && event.status === "interrupted") {
          void playbackRef.current?.context.close();
          playbackRef.current = null;
        }
        if (event.type === "transcript" && event.status === "final") {
          setMessages((prev) => [...prev, {
            id: crypto.randomUUID(), sender: "user", content: event.transcript,
            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          }]);
        }
        if (event.type === "answer") {
          window.dispatchEvent(new Event("avenqo:ai-credits-updated"));
          setMessages((prev) => [...prev, {
            id: crypto.randomUUID(), sender: "copilot", content: event.answer || t.copilot.errorPrompt,
            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          }]);
        }
        if (event.type === "audio" && event.format === "pcm16") {
          const playback = playbackRef.current ?? { context: new AudioContext({ sampleRate: 24000 }), nextTime: 0 };
          playbackRef.current = playback;
          const raw = atob(event.audio);
          const buffer = playback.context.createBuffer(1, raw.length / 2, 24000);
          const samples = buffer.getChannelData(0);
          for (let index = 0; index < samples.length; index++) {
            const value = raw.charCodeAt(index * 2) | (raw.charCodeAt(index * 2 + 1) << 8);
            samples[index] = (value > 32767 ? value - 65536 : value) / 32768;
          }
          const source = playback.context.createBufferSource();
          source.buffer = buffer;
          source.connect(playback.context.destination);
          source.start(Math.max(playback.context.currentTime, playback.nextTime));
          playback.nextTime = Math.max(playback.context.currentTime, playback.nextTime) + buffer.duration;
        }
      };
      socket.onclose = () => {
        if (voiceSocketRef.current === socket && captureRef.current) {
          stopVoice();
          startFallbackRecognition(sessionId);
        }
      };
      await new Promise<void>((resolve, reject) => {
        socket.onopen = () => resolve();
        socket.onerror = () => reject(new Error("Voice stream unavailable"));
      });
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      const context = new AudioContext({ sampleRate: 24000 });
      const source = context.createMediaStreamSource(stream);
      const processor = context.createScriptProcessor(2048, 1, 1);
      processor.onaudioprocess = (event) => {
        if (socket.readyState !== WebSocket.OPEN || sequence < 0) return;
        const input = event.inputBuffer.getChannelData(0);
        const count = Math.floor(input.length * 24000 / context.sampleRate);
        const raw = new Uint8Array(count * 2);
        for (let index = 0; index < count; index++) {
          const sample = Math.max(-1, Math.min(1, input[Math.floor(index * context.sampleRate / 24000)]));
          const value = Math.round(sample * (sample < 0 ? 32768 : 32767));
          raw[index * 2] = value & 255;
          raw[index * 2 + 1] = (value >> 8) & 255;
        }
        let binary = "";
        for (const byte of raw) binary += String.fromCharCode(byte);
        if (socket.bufferedAmount < 240000) {
          socket.send(JSON.stringify({ type: "audio", sequence: sequence++, audio: btoa(binary) }));
        }
      };
      source.connect(processor);
      processor.connect(context.destination);
      captureRef.current = { stream, context, source, processor };
      setIsListening(true);
    };
    void startVoice().catch(() => {
      stopVoice();
      startFallbackRecognition(voiceSessionId);
    });
  };

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t.copilot.title}
      className="fixed inset-y-0 right-0 z-50 w-full sm:w-[460px] bg-white dark:bg-[#0B132B] border-l border-slate-200/80 dark:border-white/[0.08] shadow-2xl flex flex-col transition-all duration-300 animate-in slide-in-from-right"
    >
      {/* Header */}
      <div className="p-4 border-b border-slate-200/80 dark:border-white/[0.08] bg-slate-50/70 dark:bg-[#060B13]/60 backdrop-blur-md flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-[#0076FF] to-[#00D4FF] text-white shadow-sm shadow-blue-500/20">
            <Sparkles className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold tracking-tight text-slate-900 dark:text-[#F4F7FB]">
                {t.copilot.title}
              </h2>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-50 text-blue-700 dark:bg-[#0076FF]/15 dark:text-[#00D4FF] border border-blue-200 dark:border-[#0076FF]/30">
                v2.4
              </span>
            </div>
            <p className="text-[11px] text-slate-500 dark:text-[#94A3B8] flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
              {t.copilot.statusActive}
            </p>
          </div>
        </div>

        <button
          onClick={() => { stopVoice(); onClose(); }}
          aria-label={t.common.close}
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-white/[0.08] transition-colors"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Active Data Sources — grounding context for the AI */}
      <div className="px-4 py-2.5 bg-white dark:bg-[#0B132B] border-b border-slate-100 dark:border-white/[0.04]">
        <div className="text-[10px] uppercase font-bold tracking-wider text-slate-400 dark:text-slate-500 mb-2">
          {t.copilot.activeSourcesLabel}
        </div>
        <div className="flex items-center gap-2 flex-wrap text-[10px] font-semibold text-slate-700 dark:text-slate-300">
          {activeSources.length === 0
            ? <span>{t.copilot.noActiveSources}</span>
            : activeSources.map((source) => (
                <span key={source.source_id} className="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200/70 dark:border-emerald-800/50 text-emerald-700 dark:text-emerald-400">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  {source.display_name}
                </span>
              ))}
        </div>
      </div>

      {/* Quick Action Pills */}
      <div className="p-3 border-b border-slate-100 dark:border-white/[0.04] bg-white dark:bg-[#0B132B]">
        <div className="text-[10px] uppercase font-semibold text-slate-400 dark:text-slate-500 mb-2 tracking-wider">
          {t.copilot.quickPills.analyzeSales}
        </div>
        <div className="flex flex-wrap gap-1.5">
          <button
            onClick={() => handleSend(t.copilot.quickPills.analyzeSales)}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs bg-slate-100 dark:bg-white/[0.06] hover:bg-blue-50 hover:text-[#0076FF] dark:hover:bg-[#172652] dark:hover:text-[#00D4FF] text-slate-700 dark:text-[#F4F7FB] transition-colors border border-transparent hover:border-blue-200 dark:hover:border-[#0076FF]/40 font-medium"
          >
            <TrendingUp className="w-3 h-3 text-[#0076FF]" />
            {t.copilot.quickPills.analyzeSales}
          </button>
          <button
            onClick={() => handleSend(t.copilot.quickPills.forecastDemand)}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs bg-slate-100 dark:bg-white/[0.06] hover:bg-blue-50 hover:text-[#0076FF] dark:hover:bg-[#172652] dark:hover:text-[#00D4FF] text-slate-700 dark:text-[#F4F7FB] transition-colors border border-transparent hover:border-blue-200 dark:hover:border-[#0076FF]/40 font-medium"
          >
            <Sparkles className="w-3 h-3 text-[#00D4FF]" />
            {t.copilot.quickPills.forecastDemand}
          </button>
          <button
            onClick={() => handleSend(t.copilot.quickPills.detectAnomalies)}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs bg-slate-100 dark:bg-white/[0.06] hover:bg-blue-50 hover:text-[#0076FF] dark:hover:bg-[#172652] dark:hover:text-[#00D4FF] text-slate-700 dark:text-[#F4F7FB] transition-colors border border-transparent hover:border-blue-200 dark:hover:border-[#0076FF]/40 font-medium"
          >
            <AlertTriangle className="w-3 h-3 text-amber-500" />
            {t.copilot.quickPills.detectAnomalies}
          </button>
          <button
            onClick={() => handleSend(t.copilot.quickPills.generateReport)}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs bg-slate-100 dark:bg-white/[0.06] hover:bg-blue-50 hover:text-[#0076FF] dark:hover:bg-[#172652] dark:hover:text-[#00D4FF] text-slate-700 dark:text-[#F4F7FB] transition-colors border border-transparent hover:border-blue-200 dark:hover:border-[#0076FF]/40 font-medium"
          >
            <FileSpreadsheet className="w-3 h-3 text-emerald-500" />
            {t.copilot.quickPills.generateReport}
          </button>
        </div>
      </div>

      {/* Messages Scroll Area */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-4 space-y-4 bg-slate-50/40 dark:bg-[#060B13]/30"
      >
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-6 text-slate-500 dark:text-[#94A3B8]">
            <div className="w-12 h-12 rounded-2xl bg-blue-50 dark:bg-[#111D3D] text-[#0076FF] dark:text-[#00D4FF] flex items-center justify-center mb-3">
              <Sparkles className="w-6 h-6" />
            </div>
            <div className="font-semibold text-sm text-slate-800 dark:text-[#F4F7FB]">
              {t.copilot.title}
            </div>
            <p className="mt-1 text-xs max-w-xs leading-relaxed">
              {t.copilot.emptyPrompt}
            </p>
          </div>
        ) : (
          messages.map((m) => (
            <div
              key={m.id}
              className={`flex gap-3 ${m.sender === "user" ? "justify-end" : "justify-start"}`}
            >
              {m.sender === "copilot" && (
                <div className="flex-none w-7 h-7 rounded-xl bg-gradient-to-tr from-[#0076FF] to-[#00D4FF] text-white flex items-center justify-center text-xs mt-1">
                  <Bot className="w-4 h-4" />
                </div>
              )}
              <div
                className={`max-w-[85%] rounded-2xl p-3.5 text-xs leading-relaxed shadow-xs ${
                  m.sender === "user"
                    ? "bg-[#0076FF] text-white rounded-tr-none"
                    : "bg-white dark:bg-[#111D3D] text-slate-900 dark:text-[#F4F7FB] border border-slate-200/80 dark:border-white/[0.08] rounded-tl-none"
                }`}
              >
                <div>{m.content}</div>

                {m.sender === "copilot" && m.grounded && (
                  <div className="mt-2.5 pt-2 border-t border-slate-100 dark:border-white/[0.06] flex items-center justify-between text-[10px] text-slate-400 dark:text-slate-500">
                    <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-medium">
                      <ShieldCheck className="w-3 h-3" />
                      {t.copilot.groundedBadge}
                    </span>
                  </div>
                )}

                <div
                  className={`mt-1 text-[9px] text-right ${
                    m.sender === "user" ? "text-blue-100" : "text-slate-400 dark:text-slate-500"
                  }`}
                >
                  {m.timestamp}
                </div>
              </div>
              {m.sender === "user" && (
                <div className="flex-none w-7 h-7 rounded-xl bg-slate-200 dark:bg-white/[0.1] text-slate-700 dark:text-white flex items-center justify-center text-xs mt-1">
                  <User className="w-4 h-4" />
                </div>
              )}
            </div>
          ))
        )}

        {isThinking && (
          <div className="flex gap-3 justify-start items-center text-xs text-slate-500 dark:text-[#94A3B8]">
            <div className="w-7 h-7 rounded-xl bg-gradient-to-tr from-[#0076FF] to-[#00D4FF] text-white flex items-center justify-center">
              <RefreshCw className="w-4 h-4 animate-spin" />
            </div>
            <span className="animate-pulse">{t.copilot.statusThinking}</span>
          </div>
        )}
      </div>

      {/* Input Form */}
      <div className="p-3 border-t border-slate-200/80 dark:border-white/[0.08] bg-white dark:bg-[#0B132B]">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex items-center gap-2"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={t.copilot.inputPlaceholder}
            className="flex-1 bg-slate-100 dark:bg-[#111D3D] border border-transparent focus:border-[#0076FF] rounded-xl px-3.5 py-2.5 text-xs text-slate-900 dark:text-[#F4F7FB] placeholder-slate-400 dark:placeholder-slate-500 outline-none transition-colors"
          />
          <button
            type="button"
            onClick={toggleListening}
            aria-label={isListening ? "Stop microphone" : "Start microphone"}
            className={`h-9 w-9 rounded-xl border flex items-center justify-center transition-colors ${isListening ? "border-rose-400 bg-rose-50 text-rose-600" : "border-slate-200 text-slate-500 hover:border-[#0076FF] hover:text-[#0076FF]"}`}
          >
            {isListening ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
          </button>
          <button
            type="submit"
            disabled={!input.trim() || isThinking}
            aria-label={t.copilot.sendButton}
            className="h-9 w-9 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] disabled:opacity-50 text-white flex items-center justify-center transition-colors shadow-xs"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
        <p className="mt-2 text-[10px] text-slate-400 dark:text-slate-500 text-center leading-normal">
          {t.copilot.disclaimer}
        </p>
      </div>
    </div>
  );
}
