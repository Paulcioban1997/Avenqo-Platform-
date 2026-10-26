"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import {
  Sparkles,
  X,
  Send,
  Bot,
  User,
  ShieldCheck,
  RefreshCw,
  Mic,
  MicOff,
  MessageSquare,
  Radio,
  Plus,
  History,
  Volume2,
  VolumeX,
  Square,
  RadioTower,
  ChevronDown,
  ShieldAlert,
  AlertCircle,
} from "lucide-react";
import type { AppTranslations } from "@/lib/i18n/app-dictionary";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAuthHeaders } from "@/lib/api-headers";
import { useSession } from "@/lib/session-context";
import { RequestFailure } from "@/components/ui/request-failure";
import { getApplicationCatalog } from "@/lib/i18n/generated-app-catalogs";
import { apiFetch, ApiRequestError } from "@/lib/api-request";
import { CANONICAL_LOCALES } from "@/lib/i18n/canonical-locales.generated";

function getBcp47ForLocale(localeCode: string): string {
  const found = CANONICAL_LOCALES.find((l) => l.code === localeCode);
  if (found?.bcp47) return found.bcp47;
  if (localeCode === "fr") return "fr-CA";
  if (localeCode === "en") return "en-US";
  if (localeCode === "es") return "es-ES";
  if (localeCode === "pt") return "pt-BR";
  return localeCode;
}

interface BrowserSpeechRecognition {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}

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
  sourceName?: string;
}

export type CopilotMode = "text" | "mic" | "live";
export type LiveVoiceState =
  | "idle"
  | "connecting"
  | "connected"
  | "listening"
  | "thinking"
  | "speaking"
  | "interrupted"
  | "error";

