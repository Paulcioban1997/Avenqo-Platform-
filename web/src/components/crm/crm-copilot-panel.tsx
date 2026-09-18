"use client";

import React, { useState, useRef, useEffect } from "react";
import Image from "next/image";
import {
  Send,
  Sparkles,
  Calendar,
  Clock,
  Search,
  Bell,
  BarChart3,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  X,
  ChevronRight,
} from "lucide-react";
import type { AppTranslations } from "@/lib/i18n/app-dictionary";
import { getAuthHeaders } from "@/lib/api-headers";

interface Message {
  id: string;
  sender: "user" | "copilot";
  content: string;
  timestamp: string;
  action?: string;
  status?: "success" | "conflict" | "error";
  details?: any;
}

interface CRMCopilotPanelProps {
  t: AppTranslations;
  userName?: string;
  onAppointmentCreated?: () => void;
  onSelectAction?: (action: string) => void;
  onClose?: () => void;
  isFloating?: boolean;
}

export function CRMCopilotPanel({
  t,
  userName = "Utilisateur",
  onAppointmentCreated,
  onSelectAction,
  onClose,
  isFloating = false,
}: CRMCopilotPanelProps) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome-1",
      sender: "copilot",
      content: `Bonjour ${userName} ! Je suis votre Copilot Avenqo en direct. Comment puis-je vous aider aujourd'hui ?`,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    },
  ]);
  const [isThinking, setIsThinking] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const suggestedActions = [
    { label: "Créer un rendez-vous", query: "Crée un rendez-vous aujourd'hui à 14h30 de physiothérapie d'une durée de 30 minutes.", icon: Calendar },
    { label: "Trouver un créneau libre", query: "Trouve-moi un créneau libre aujourd'hui", icon: Clock },
    { label: "Rechercher un client", query: "Rechercher un client", icon: Search },
    { label: "Envoyer des rappels", query: "Envoyer des rappels de rendez-vous", icon: Bell },
    { label: "Voir mes rendez-vous aujourd'hui", query: "Voir mes rendez-vous aujourd'hui", icon: Calendar },
    { label: "Générer un rapport", query: "Générer un rapport de performance CRM", icon: BarChart3 },
  ];

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isThinking]);

  const handleSendMessage = async (textToSend?: string) => {
    const query = (textToSend || input).trim();
    if (!query || isThinking) return;

    const userMsg: Message = {
      id: `u-${Date.now()}`,
      sender: "user",
      content: query,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsThinking(true);

    try {
      const res = await fetch("/api/v1/crm/copilot/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          message: query,
          locale: "fr",
        }),
      });

      if (res.ok) {
        const data = await res.json();
        const copilotMsg: Message = {
          id: `c-${Date.now()}`,
          sender: "copilot",
          content: data.reply || "Traitement terminé.",
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          status: data.status,
          action: data.action,
          details: data.appointment || data.slots || data.clients || data.kpis,
        };
        setMessages((prev) => [...prev, copilotMsg]);

        // Auto-refresh calendar and KPIs if appointment created
        if (data.action === "appointment_created" || data.status === "success") {
          onAppointmentCreated?.();
        }
      } else {
        const copilotMsg: Message = {
          id: `c-${Date.now()}`,
          sender: "copilot",
          content: "Une erreur est survenue lors de la communication avec le service CRM AI. Veuillez réessayer.",
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          status: "error",
        };
        setMessages((prev) => [...prev, copilotMsg]);
      }
    } catch {
      const copilotMsg: Message = {
        id: `c-${Date.now()}`,
        sender: "copilot",
        content: "Impossible de joindre le serveur CRM. Vérifiez votre connexion.",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        status: "error",
      };
      setMessages((prev) => [...prev, copilotMsg]);
    } finally {
      setIsThinking(false);
    }
  };

  return (
    <aside
      className={`flex flex-col bg-white dark:bg-[#0B132B] border-l border-slate-200/80 dark:border-white/[0.08] transition-all duration-200 ${
        isFloating
          ? "fixed right-0 top-16 bottom-0 w-80 sm:w-96 z-40 shadow-2xl"
          : "w-80 xl:w-96 shrink-0 h-[calc(100vh-5rem)] sticky top-20 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm dark:shadow-none"
      }`}
    >
      {/* COPILOT HEADER */}
      <div className="p-4 border-b border-slate-200/80 dark:border-white/[0.08] flex items-center justify-between bg-slate-50/50 dark:bg-white/[0.02] rounded-t-2xl">
        <div className="flex items-center gap-3">
          <div className="relative">
            <Image
              src="/brand/avenqo-icon.png"
              alt="Avenqo Copilot"
              width={34}
              height={34}
              className="rounded-xl object-contain shadow-xs shadow-blue-500/25"
            />
            <span className="absolute -bottom-0.5 -right-0.5 flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500 border border-white dark:border-[#0B132B]" />
            </span>
          </div>
          <div>
            <div className="font-extrabold text-sm text-slate-900 dark:text-white tracking-tight flex items-center gap-1.5">
              <span>Avenqo Copilot</span>
              <Sparkles className="w-3.5 h-3.5 text-[#00D4FF]" />
            </div>
            <div className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 inline-block" />
              <span>En ligne</span>
            </div>
          </div>
        </div>

        {onClose && (
          <button
            onClick={onClose}
            className="p-1.5 rounded-xl text-slate-400 hover:text-slate-600 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/[0.06] transition"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* CHAT MESSAGES AREA */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3 text-xs">
        {/* SUGGESTED ACTIONS PILLS */}
        <div className="space-y-1.5 pb-2">
          <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 px-1">
            Actions suggérées
          </div>
          <div className="grid grid-cols-1 gap-1.5">
            {suggestedActions.map((act, idx) => {
              const Icon = act.icon;
              return (
                <button
                  key={idx}
                  onClick={() => handleSendMessage(act.query)}
                  className="flex items-center justify-between px-3 py-2 rounded-xl bg-slate-100/80 dark:bg-white/[0.04] hover:bg-blue-50 dark:hover:bg-blue-950/40 text-slate-700 dark:text-[#94A3B8] hover:text-[#0076FF] dark:hover:text-[#00D4FF] border border-slate-200/50 dark:border-white/[0.04] transition group text-left"
                >
                  <div className="flex items-center gap-2 truncate">
                    <Icon className="w-3.5 h-3.5 text-slate-400 group-hover:text-[#0076FF] dark:group-hover:text-[#00D4FF] shrink-0" />
                    <span className="text-[11px] font-medium truncate">{act.label}</span>
                  </div>
                  <ChevronRight className="w-3 h-3 text-slate-400 opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
                </button>
              );
            })}
          </div>
        </div>

        <div className="border-t border-slate-200/60 dark:border-white/[0.06] my-2" />

        {/* MESSAGES */}
        {messages.map((m) => (
          <div
            key={m.id}
            className={`flex flex-col ${m.sender === "user" ? "items-end" : "items-start"} space-y-1 animate-in fade-in duration-200`}
          >
            <div
              className={`max-w-[90%] p-3 rounded-2xl ${
                m.sender === "user"
                  ? "bg-gradient-to-r from-[#0076FF] to-[#005bd3] text-white rounded-br-xs shadow-xs"
                  : "bg-slate-100 dark:bg-[#111D3D] text-slate-800 dark:text-[#F4F7FB] border border-slate-200/60 dark:border-white/[0.06] rounded-bl-xs"
              }`}
            >
              <p className="whitespace-pre-line leading-relaxed text-[11px]">{m.content}</p>

              {/* SPECIAL ACTION BADGES */}
              {m.action === "appointment_created" && (
                <div className="mt-2.5 p-2 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-700 dark:text-emerald-400 flex items-center gap-2">
                  <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                  <span className="text-[10px] font-bold">Calendrier CRM & Google mis à jour</span>
                </div>
              )}
              {m.status === "conflict" && (
                <div className="mt-2.5 p-2 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-700 dark:text-amber-400 flex items-center gap-2">
                  <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                  <span className="text-[10px] font-bold">Conflit détecté • Création annulée</span>
                </div>
              )}
            </div>
            <span className="text-[9px] text-slate-400 px-1">{m.timestamp}</span>
          </div>
        ))}

        {isThinking && (
          <div className="flex items-center gap-2 text-slate-400 dark:text-slate-500 p-2 text-[11px] animate-pulse">
            <RefreshCw className="w-3.5 h-3.5 animate-spin text-[#0076FF]" />
            <span>Vérification des disponibilités & exécution...</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* INPUT AREA */}
      <div className="p-3 border-t border-slate-200/80 dark:border-white/[0.08] bg-slate-50/40 dark:bg-white/[0.02] rounded-b-2xl">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSendMessage();
          }}
          className="relative flex items-center"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Posez-moi une question ou donnez une commande..."
            disabled={isThinking}
            className="w-full pl-3 pr-10 py-2.5 text-xs rounded-xl bg-white dark:bg-[#111D3D] border border-slate-200 dark:border-white/[0.08] text-slate-900 dark:text-white placeholder-slate-400 focus:outline-hidden focus:ring-2 focus:ring-[#0076FF] transition"
          />
          <button
            type="submit"
            disabled={!input.trim() || isThinking}
            className="absolute right-1.5 p-1.5 rounded-lg bg-gradient-to-r from-[#0076FF] to-[#00D4FF] text-white disabled:opacity-40 hover:opacity-90 transition shadow-xs"
            title="Envoyer la commande"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        </form>
        <div className="mt-1.5 text-center text-[9px] text-slate-400 dark:text-slate-500">
          Connecté aux 11 outils CRM Avenqo & Google Calendar
        </div>
      </div>
    </aside>
  );
}
