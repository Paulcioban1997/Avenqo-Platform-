"use client";

import React, { useState, useEffect, useCallback } from "react";
import Image from "next/image";
import {
  Calendar as CalendarIcon,
  Users,
  Plus,
  Zap,
  TrendingUp,
  Settings,
  RefreshCw,
  Clock,
  Building,
  CalendarCheck,
  ChevronRight,
  LayoutDashboard,
  Megaphone,
  BarChart3,
  Bot,
  Sparkles,
} from "lucide-react";
import type { AppTranslations } from "@/lib/i18n/app-dictionary";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
import { getAuthHeaders } from "@/lib/api-headers";
import { CRMKpiCards, type CRMKpis } from "./crm-kpi-cards";
import { CRMCalendarView } from "./crm-calendar-view";
import { CRMClientsView } from "./crm-clients-view";
import { CRMPipelinesView } from "./crm-pipelines-view";
import { CRMAutomationsView } from "./crm-automations-view";
import { CRMCalendarConnectionCard } from "./crm-calendar-connection-card";
import { CRMCampaignsView } from "./crm-campaigns-view";
import { CRMReportsView } from "./crm-reports-view";
import { CRMCopilotPanel } from "./crm-copilot-panel";
import { AppointmentDetailsDrawer, type AppointmentItem } from "./appointment-details-drawer";
import { NewAppointmentModal } from "./new-appointment-modal";

export type CRMSubTab =
  | "overview"
  | "clients"
  | "appointments"
  | "pipelines"
  | "automations"
  | "campaigns"
  | "reports"
  | "connections";

interface CRMViewProps {
  t?: AppTranslations;
  activeSubTab?: CRMSubTab;
}