export function AvenqoCopilot({
  isOpen,
  onClose,
  activeRoute,
  t,
}: AvenqoCopilotProps) {
  const { locale } = useLocale();
  const [mode, setMode] = useState<CopilotMode>("text");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isThinking, setIsThinking] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversationTitle, setConversationTitle] = useState<string>("");
  const [conversationsList, setConversationsList] = useState<Array<{ id: string; title: string; created_at: string }>>([]);
  const [showHistoryDropdown, setShowHistoryDropdown] = useState(false);
  const session = useSession();
  const activeSources = session.activeDataSources;

  // Microphone dictation state (Mode 2)
  const [isDictating, setIsDictating] = useState(false);
  const [voiceReplyEnabled, setVoiceReplyEnabled] = useState(true);

  // Live Voice Real-Time state (Mode 3)
  const [liveState, setLiveState] = useState<LiveVoiceState>("idle");
  const [liveErrorMessage, setLiveErrorMessage] = useState<string | null>(null);
  const [isMuted, setIsMuted] = useState(false);
  const [voiceSessionId, setVoiceSessionId] = useState<string | null>(null);
  const [liveTranscriptUser, setLiveTranscriptUser] = useState("");
  const [liveTranscriptAssistant, setLiveTranscriptAssistant] = useState("");

  const recognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const voiceSocketRef = useRef<WebSocket | null>(null);
  const captureRef = useRef<{
    stream: MediaStream;
    context: AudioContext;
    source: MediaStreamAudioSourceNode;
    processor: ScriptProcessorNode;
  } | null>(null);
  const playbackRef = useRef<{
    context: AudioContext;
    nextTime: number;
    sources: Set<AudioBufferSourceNode>;
  } | null>(null);
  const isMutedRef = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const pendingRequestRef = useRef<{ content: string; key: string } | null>(null);
  const fallbackVoiceRef = useRef(false);
  const voiceGenerationRef = useRef(0);

  isMutedRef.current = isMuted;

  // Auto-scroll on message change
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isThinking, liveTranscriptAssistant]);

  // Load previous conversations list on drawer open
  const loadConversations = useCallback(async () => {
    try {
      const headers = {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
      };
      const res = await apiFetch("/api/v1/ai/chat/conversations?limit=15", { headers });
      if (res.ok) {
        const list = await res.json();
        if (Array.isArray(list)) {
          setConversationsList(list);
          if (!conversationId && list.length > 0) {
            // Restore most recent conversation
            setConversationId(list[0].id);
            setConversationTitle(list[0].title);
            void loadConversationMessages(list[0].id);
          }
        }
      }
    } catch {
      // Graceful fallback
    }
  }, [conversationId]);

  const loadConversationMessages = async (convId: string) => {
    try {
      const headers = {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
      };
      const res = await apiFetch(`/api/v1/ai/chat/conversations/${convId}`, { headers });
      if (res.ok) {
        const detail = await res.json();
        setConversationTitle(detail.title || "Conversation");
        if (Array.isArray(detail.messages)) {
          const loaded: ChatMessage[] = detail.messages.map((m: any) => ({
            id: m.id,
            sender: m.role === "user" ? "user" : "copilot",
            content: m.content,
            timestamp: new Date(m.created_at || Date.now()).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
            grounded: m.role !== "user",
          }));
          setMessages(loaded);
        }
      }
    } catch {
      // Fallback
    }
  };

  useEffect(() => {
    if (isOpen) {
      void loadConversations();
    }
  }, [isOpen, loadConversations]);

  const handleSelectConversation = (conv: { id: string; title: string }) => {
    setConversationId(conv.id);
    setConversationTitle(conv.title);
    setShowHistoryDropdown(false);
    void loadConversationMessages(conv.id);
  };

  const handleNewConversation = async () => {
    setConversationId(null);
    setConversationTitle("");
    setMessages([]);
    setShowHistoryDropdown(false);
    if (liveState !== "idle") {
      stopVoice();
    }
  };

  const handleSend = async (textToSend?: string, voiceSessionOverride?: string | null) => {
    const query = (textToSend || input).trim();
    if (!query || isThinking) return;
    const pendingRequest = pendingRequestRef.current?.content === query
      ? pendingRequestRef.current
      : { content: query, key: crypto.randomUUID() };
    pendingRequestRef.current = pendingRequest;

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
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
        ...getAuthHeaders(),
      };

      let activeConversationId = conversationId;
      if (activeConversationId === null) {
        const conversationResponse = await apiFetch("/api/v1/ai/chat/conversations", {
          method: "POST",
          headers,
          body: JSON.stringify({ title: query.slice(0, 54), locale }),
        });
        if (!conversationResponse.ok) throw new Error("Conversation creation failed");
        const conversation = await conversationResponse.json();
        activeConversationId = conversation.id;
        setConversationId(activeConversationId);
        setConversationTitle(conversation.title || query.slice(0, 54));
        void loadConversations();
      }

      const voiceSession = voiceSessionOverride ?? voiceSessionId;
      const res = voiceSession
        ? await apiFetch(`/api/v1/ai/voice/sessions/${voiceSession}/turn`, {
            method: "POST",
            headers: {
              ...headers,
              "Idempotency-Key": pendingRequest.key,
            },
            body: JSON.stringify({ transcript: query, request_id: pendingRequest.key }),
          })
        : await apiFetch(
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
        const outcomes: Array<{ success?: boolean; error?: string; data?: { error?: string } }> = Array.isArray(data.tool_outcomes) ? data.tool_outcomes : [];
        const toolError = outcomes.find((outcome) => !outcome.success)?.error
          || outcomes.find((outcome) => outcome.data?.error)?.data?.error;
        const copilotMsg: ChatMessage = {
          id: crypto.randomUUID(),
          sender: "copilot",
          content: (typeof data.answer === "string" && data.answer.trim()) || (typeof toolError === "string" ? toolError : t.copilot.errorPrompt),
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          grounded: Boolean(data.grounded_source && data.status === "success"),
          sourceName: data.grounded_source || undefined,
        };
        setMessages((prev) => [...prev, copilotMsg]);

        // Voice reply in dictation or fallback voice mode if enabled
        if ((mode === "mic" || fallbackVoiceRef.current) && voiceReplyEnabled && data.answer && "speechSynthesis" in window) {
          const spoken = new SpeechSynthesisUtterance(data.answer);
          spoken.lang = getBcp47ForLocale(locale);
          spoken.onend = () => {
            if (fallbackVoiceRef.current) startFallbackRecognition(voiceSession);
          };
          spoken.onerror = () => {
            fallbackVoiceRef.current = false;
            setIsDictating(false);
          };
          window.speechSynthesis.speak(spoken);
        }
      } else {
        const errorMsg: ChatMessage = {
          id: crypto.randomUUID(),
          sender: "copilot",
          content: t.copilot.errorPrompt,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          grounded: false,
        };
        setMessages((prev) => [...prev, errorMsg]);
      }
    } catch (error) {
      const errorMsg: ChatMessage = {
        id: crypto.randomUUID(),
        sender: "copilot",
        content: error instanceof ApiRequestError && error.publicMessage ? error.publicMessage : t.copilot.errorPrompt,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        grounded: false,
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsThinking(false);
    }
  };

  const stopVoice = () => {
    voiceGenerationRef.current += 1;
    fallbackVoiceRef.current = false;
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
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
    setIsDictating(false);
    setLiveState("idle");
    setLiveTranscriptUser("");
    setLiveTranscriptAssistant("");
  };

  // Mode 2: Dictation Fallback / Web Speech API
  const startFallbackRecognition = (sessionId: string | null) => {
    const speechWindow = window as Window & {
      SpeechRecognition?: new () => BrowserSpeechRecognition;
      webkitSpeechRecognition?: new () => BrowserSpeechRecognition;
    };
    const Recognition = speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition;
    if (!Recognition) {
      setIsDictating(false);
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          sender: "copilot",
          content: locale.startsWith("fr")
            ? "La reconnaissance vocale n’est pas disponible dans ce navigateur. Utilisez le mode texte ou autorisez le microphone."
            : "Voice recognition is not available in this browser. Please use text or grant microphone permissions.",
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
      return;
    }
    const recognition = new Recognition();
    fallbackVoiceRef.current = true;
    recognition.interimResults = true;
    recognition.continuous = false;
    let transcript = "";
    recognition.onresult = (event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => {
      transcript = Array.from(event.results as ArrayLike<ArrayLike<{ transcript: string }>>)
        .map((result: ArrayLike<{ transcript: string }>) => result[0]?.transcript || "")
        .join(" ");
      setInput(transcript);
      setLiveTranscriptUser(transcript);
    };
    recognition.onerror = () => {
      fallbackVoiceRef.current = false;
      setIsDictating(false);
    };
    recognition.onend = () => {
      recognitionRef.current = null;
      if (fallbackVoiceRef.current && transcript.trim()) {
        void handleSend(transcript, sessionId);
      } else {
        setIsDictating(false);
      }
    };
    recognitionRef.current = recognition;
    setIsDictating(true);
    recognition.start();
  };

  const toggleDictation = () => {
    if (isDictating) {
      stopVoice();
      return;
    }
    startFallbackRecognition(voiceSessionId);
  };

  // Mode 3: Live Real-Time Voice over WebSocket with State Machine
  const startLiveVoiceSession = async () => {
    if (liveState !== "idle" && liveState !== "error") {
      stopVoice();
      return;
    }

    const generation = ++voiceGenerationRef.current;
    setLiveErrorMessage(null);
    setLiveState("connecting");
    const ensureActive = () => {
      if (voiceGenerationRef.current !== generation) throw new Error("Voice start cancelled");
    };

    // 1. Verify microphone support (WebRTC MediaDevices or Web Speech API)
    let userStream: MediaStream | null = null;
    if (navigator.mediaDevices?.getUserMedia) {
      try {
        userStream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
      } catch {
        // MediaStream permission denied or device not found
      }
    }

    if (!userStream) {
      const speechWindow = typeof window !== "undefined" ? (window as any) : {};
      const hasSpeechRec = Boolean(speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition);
      if (hasSpeechRec) {
        setLiveState("connected");
        startFallbackRecognition(voiceSessionId);
        return;
      }
      setLiveState("error");
      setLiveErrorMessage(
        locale === "fr"
          ? "L'accès au microphone est requis. Veuillez autoriser le microphone dans les paramètres de votre navigateur pour converser avec Central AI."
          : "Microphone permission is required. Please allow microphone access in your browser settings to speak with Central AI."
      );
      return;
    }

    ensureActive();

    const playbackContext = new AudioContext({ sampleRate: 24000 });
    void playbackContext.resume();
    playbackRef.current = { context: playbackContext, nextTime: 0, sources: new Set() };

    try {
      let sessionId = voiceSessionId;
      let activeConversationId = conversationId;
      if (!activeConversationId) {
        const conversationResponse = await apiFetch("/api/v1/ai/chat/conversations", {
          method: "POST",
          headers: { "Content-Type": "application/json", ...getAuthHeaders() },
          body: JSON.stringify({ title: "Central Voice Live", locale }),
        });
        if (conversationResponse.ok) {
          const created = await conversationResponse.json();
          activeConversationId = created.id;
          setConversationId(activeConversationId);
          setConversationTitle(created.title || "Central Voice Live");
          void loadConversations();
        }
      }
      ensureActive();

      if (!sessionId && activeConversationId) {
        const response = await apiFetch("/api/v1/ai/voice/sessions", {
          method: "POST",
          headers: { "Content-Type": "application/json", ...getAuthHeaders() },
          body: JSON.stringify({
            conversation_id: activeConversationId,
            locale,
            entrypoint: "central",
            request_id: crypto.randomUUID(),
          }),
        });
        if (response.ok) {
          const sess = await response.json();
          sessionId = sess.id;
          setVoiceSessionId(sessionId);
        }
      }
      ensureActive();

      if (!sessionId) {
        userStream.getTracks().forEach((track) => track.stop());
        void playbackRef.current?.context.close();
        playbackRef.current = null;
        setLiveState("error");
        setLiveErrorMessage(
          locale === "fr"
            ? "Impossible d'initialiser la session vocale sur le serveur Avenqo."
            : "Failed to initialize voice session on Avenqo server."
        );
        return;
      }

      const ticketResponse = await apiFetch(`/api/v1/ai/voice/sessions/${sessionId}/stream-ticket`, {
        method: "POST",
        headers: getAuthHeaders(),
      });
      if (!ticketResponse.ok) {
        userStream.getTracks().forEach((track) => track.stop());
        void playbackRef.current?.context.close();
        playbackRef.current = null;
        setLiveState("error");
        setLiveErrorMessage(
          locale === "fr"
            ? "Le jeton d'accès au flux temps réel est indisponible. Vérifiez votre abonnement et vos crédits IA."
            : "Voice stream ticket is unavailable. Please verify your subscription and AI credits."
        );
        return;
      }

      const { ticket, realtime: available, stream_url: streamUrl } = await ticketResponse.json();
      ensureActive();

      if (!available) {
        userStream.getTracks().forEach((track) => track.stop());
        void playbackRef.current?.context.close();
        playbackRef.current = null;
        const hasSpeech = "SpeechRecognition" in window || "webkitSpeechRecognition" in window;
        if (hasSpeech) {
          setLiveState("connected");
          setTimeout(() => {
            setLiveState("listening");
            startFallbackRecognition(sessionId);
          }, 400);
          return;
        }
        setLiveState("error");
        setLiveErrorMessage(
          locale === "fr"
            ? "Le flux audio temps réel (WebRTC/WebSocket) n'est pas activé sur cet environnement. Utilisez le mode texte ou dictez votre message."
            : "Real-time audio streaming is not enabled in this environment. Please use text mode or dictation."
        );
        return;
      }

      const origin = window.location.origin.replace(/^http/, "ws");
      const socket = new WebSocket(streamUrl || `${origin}/api/v1/ai/voice/sessions/${sessionId}/stream`, [
        "avenqo.voice",
        `ticket.${ticket}`,
      ]);
      voiceSocketRef.current = socket;
      let sequence = -1;

      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data);

          if (event.type === "lifecycle" && Number.isInteger(event.next_audio_sequence)) {
            sequence = Math.max(sequence, event.next_audio_sequence);
            setLiveState("listening");
          }

          if (event.type === "error" && event.status === "text_fallback") {
            stopVoice();
            startFallbackRecognition(sessionId);
            return;
          }

          // Natural Barge-In interruption: immediately silence buffer queue
          if (event.type === "lifecycle" && event.status === "interrupted") {
            setLiveState("interrupted");
            const playback = playbackRef.current;
            if (playback) {
              for (const source of playback.sources) source.stop();
              playback.sources.clear();
              playback.nextTime = playback.context.currentTime;
            }
            setTimeout(() => {
              if (voiceSocketRef.current === socket) setLiveState("listening");
            }, 600);
          }

          if (event.type === "transcript") {
            if (event.transcript) {
              setLiveTranscriptUser(event.transcript);
            }
            if (event.status === "final") {
              setLiveState("thinking");
              setMessages((prev) => [
                ...prev,
                {
                  id: crypto.randomUUID(),
                  sender: "user",
                  content: event.transcript,
                  timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
                },
              ]);
            }
          }

          if (event.type === "answer") {
            window.dispatchEvent(new Event("avenqo:ai-credits-updated"));
            if (event.answer) {
              setLiveTranscriptAssistant(event.answer);
              setMessages((prev) => [
                ...prev,
                {
                  id: crypto.randomUUID(),
                  sender: "copilot",
                  content: event.answer,
                  timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
                  grounded: true,
                },
              ]);
            }
          }

          if (event.type === "audio" && event.format === "pcm16") {
            setLiveState("speaking");
            const playback =
              playbackRef.current ?? {
                context: new AudioContext({ sampleRate: 24000 }),
                nextTime: 0,
                sources: new Set<AudioBufferSourceNode>(),
              };
            playbackRef.current = playback;
            void playback.context.resume();
            const raw = atob(event.audio);
            const buffer = playback.context.createBuffer(1, raw.length / 2, 24000);
            const samples = buffer.getChannelData(0);
            for (let index = 0; index < samples.length; index++) {
              const value = raw.charCodeAt(index * 2) | (raw.charCodeAt(index * 2 + 1) << 8);
              samples[index] = (value > 32767 ? value - 65536 : value) / 32768;
            }
            const source = playback.context.createBufferSource();
            source.buffer = buffer;
            playback.sources.add(source);
            source.onended = () => {
              playback.sources.delete(source);
              if (playback.sources.size === 0) {
                setLiveState("listening");
              }
            };
            source.connect(playback.context.destination);
            source.start(Math.max(playback.context.currentTime, playback.nextTime));
            playback.nextTime = Math.max(playback.context.currentTime, playback.nextTime) + buffer.duration;
          }
        } catch {
          // ignore parsing error
        }
      };

      socket.onclose = () => {
        if (voiceSocketRef.current === socket && captureRef.current) {
          stopVoice();
          startFallbackRecognition(sessionId);
        }
      };

      await new Promise<void>((resolve, reject) => {
        const timeout = window.setTimeout(() => reject(new Error(locale === "fr" ? "Délai de connexion dépassé" : "Voice connection timed out")), 15000);
        socket.onopen = () => {
          window.clearTimeout(timeout);
          setLiveState("connected");
          resolve();
        };
        socket.onerror = () => {
          window.clearTimeout(timeout);
          reject(new Error(locale === "fr" ? "Flux vocal temps réel indisponible" : "Voice stream unavailable"));
        };
      });

      ensureActive();

      const context = new AudioContext({ sampleRate: 24000 });
      const source = context.createMediaStreamSource(userStream);
      const processor = context.createScriptProcessor(2048, 1, 1);

      processor.onaudioprocess = (event) => {
        if (socket.readyState !== WebSocket.OPEN || sequence < 0 || isMutedRef.current) return;
        const inputBuffer = event.inputBuffer.getChannelData(0);
        const count = Math.floor((inputBuffer.length * 24000) / context.sampleRate);
        const raw = new Uint8Array(count * 2);
        for (let index = 0; index < count; index++) {
          const sample = Math.max(-1, Math.min(1, inputBuffer[Math.floor((index * context.sampleRate) / 24000)]));
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
      captureRef.current = { stream: userStream, context, source, processor };
      setLiveState("listening");
    } catch (err) {
      if (voiceGenerationRef.current !== generation) return;
      stopVoice();
      setLiveState("error");
      setLiveErrorMessage(
        err instanceof Error && err.message
          ? err.message
          : locale === "fr"
          ? "Échec de connexion au flux vocal temps réel. Veuillez réessayer."
          : "Failed to connect to real-time voice stream. Please try again."
      );
    }
  };

  const toggleVoiceStream = () => {
    if (liveState !== "idle" || isDictating) {
      stopVoice();
    } else {
      void startLiveVoiceSession();
    }
  };

  if (!isOpen) return null;

  return (
    <div
      id="avenqo-central-dialog"
      role="dialog"
      aria-modal="true"
      aria-label={t.copilot.title}
      className="fixed inset-y-0 right-0 z-50 w-full sm:w-[480px] bg-white dark:bg-[#0B132B] border-l border-slate-200/80 dark:border-white/[0.08] shadow-2xl flex flex-col transition-all duration-300 animate-in slide-in-from-right"
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
                {locale === "fr" ? "Central AI" : "Central AI"}
              </span>
            </div>
            <p className="text-[11px] text-slate-500 dark:text-[#94A3B8] flex items-center gap-1">
              {locale === "fr" ? "Assistant conversationnel unifié tri-modal" : "Unified tri-modal conversational AI"}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1">
          {/* New conversation button */}
          <button
            type="button"
            onClick={handleNewConversation}
            title={locale === "fr" ? "Nouvelle conversation" : "New conversation"}
            aria-label="New conversation"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-white/[0.08] transition-colors"
          >
            <Plus className="w-4 h-4" />
          </button>

          {/* History dropdown toggle */}
          <button
            type="button"
            onClick={() => setShowHistoryDropdown((prev) => !prev)}
            title={locale === "fr" ? "Historique des conversations" : "Conversation history"}
            aria-label="Conversation history"
            className={`p-1.5 rounded-lg transition-colors ${
              showHistoryDropdown
                ? "bg-blue-50 text-[#0076FF] dark:bg-white/[0.12] dark:text-[#00D4FF]"
                : "text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-white/[0.08]"
            }`}
          >
            <History className="w-4 h-4" />
          </button>

          <button
            type="button"
            onClick={() => {
              stopVoice();
              onClose();
            }}
            aria-label={t.common.close}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-white/[0.08] transition-colors ml-1"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* History Dropdown Overlay */}
      {showHistoryDropdown && (
        <div className="p-3 bg-slate-50 dark:bg-[#080E1E] border-b border-slate-200 dark:border-white/[0.08] space-y-2 animate-in fade-in duration-150">
          <div className="flex items-center justify-between text-[11px] font-bold text-slate-500 uppercase tracking-wider">
            <span>{locale === "fr" ? "Historique des conversations" : "Conversation History"}</span>
            <button
              onClick={handleNewConversation}
              className="text-[#0076FF] hover:underline flex items-center gap-1 font-semibold normal-case"
            >
              <Plus size={12} />
              {locale === "fr" ? "Nouvelle" : "New"}
            </button>
          </div>
          <div className="max-h-48 overflow-y-auto space-y-1">
            {conversationsList.length === 0 ? (
              <p className="text-xs text-slate-400 italic py-2 text-center">
                {locale === "fr" ? "Aucune conversation antérieure" : "No previous conversations"}
              </p>
            ) : (
              conversationsList.map((conv) => (
                <button
                  key={conv.id}
                  onClick={() => handleSelectConversation(conv)}
                  className={`w-full text-left px-3 py-2 rounded-lg text-xs transition-colors flex items-center justify-between ${
                    conversationId === conv.id
                      ? "bg-blue-50 text-[#0076FF] font-semibold dark:bg-[#0076FF]/15 dark:text-[#00D4FF]"
                      : "text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-white/[0.06]"
                  }`}
                >
                  <span className="truncate pr-2">{conv.title || "Conversation sans titre"}</span>
                  <span className="text-[10px] text-slate-400 shrink-0">
                    {new Date(conv.created_at).toLocaleDateString([], { month: "short", day: "numeric" })}
                  </span>
                </button>
              ))
            )}
          </div>
        </div>
      )}

      {/* Tri-Modal Tab Switcher */}
      <div className="grid grid-cols-3 p-1.5 bg-slate-100 dark:bg-[#060B13] border-b border-slate-200/80 dark:border-white/[0.06] text-xs font-semibold">
        <button
          type="button"
          onClick={() => {
            if (liveState !== "idle") stopVoice();
            setMode("text");
          }}
          className={`py-2 rounded-lg flex items-center justify-center gap-2 transition-all ${
            mode === "text"
              ? "bg-white dark:bg-[#111D3D] text-[#0076FF] dark:text-[#00D4FF] shadow-xs"
              : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
          }`}
        >
          <MessageSquare className="w-3.5 h-3.5" />
          <span>{locale === "fr" ? "Texte" : "Text"}</span>
        </button>

        <button
          type="button"
          onClick={() => {
            if (liveState !== "idle") stopVoice();
            setMode("mic");
          }}
          className={`py-2 rounded-lg flex items-center justify-center gap-2 transition-all ${
            mode === "mic"
              ? "bg-white dark:bg-[#111D3D] text-[#0076FF] dark:text-[#00D4FF] shadow-xs"
              : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
          }`}
        >
          <Mic className="w-3.5 h-3.5" />
          <span>{locale === "fr" ? "Microphone" : "Microphone"}</span>
        </button>

        <button
          type="button"
          onClick={() => {
            setMode("live");
          }}
          className={`py-2 rounded-lg flex items-center justify-center gap-2 transition-all relative ${
            mode === "live"
              ? "bg-white dark:bg-[#111D3D] text-[#0076FF] dark:text-[#00D4FF] shadow-xs"
              : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
          }`}
        >
          <Radio className="w-3.5 h-3.5" />
          <span>{locale === "fr" ? "Conversation Live" : "Live Voice"}</span>
          <span className="flex h-1.5 w-1.5 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
          </span>
        </button>
      </div>

      {/* Active Data Sources — grounding context for the AI */}
      <div className="px-4 py-2 bg-white dark:bg-[#0B132B] border-b border-slate-100 dark:border-white/[0.04]">
        <div className="text-[10px] uppercase font-bold tracking-wider text-slate-400 dark:text-slate-500 mb-1.5 flex items-center justify-between">
          <span>{t.copilot.activeSourcesLabel}</span>
          {conversationTitle && (
            <span className="font-semibold text-slate-500 dark:text-slate-400 truncate max-w-[200px]">
              {conversationTitle}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5 flex-wrap text-[10px] font-semibold text-slate-700 dark:text-slate-300">
          {session.sourceError ? (
            <RequestFailure error={session.sourceError} retry={() => { void session.reload(); }} />
          ) : session.loading ? (
            <span>{getApplicationCatalog(locale).company.connectionsLoading}</span>
          ) : activeSources.length === 0 ? (
            <span className="italic text-slate-400">{t.copilot.noActiveSources}</span>
          ) : (
            activeSources.map((source) => (
              <span
                key={source}
                className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200/70 dark:border-emerald-800/50 text-emerald-700 dark:text-emerald-400"
              >
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                {source}
              </span>
            ))
          )}
        </div>
      </div>

      {/* ========================================================
          MODE 1: TEXT CHAT
          ======================================================== */}
      {mode === "text" && (
        <>
          {/* Quick suggestions follow the active workspace */}
          <div className="p-2.5 border-b border-slate-100 dark:border-white/[0.04] bg-slate-50/50 dark:bg-[#060B13]/30">
            <div className="flex flex-wrap gap-1.5">
              {(activeRoute.startsWith("/billing")
                ? locale === "fr"
                  ? ["Expliquer ma facture", "Voir mon solde de crédits", "Quels modules sont inclus ?"]
                  : ["Explain my invoice", "Show my credit balance", "Which modules are included?"]
                : activeRoute.startsWith("/crm")
                ? locale === "fr"
                  ? ["Afficher mes rendez-vous", "Trouver un client", "Aider à créer un rendez-vous"]
                  : ["Show my appointments", "Find a customer", "Help create an appointment"]
                : activeRoute.startsWith("/retail")
                ? Object.values(t.copilot.quickPills)
                : locale === "fr"
                ? ["Combien ai-je vendu ce mois-ci sur toutes mes boutiques ?", "Quelle boutique performe le mieux ?", "Compare Shopify et WooCommerce sur les 30 derniers jours"]
                : ["How much did I sell across all stores this month?", "Which store performs best?", "Compare Shopify and WooCommerce over the last 30 days"]
              ).map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  disabled={isThinking}
                  onClick={() => void handleSend(prompt)}
                  className="px-2.5 py-1 rounded-full text-[11px] bg-white dark:bg-white/[0.06] border border-slate-200/60 dark:border-white/[0.08] hover:text-[#0076FF] hover:border-[#0076FF]/40 disabled:opacity-50 transition-colors shadow-2xs"
                >
                  {prompt}
                </button>
              ))}
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
                    <div className="flex-none w-7 h-7 rounded-xl bg-gradient-to-tr from-[#0076FF] to-[#00D4FF] text-white flex items-center justify-center text-xs mt-1 shadow-xs">
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
                    <div className="whitespace-pre-wrap">{m.content}</div>

                    {m.sender === "copilot" && m.grounded && (
                      <div className="mt-2.5 pt-2 border-t border-slate-100 dark:border-white/[0.06] flex items-center justify-between text-[10px] text-slate-400 dark:text-slate-500">
                        <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-medium">
                          <ShieldCheck className="w-3 h-3" />
                          {m.sourceName || t.copilot.groundedBadge}
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

          {/* Text Input Form */}
          <div className="p-3 border-t border-slate-200/80 dark:border-white/[0.08] bg-white dark:bg-[#0B132B]">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void handleSend();
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
                onClick={toggleVoiceStream}
                aria-label={liveState !== "idle" || isDictating ? "Stop microphone" : "Start microphone"}
                className={`h-9 w-9 rounded-xl border flex items-center justify-center transition-colors ${
                  liveState !== "idle" || isDictating
                    ? "border-rose-400 bg-rose-50 text-rose-600 dark:bg-rose-950/40 dark:text-rose-400"
                    : "border-slate-200 text-slate-500 hover:border-[#0076FF] hover:text-[#0076FF] dark:border-white/[0.08]"
                }`}
              >
                {liveState !== "idle" || isDictating ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
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
        </>
      )}

      {/* ========================================================
          MODE 2: MICROPHONE / DICTATION
          ======================================================== */}
      {mode === "mic" && (
        <div className="flex-1 flex flex-col justify-between p-6 bg-slate-50/50 dark:bg-[#060B13]/30">
          <div className="space-y-4">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-700 dark:text-slate-300">
              <span>{locale === "fr" ? "Mode Dictée Vocale" : "Voice Dictation Mode"}</span>
              <button
                type="button"
                onClick={() => setVoiceReplyEnabled((prev) => !prev)}
                className="flex items-center gap-1.5 text-[11px] text-[#0076FF] hover:underline"
              >
                {voiceReplyEnabled ? <Volume2 size={13} /> : <VolumeX size={13} />}
                <span>
                  {voiceReplyEnabled
                    ? locale === "fr"
                      ? "Lecture audio activée"
                      : "Voice reply enabled"
                    : locale === "fr"
                    ? "Lecture audio désactivée"
                    : "Voice reply muted"}
                </span>
              </button>
            </div>

            {/* Live dictation transcription box */}
            <div className="min-h-[140px] p-4 rounded-2xl bg-white dark:bg-[#111D3D] border border-slate-200/80 dark:border-white/[0.08] shadow-xs flex flex-col justify-between">
              <div className="text-xs text-slate-900 dark:text-[#F4F7FB] leading-relaxed">
                {input.trim() ? (
                  input
                ) : isDictating ? (
                  <span className="italic text-blue-500 animate-pulse">
                    {locale === "fr"
                      ? "Parlez maintenant, votre question s'affiche ici..."
                      : "Speak now, your question appears here..."}
                  </span>
                ) : (
                  <span className="text-slate-400">
                    {locale === "fr"
                      ? "Cliquez sur le microphone ci-dessous pour dicter votre question à Central AI."
                      : "Click the microphone button below to dictate your question to Central AI."}
                  </span>
                )}
              </div>
              <div className="text-[10px] text-right text-slate-400 mt-2">
                {isDictating
                  ? locale === "fr"
                    ? "Enregistrement en direct..."
                    : "Live recording..."
                  : locale === "fr"
                  ? "Prêt"
                  : "Ready"}
              </div>
            </div>
          </div>

          {/* Central Mic Button */}
          <div className="flex flex-col items-center justify-center my-8 space-y-4">
            <div className="relative">
              {isDictating && (
                <div className="absolute inset-0 rounded-full bg-rose-500/20 animate-ping" />
              )}
              <button
                type="button"
                onClick={toggleDictation}
                className={`relative h-20 w-20 rounded-full flex items-center justify-center transition-all duration-300 shadow-xl ${
                  isDictating
                    ? "bg-rose-500 text-white shadow-rose-500/30 scale-105"
                    : "bg-gradient-to-tr from-[#0076FF] to-[#00D4FF] text-white shadow-blue-500/25 hover:scale-105"
                }`}
              >
                {isDictating ? <MicOff className="w-8 h-8" /> : <Mic className="w-8 h-8" />}
              </button>
            </div>

            <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">
              {isDictating
                ? locale === "fr"
                  ? "Cliquez pour arrêter et envoyer"
                  : "Click to stop and submit"
                : locale === "fr"
                ? "Cliquez pour commencer à parler"
                : "Click to start speaking"}
            </span>
          </div>

          {/* Action bar */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={!input.trim() || isThinking}
              onClick={() => void handleSend(input)}
              className="flex-1 py-2.5 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] disabled:opacity-50 text-white font-semibold text-xs flex items-center justify-center gap-2 shadow-xs transition-colors"
            >
              {isThinking ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>{t.copilot.statusThinking}</span>
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  <span>{locale === "fr" ? "Envoyer la question dictée" : "Send dictated query"}</span>
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* ========================================================
          MODE 3: CONVERSATION LIVE (Bulle IA Animée / Real-Time Voice)
          ======================================================== */}
      {mode === "live" && (
        <div className="flex-1 flex flex-col justify-between p-6 bg-gradient-to-b from-slate-50 to-blue-50/30 dark:from-[#060B13] dark:to-[#0B132B] relative overflow-hidden">
          {/* Top Status Badge */}
          <div className="flex items-center justify-between z-10">
              <div className="flex items-center gap-2">
                <RadioTower
                  className={`w-4 h-4 ${
                    liveState === "listening" || liveState === "speaking"
                      ? "text-emerald-500 animate-pulse"
                      : liveState === "connected"
                      ? "text-cyan-500 animate-pulse"
                      : liveState === "connecting"
                      ? "text-[#0076FF] animate-spin"
                      : liveState === "error"
                      ? "text-rose-500"
                      : "text-slate-400"
                  }`}
                />
                <span className="text-xs font-bold text-slate-800 dark:text-slate-200">
                  {liveState === "idle"
                    ? locale === "fr"
                      ? "Session vocale prête"
                      : "Voice session ready"
                    : liveState === "connecting"
                    ? locale === "fr"
                      ? "Connexion au flux temps réel..."
                      : "Connecting real-time stream..."
                    : liveState === "connected"
                    ? locale === "fr"
                      ? "Connecté · En attente de parole"
                      : "Connected · Waiting for speech"
                    : liveState === "listening"
                    ? locale === "fr"
                      ? "Central AI vous écoute..."
                      : "Central AI is listening..."
                    : liveState === "thinking"
                    ? locale === "fr"
                      ? "Analyse de vos données d'entreprise..."
                      : "Analyzing business data..."
                    : liveState === "speaking"
                    ? locale === "fr"
                      ? "Central AI vous répond..."
                      : "Central AI is answering..."
                    : liveState === "interrupted"
                    ? locale === "fr"
                      ? "Interrompu (Barge-in)"
                      : "Interrupted (Barge-in)"
                    : locale === "fr"
                    ? "Connexion audio interrompue"
                    : "Audio connection failed"}
                </span>
              </div>

              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-200/70 dark:bg-white/[0.08] text-slate-600 dark:text-slate-400">
                {locale.toUpperCase()} · 24 kHz
              </span>
            </div>

            {/* Error Message Alert Card */}
            {liveState === "error" && liveErrorMessage && (
              <div className="my-2 p-3.5 rounded-2xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-800 dark:text-rose-200 text-xs flex flex-col gap-2 z-10 animate-in fade-in">
                <div className="flex items-start gap-2">
                  <ShieldAlert className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                  <span className="font-semibold leading-relaxed">{liveErrorMessage}</span>
                </div>
                <div className="flex items-center gap-2 self-end mt-1">
                  <button
                    type="button"
                    onClick={() => setMode("text")}
                    className="px-3 py-1 rounded-lg bg-white dark:bg-slate-900 border border-rose-200 dark:border-rose-900 text-rose-700 dark:text-rose-300 font-bold text-[11px] hover:bg-rose-100 dark:hover:bg-rose-900/40 transition"
                  >
                    {locale === "fr" ? "Mode texte" : "Text mode"}
                  </button>
                  <button
                    type="button"
                    onClick={() => void startLiveVoiceSession()}
                    className="px-3.5 py-1 rounded-lg bg-rose-600 hover:bg-rose-700 text-white font-bold text-[11px] transition shadow-xs flex items-center gap-1.5"
                  >
                    <RefreshCw className="w-3 h-3" />
                    <span>{locale === "fr" ? "Réessayer" : "Retry"}</span>
                  </button>
                </div>
              </div>
            )}

            {/* Interactive Animated AI Orb */}
            <div className="my-auto flex flex-col items-center justify-center relative py-6">
              {/* Outermost breathing pulse rings */}
              <div
                className={`absolute w-64 h-64 rounded-full transition-all duration-700 pointer-events-none ${
                  liveState === "listening"
                    ? "bg-cyan-500/15 animate-ping"
                    : liveState === "speaking"
                    ? "bg-blue-500/20 animate-pulse"
                    : liveState === "thinking"
                    ? "bg-purple-500/20 animate-spin"
                    : liveState === "interrupted"
                    ? "bg-amber-500/30 scale-110"
                    : liveState === "error"
                    ? "bg-rose-500/10"
                    : "bg-blue-400/5"
                }`}
              />

              <div
                className={`absolute w-52 h-52 rounded-full transition-all duration-500 pointer-events-none ${
                  liveState === "listening"
                    ? "bg-cyan-400/20 scale-105"
                    : liveState === "speaking"
                    ? "bg-emerald-400/20 scale-110"
                    : liveState === "thinking"
                    ? "bg-purple-500/25 scale-100"
                    : liveState === "error"
                    ? "bg-rose-500/15 scale-95"
                    : "bg-slate-400/5"
                }`}
              />

              {/* Core Interactive Glowing Orb Sphere */}
              <div
                className={`relative w-36 h-36 rounded-full flex items-center justify-center shadow-2xl transition-all duration-500 ${
                  liveState === "listening"
                    ? "bg-gradient-to-tr from-[#00D4FF] via-[#0076FF] to-[#00F0FF] shadow-[0_0_50px_rgba(0,212,255,0.5)] scale-105"
                    : liveState === "speaking"
                    ? "bg-gradient-to-tr from-[#10B981] via-[#0076FF] to-[#00D4FF] shadow-[0_0_60px_rgba(16,185,129,0.5)] scale-110"
                    : liveState === "thinking"
                    ? "bg-gradient-to-tr from-[#8B5CF6] via-[#EC4899] to-[#3B82F6] shadow-[0_0_50px_rgba(139,92,246,0.5)] animate-pulse"
                    : liveState === "interrupted"
                    ? "bg-gradient-to-tr from-[#F59E0B] to-[#EF4444] shadow-[0_0_50px_rgba(245,158,11,0.5)]"
                    : liveState === "connecting"
                    ? "bg-gradient-to-tr from-[#0076FF] to-[#8B5CF6] shadow-xl animate-spin"
                    : liveState === "connected"
                    ? "bg-gradient-to-tr from-[#0076FF] to-[#00D4FF] shadow-[0_0_40px_rgba(0,118,255,0.4)] animate-pulse"
                    : liveState === "error"
                    ? "bg-gradient-to-tr from-rose-600 to-amber-600 shadow-xl"
                    : "bg-gradient-to-tr from-slate-200 via-blue-100 to-slate-300 dark:from-[#111D3D] dark:via-[#0076FF]/30 dark:to-[#0B132B] shadow-lg"
                }`}
              >
                {liveState === "thinking" ? (
                  <RefreshCw className="w-12 h-12 text-white animate-spin" />
                ) : liveState === "speaking" ? (
                  <Volume2 className="w-12 h-12 text-white animate-bounce" />
                ) : liveState === "listening" ? (
                  <Mic className="w-12 h-12 text-white" />
                ) : liveState === "error" ? (
                  <AlertCircle className="w-12 h-12 text-white" />
                ) : (
                  <Sparkles className="w-12 h-12 text-slate-400 dark:text-blue-300" />
                )}
              </div>

              <div className="mt-6 text-center">
                <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                  {liveState === "idle"
                    ? locale === "fr"
                      ? "Touchez 'Démarrer la session' pour parler naturellement"
                      : "Touch 'Start session' to speak naturally"
                    : liveState === "connecting"
                    ? locale === "fr"
                      ? "Initialisation du microphone et du flux audio..."
                      : "Initializing microphone and audio stream..."
                    : liveState === "connected"
                    ? locale === "fr"
                      ? "Connexion établie avec succès"
                      : "Connection established successfully"
                    : liveState === "error"
                    ? locale === "fr"
                      ? "Une action est requise pour rétablir la communication"
                      : "Action required to restore communication"
                    : isMuted
                    ? locale === "fr"
                      ? "Microphone coupé (en pause)"
                      : "Microphone muted (paused)"
                    : locale === "fr"
                    ? "Posez vos questions ventes, stocks ou rendez-vous en continu"
                    : "Ask questions on sales, inventory or bookings continuously"}
                </span>
              </div>
            </div>

            {/* Live Subtitle Transcript overlay */}
            <div className="min-h-[85px] max-h-28 overflow-y-auto p-3.5 rounded-2xl bg-white/80 dark:bg-[#111D3D]/80 backdrop-blur-md border border-slate-200/80 dark:border-white/[0.08] text-xs shadow-sm mb-4">
              {liveTranscriptAssistant ? (
                <div className="text-slate-900 dark:text-[#F4F7FB]">
                  <span className="font-bold text-[#0076FF] mr-1.5">Central AI:</span>
                  {liveTranscriptAssistant}
                </div>
              ) : liveTranscriptUser ? (
                <div className="text-slate-700 dark:text-slate-300 italic">
                  <span className="font-bold text-slate-500 mr-1.5">Vous:</span>
                  {liveTranscriptUser}
                </div>
              ) : (
                <div className="text-slate-400 italic text-center py-2">
                  {locale === "fr"
                    ? "Les sous-titres et réponses de votre conversation s'affichent ici en direct."
                    : "Live subtitles and spoken responses appear here in real time."}
                </div>
              )}
            </div>

            {/* Bottom Dock Controls */}
            <div className="flex items-center justify-center gap-3 z-10">
              {liveState === "idle" || liveState === "error" ? (
                <button
                  type="button"
                  onClick={() => void startLiveVoiceSession()}
                  className="flex-1 py-3 px-4 rounded-xl bg-gradient-to-r from-[#0076FF] to-[#00D4FF] hover:from-[#005bd3] hover:to-[#00b2d6] text-white font-bold text-xs flex items-center justify-center gap-2 shadow-lg shadow-blue-500/25 transition-all"
                >
                  <Radio className="w-4 h-4" />
                  <span>
                    {liveState === "error"
                      ? locale === "fr"
                        ? "Réessayer la connexion LIVE"
                        : "Retry LIVE conversation"
                      : locale === "fr"
                      ? "Démarrer la conversation LIVE"
                      : "Start LIVE conversation"}
                  </span>
                </button>
              ) : (
                <>
                  {/* Mute toggle button */}
                  <button
                    type="button"
                    onClick={() => setIsMuted((prev) => !prev)}
                    className={`h-11 px-4 rounded-xl font-semibold text-xs border flex items-center gap-2 transition-colors ${
                      isMuted
                        ? "border-amber-400 bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300"
                        : "border-slate-200 dark:border-white/[0.1] bg-white dark:bg-[#111D3D] text-slate-700 dark:text-slate-200 hover:border-[#0076FF]"
                    }`}
                  >
                    {isMuted ? <MicOff size={15} /> : <Mic size={15} />}
                    <span>{isMuted ? (locale === "fr" ? "Micro coupé" : "Muted") : (locale === "fr" ? "Couper micro" : "Mute")}</span>
                  </button>

                  {/* End Session button */}
                  <button
                    type="button"
                    onClick={stopVoice}
                    className="flex-1 py-3 px-4 rounded-xl bg-rose-600 hover:bg-rose-700 text-white font-bold text-xs flex items-center justify-center gap-2 shadow-lg shadow-rose-600/25 transition-all"
                  >
                    <Square className="w-3.5 h-3.5 fill-current" />
                    <span>{locale === "fr" ? "Terminer la session" : "End session"}</span>
                  </button>
                </>
              )}
            </div>
          </div>
      )}
    </div>
  );
}
