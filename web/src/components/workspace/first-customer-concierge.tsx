"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  CheckCircle2,
  Clock,
  AlertCircle,
  Sparkles,
  ArrowRight,
  ShieldCheck,
  Calendar,
  PhoneCall,
  FileCheck,
  HelpCircle,
  ExternalLink,
  ChevronRight,
  LifeBuoy,
} from "lucide-react";
import { useLocale } from "@/lib/i18n/locale-context";

interface ActivationMilestone {
  id: string;
  titleFr: string;
  titleEn: string;
  descFr: string;
  descEn: string;
  status: "verified" | "in_progress" | "pending" | "blocked";
  actionHref?: string;
  actionLabelFr?: string;
  actionLabelEn?: string;
}

export function FirstCustomerConcierge() {
  const { locale } = useLocale();
  const isEn = locale === "en";

  const [milestones, setMilestones] = useState<ActivationMilestone[]>([
    {
      id: "workspace_creation",
      titleFr: "Création de votre espace",
      titleEn: "Workspace Creation",
      descFr: "Organisation et compte propriétaire initialisés",
      descEn: "Organization and owner credentials provisioned",
      status: "verified",
    },
    {
      id: "sector_profile",
      titleFr: "Profil sectoriel & modules",
      titleEn: "Sector Profile & Modules",
      descFr: "Allocation exacte des capacités selon votre forfait",
      descEn: "Exact module allocation aligned with subscription plan",
      status: "verified",
    },
    {
      id: "integrations",
      titleFr: "Connexions & Intégrations",
      titleEn: "Connections & Integrations",
      descFr: "Vérifiez vos flux de données (Calendrier, Téléphonie, E-commerce)",
      descEn: "Verify live data streams (Calendar, Voice, E-commerce)",
      status: "in_progress",
      actionHref: "/connections",
      actionLabelFr: "Vérifier les connexions",
      actionLabelEn: "Review Connections",
    },
    {
      id: "agent_testing",
      titleFr: "Test contrôlé en simulation",
      titleEn: "Controlled Simulation Test",
      descFr: "Testez votre agent en environnement de démonstration sans impact réel",
      descEn: "Test agents in simulated mode with zero external impact",
      status: "in_progress",
      actionHref: "/voice",
      actionLabelFr: "Lancer un test vocal",
      actionLabelEn: "Run Voice Test",
    },
    {
      id: "first_value",
      titleFr: "Première valeur métier vérifiée",
      titleEn: "First Verified Business Value",
      descFr: "Premier appel qualifié ou première commande analysée avec succès",
      descEn: "First live call qualified or first dataset insight confirmed",
      status: "pending",
    },
  ]);

  const verifiedCount = milestones.filter((m) => m.status === "verified").length;
  const progressPercent = Math.round((verifiedCount / milestones.length) * 100);

  const nextAction = milestones.find((m) => m.status === "in_progress" || m.status === "pending");

  return (
    <div className="rounded-3xl border border-slate-200/80 bg-white p-6 shadow-sm dark:border-white/[0.08] dark:bg-[#0B132B]">
      {/* Top Banner: Concierge Intro */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200/60 pb-5 dark:border-white/[0.08]">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-tr from-[#0076FF] to-[#7B2CBF] text-white shadow-md shadow-blue-500/20">
            <Sparkles size={20} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-slate-900 dark:text-white">
                {isEn ? "First Customer Concierge" : "Centre d'Accompagnement Client"}
              </h2>
              <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-bold text-[#0076FF] dark:bg-blue-900/30 dark:text-blue-300">
                {isEn ? "VIP Pilot Program" : "Programme Pilote"}
              </span>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {isEn
                ? "Step-by-step progress towards your first verified business value."
                : "Progression guidée étape par étape jusqu'à votre première valeur métier vérifiée."}
            </p>
          </div>
        </div>

        {/* Progress Badge */}
        <div className="flex items-center gap-3 sm:text-right">
          <div>
            <span className="text-xs font-bold text-slate-900 dark:text-white">
              {verifiedCount} / {milestones.length} {isEn ? "completed" : "étapes validées"}
            </span>
            <div className="mt-1 h-2 w-32 overflow-hidden rounded-full bg-slate-100 dark:bg-white/10">
              <div
                className="h-full rounded-full bg-gradient-to-r from-[#0076FF] to-cyan-400 transition-all duration-500"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Recommended Next Action Card */}
      {nextAction && (
        <div className="mt-5 rounded-2xl border border-blue-200/80 bg-blue-50/50 p-4 dark:border-blue-500/20 dark:bg-blue-950/20">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="space-y-1">
              <span className="text-[10px] font-bold uppercase tracking-wider text-[#0076FF] dark:text-cyan-300">
                {isEn ? "Recommended Next Action" : "Prochaine action recommandée"}
              </span>
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                {isEn ? nextAction.titleEn : nextAction.titleFr}
              </h3>
              <p className="text-xs text-slate-600 dark:text-slate-300">
                {isEn ? nextAction.descEn : nextAction.descFr}
              </p>
            </div>

            {nextAction.actionHref && (
              <Link
                href={nextAction.actionHref}
                className="inline-flex shrink-0 items-center gap-1.5 rounded-xl bg-[#0076FF] px-4 py-2 text-xs font-semibold text-white shadow-xs transition hover:bg-blue-600"
              >
                <span>{isEn ? nextAction.actionLabelEn : nextAction.actionLabelFr}</span>
                <ArrowRight size={13} />
              </Link>
            )}
          </div>
        </div>
      )}

      {/* Milestones Stepper Grid */}
      <div className="mt-6 divide-y divide-slate-100 dark:divide-white/[0.06]">
        {milestones.map((m, idx) => {
          const isVerified = m.status === "verified";
          const isInProgress = m.status === "in_progress";
          const isBlocked = m.status === "blocked";

          return (
            <div
              key={m.id}
              className="flex items-center justify-between py-3 text-xs"
            >
              <div className="flex items-center gap-3">
                <div
                  className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold ${
                    isVerified
                      ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                      : isInProgress
                      ? "bg-blue-500/15 text-[#0076FF] dark:text-cyan-300 animate-pulse"
                      : isBlocked
                      ? "bg-red-500/15 text-red-500"
                      : "bg-slate-100 text-slate-400 dark:bg-white/5"
                  }`}
                >
                  {isVerified ? (
                    <CheckCircle2 size={15} />
                  ) : isBlocked ? (
                    <AlertCircle size={15} />
                  ) : (
                    idx + 1
                  )}
                </div>

                <div>
                  <span className="font-semibold text-slate-900 dark:text-white">
                    {isEn ? m.titleEn : m.titleFr}
                  </span>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400">
                    {isEn ? m.descEn : m.descFr}
                  </p>
                </div>
              </div>

              <div>
                <span
                  className={`rounded-full px-2.5 py-0.5 text-[10px] font-semibold ${
                    isVerified
                      ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
                      : isInProgress
                      ? "bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-cyan-300"
                      : isBlocked
                      ? "bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300"
                      : "bg-slate-100 text-slate-500 dark:bg-white/5 dark:text-slate-400"
                  }`}
                >
                  {isVerified
                    ? isEn
                      ? "Verified"
                      : "Vérifié"
                    : isInProgress
                    ? isEn
                      ? "In Progress"
                      : "En cours"
                    : isBlocked
                    ? isEn
                      ? "Action Required"
                      : "Action requise"
                    : isEn
                    ? "Pending"
                    : "En attente"}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Support & Concierge Assistance footer */}
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4 text-xs text-slate-500 dark:border-white/[0.06] dark:text-slate-400">
        <div className="flex items-center gap-1.5">
          <LifeBuoy size={14} className="text-[#0076FF]" />
          <span>
            {isEn
              ? "Need assistance with your setup? Our deployment team is at your service."
              : "Besoin d'aide pour votre mise en route ? Notre équipe d'ingénierie est à votre disposition."}
          </span>
        </div>
        <Link
          href="/contact"
          className="font-medium text-[#0076FF] hover:underline dark:text-cyan-400"
        >
          {isEn ? "Contact Concierge" : "Contacter le Concierge"} ➔
        </Link>
      </div>
    </div>
  );
}