export function CRMView({ t: propT, activeSubTab = "overview" }: CRMViewProps) {
  const { locale } = useLocale();
  const t = propT || getAppTranslations(locale);
  const [currentTab, setCurrentTab] = useState<CRMSubTab>(activeSubTab);
  const [currentDate, setCurrentDate] = useState<Date>(new Date());
  const [kpis, setKpis] = useState<CRMKpis>({
    active_clients: 0,
    appointments_this_month: 0,
    attendance_rate_percent: 0,
    total_revenue_generated: 0,
    currency: "CAD",
  });
  const [appointments, setAppointments] = useState<AppointmentItem[]>([]);
  const [services, setServices] = useState<{ id: string; name: string }[]>([]);
  const [employees, setEmployees] = useState<
    { id: string; first_name: string; last_name: string; color_code?: string | null }[]
  >([]);

  const [isLoading, setIsLoading] = useState(false);
  const [companyName, setCompanyName] = useState<string>("");
  const [isMobileCopilotOpen, setIsMobileCopilotOpen] = useState(false);

  // Drawers and Modals
  const [selectedAppointment, setSelectedAppointment] = useState<AppointmentItem | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [appointmentToEdit, setAppointmentToEdit] = useState<AppointmentItem | null>(null);

  // Load CRM data from backend
  const loadCRMData = useCallback(async () => {
    setIsLoading(true);
    try {
      const headers = getAuthHeaders();

      const [kpiRes, appRes, srvRes, empRes, sumRes] = await Promise.all([
        fetch("/api/v1/crm/kpis", { headers }),
        fetch("/api/v1/crm/appointments?limit=250", { headers }),
        fetch("/api/v1/crm/services", { headers }),
        fetch("/api/v1/crm/employees", { headers }),
        fetch("/api/v1/crm/summary", { headers }),
      ]);

      if (kpiRes.ok) {
        const kData = await kpiRes.json();
        setKpis(kData);
      }
      if (appRes.ok) {
        const aData = await appRes.json();
        setAppointments(aData || []);
      }
      if (srvRes.ok) {
        const sData = await srvRes.json();
        setServices(sData || []);
      }
      if (empRes.ok) {
        const eData = await empRes.json();
        setEmployees(eData || []);
      }
      if (sumRes.ok) {
        const sumData = await sumRes.json();
        if (sumData.company_name) {
          setCompanyName(sumData.company_name);
        }
      }
    } catch {
      // Keep real zeroes
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCRMData();
  }, [loadCRMData]);

  // Listen for global entity select from search palette (Ctrl+K)
  useEffect(() => {
    function handleSelectEntity(e: CustomEvent) {
      const detail = e.detail;
      if (!detail) return;
      if (detail.type === "appointment" && detail.id) {
        const matched = appointments.find((a) => a.id === detail.id);
        if (matched) {
          setSelectedAppointment(matched);
          setIsDrawerOpen(true);
        }
      } else if (detail.type === "client") {
        setCurrentTab("clients");
      } else if (detail.type === "opportunity") {
        setCurrentTab("pipelines");
      }
    }
    window.addEventListener("crm:select-entity" as any, handleSelectEntity);
    return () => window.removeEventListener("crm:select-entity" as any, handleSelectEntity);
  }, [appointments]);

  // Appointment Drawer Actions
  const handleSelectAppointment = (app: AppointmentItem) => {
    setSelectedAppointment(app);
    setIsDrawerOpen(true);
  };

  const handleStatusChange = async (id: string, newStatus: string) => {
    await fetch(`/api/v1/crm/appointments/${id}/status`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
      },
      body: JSON.stringify({ status: newStatus }),
    });
    // Refresh without full page reload
    loadCRMData();
    if (selectedAppointment && selectedAppointment.id === id) {
      setSelectedAppointment({
        ...selectedAppointment,
        status: newStatus as any,
      });
    }
  };

  const handleRescheduleClick = (appointment: AppointmentItem) => {
    setIsDrawerOpen(false);
    setAppointmentToEdit(appointment);
    setIsModalOpen(true);
  };

  const handleNewAppointmentClick = () => {
    setAppointmentToEdit(null);
    setIsModalOpen(true);
  };

  const formattedCurrentDate = new Date().toLocaleDateString(locale === "fr" ? "fr-CA" : "en-US", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  const navTabs = [
    { id: "overview", label: t.crm.tabs.overview || "Aperçu", icon: LayoutDashboard },
    { id: "clients", label: t.crm.tabs.clients || "Clients", icon: Users },
    { id: "appointments", label: t.crm.tabs.appointments || "Rendez-vous", icon: CalendarIcon },
    { id: "pipelines", label: t.crm.tabs.pipelines || "Pipelines & Deals", icon: TrendingUp },
    { id: "automations", label: t.crm.tabs.automations || "Automatisations", icon: Zap },
    { id: "campaigns", label: t.crm.tabs.campaigns || "Campagnes", icon: Megaphone },
    { id: "reports", label: t.crm.tabs.reports || "Rapports", icon: BarChart3 },
    { id: "connections", label: t.crm.tabs.connections || "Connexions", icon: Settings },
  ];

  return (
    <div className="flex gap-6 items-start animate-in fade-in duration-300">
      {/* LEFT / CENTER: MAIN CRM WORKSPACE */}
      <div className="flex-1 min-w-0 space-y-6">
        {/* CRM HEADER */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-white dark:bg-[#0B132B] p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-xs">
          <div className="flex items-center gap-3.5">
            <Image
              src="/brand/avenqo-icon.png"
              alt="Avenqo CRM AI"
              width={42}
              height={42}
              className="rounded-xl object-contain shadow-sm shadow-blue-500/20 shrink-0"
            />
            <div className="space-y-1">
              <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                <Building className="w-3.5 h-3.5 text-[#0076FF]" />
                <span className="font-bold text-slate-700 dark:text-slate-200">{companyName || "Avenqo"}</span>
                <span>•</span>
                <span className="capitalize">{formattedCurrentDate}</span>
              </div>
              <h1 className="text-xl font-extrabold text-slate-900 dark:text-white tracking-tight">
                {t.crm.title || "CRM AI & Planification Intelligente"}
              </h1>
            </div>
          </div>

          <div className="flex items-center gap-2.5 w-full sm:w-auto">
            <button
              onClick={() => loadCRMData()}
              className="p-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 transition"
              title="Rafraîchir les données"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
            </button>

            {/* Mobile Copilot Trigger */}
            <button
              onClick={() => setIsMobileCopilotOpen(true)}
              className="lg:hidden p-2.5 rounded-xl border border-blue-200 dark:border-blue-900 bg-blue-50 dark:bg-blue-950/50 text-[#0076FF] dark:text-[#00D4FF] hover:bg-blue-100 transition"
              title="Ouvrir Avenqo Copilot"
            >
              <Sparkles className="w-4 h-4" />
            </button>

            <button
              onClick={handleNewAppointmentClick}
              className="flex-1 sm:flex-initial px-5 py-2.5 text-xs font-bold rounded-xl bg-gradient-to-r from-[#0076FF] to-[#00D4FF] text-white shadow-md hover:shadow-lg hover:opacity-95 transition flex items-center justify-center gap-2"
            >
              <Plus className="w-4 h-4" />
              <span>{t.crm.header.newAppointment}</span>
            </button>
          </div>
        </div>

        {/* CRM SUB-NAVIGATION TABS (Item 4) */}
        <div className="flex items-center gap-1.5 border-b border-slate-200 dark:border-slate-800 pb-2 overflow-x-auto scrollbar-none">
          {navTabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = currentTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setCurrentTab(tab.id as CRMSubTab)}
                className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold whitespace-nowrap transition ${
                  isActive
                    ? "bg-[#0076FF]/10 text-[#0076FF] dark:text-[#00D4FF] dark:bg-blue-950/50 border border-blue-200/50 dark:border-blue-800/40"
                    : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800/60"
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* REAL DATA KPI CARDS (Item 6) */}
        <CRMKpiCards kpis={kpis} t={t} isLoading={isLoading} />

        {/* MAIN VIEW SECTIONS */}
        {currentTab === "overview" && (
          <div className="space-y-6">
            <CRMCalendarView
              appointments={appointments}
              services={services}
              employees={employees}
              currentDate={currentDate}
              onDateChange={setCurrentDate}
              onSelectAppointment={handleSelectAppointment}
              onNewAppointmentClick={handleNewAppointmentClick}
              isLoading={isLoading}
              t={t}
            />
          </div>
        )}

        {currentTab === "appointments" && (
          <CRMCalendarView
            appointments={appointments}
            services={services}
            employees={employees}
            currentDate={currentDate}
            onDateChange={setCurrentDate}
            onSelectAppointment={handleSelectAppointment}
            onNewAppointmentClick={handleNewAppointmentClick}
            isLoading={isLoading}
            t={t}
          />
        )}

        {currentTab === "clients" && <CRMClientsView t={t} />}

        {currentTab === "pipelines" && <CRMPipelinesView t={t} />}

        {currentTab === "automations" && <CRMAutomationsView t={t} />}

        {currentTab === "campaigns" && <CRMCampaignsView t={t} />}

        {currentTab === "reports" && <CRMReportsView t={t} />}

        {currentTab === "connections" && <CRMCalendarConnectionCard t={t} />}
      </div>

      {/* RIGHT: PERMANENT AVENQO COPILOT PANEL (Item 10, 11, 12) */}
      <div className="hidden lg:block shrink-0">
        <CRMCopilotPanel
          t={t}
          userName={companyName}
          onAppointmentCreated={() => {
            loadCRMData();
          }}
        />
      </div>

      {/* MOBILE / TABLET FLOATING COPILOT DRAWER */}
      {isMobileCopilotOpen && (
        <CRMCopilotPanel
          t={t}
          userName={companyName}
          isFloating={true}
          onClose={() => setIsMobileCopilotOpen(false)}
          onAppointmentCreated={() => {
            loadCRMData();
          }}
        />
      )}

      {/* SLIDE-OVER APPOINTMENT DETAILS DRAWER */}
      <AppointmentDetailsDrawer
        appointment={selectedAppointment}
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        onStatusChange={handleStatusChange}
        onRescheduleClick={handleRescheduleClick}
        t={t}
      />

      {/* NEW / RESCHEDULE APPOINTMENT MODAL */}
      <NewAppointmentModal
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          setAppointmentToEdit(null);
        }}
        onSuccess={() => {
          loadCRMData();
        }}
        initialAppointment={appointmentToEdit}
        t={t}
      />
    </div>
  );
}
