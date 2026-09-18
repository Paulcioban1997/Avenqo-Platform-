"use client";

import React, { useState, useMemo } from "react";
import {
  Calendar as CalendarIcon,
  ChevronLeft,
  ChevronRight,
  Clock,
  User,
  Wrench,
  Search,
  Filter,
  CheckCircle2,
  AlertCircle,
  XCircle,
  MoreHorizontal,
  CalendarDays,
  List,
  Columns3,
  CalendarRange,
} from "lucide-react";
import type { AppTranslations } from "@/lib/i18n/app-dictionary";
import type { AppointmentItem } from "./appointment-details-drawer";

export type CalendarMode = "month" | "week" | "day" | "agenda" | "list" | "kanban";

interface CRMCalendarViewProps {
  appointments: AppointmentItem[];
  services: { id: string; name: string }[];
  employees: { id: string; first_name: string; last_name: string; color_code?: string | null }[];
  currentDate: Date;
  onDateChange: (date: Date) => void;
  onSelectAppointment: (appointment: AppointmentItem) => void;
  onNewAppointmentClick: () => void;
  isLoading?: boolean;
  t: AppTranslations;
}

export function CRMCalendarView({
  appointments,
  services,
  employees,
  currentDate,
  onDateChange,
  onSelectAppointment,
  onNewAppointmentClick,
  isLoading = false,
  t,
}: CRMCalendarViewProps) {
  const [viewMode, setViewMode] = useState<CalendarMode>("week");
  const [selectedServiceId, setSelectedServiceId] = useState<string>("all");
  const [selectedEmployeeId, setSelectedEmployeeId] = useState<string>("all");
  const [selectedStatus, setSelectedStatus] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Filter appointments
  const filteredAppointments = useMemo(() => {
    return appointments.filter((app) => {
      if (selectedServiceId !== "all" && app.service_id !== selectedServiceId) return false;
      if (selectedEmployeeId !== "all" && app.employee_id !== selectedEmployeeId) return false;
      if (selectedStatus !== "all" && app.status !== selectedStatus) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const clientMatch = app.client_name?.toLowerCase().includes(q);
        const titleMatch = app.title?.toLowerCase().includes(q);
        const serviceMatch = app.service_name?.toLowerCase().includes(q);
        const empMatch = app.employee_name?.toLowerCase().includes(q);
        if (!clientMatch && !titleMatch && !serviceMatch && !empMatch) return false;
      }
      return true;
    });
  }, [appointments, selectedServiceId, selectedEmployeeId, selectedStatus, searchQuery]);

  // Date Nav Helpers
  const handlePrev = () => {
    const next = new Date(currentDate);
    if (viewMode === "month") next.setMonth(next.getMonth() - 1);
    else if (viewMode === "week") next.setDate(next.getDate() - 7);
    else if (viewMode === "day") next.setDate(next.getDate() - 1);
    else next.setDate(next.getDate() - 7);
    onDateChange(next);
  };

  const handleNext = () => {
    const next = new Date(currentDate);
    if (viewMode === "month") next.setMonth(next.getMonth() + 1);
    else if (viewMode === "week") next.setDate(next.getDate() + 7);
    else if (viewMode === "day") next.setDate(next.getDate() + 1);
    else next.setDate(next.getDate() + 7);
    onDateChange(next);
  };

  const handleToday = () => {
    onDateChange(new Date());
  };

  const formattedHeaderDate = useMemo(() => {
    const locale = "fr-CA";
    if (viewMode === "month") {
      return currentDate.toLocaleDateString(locale, { month: "long", year: "numeric" });
    }
    if (viewMode === "day") {
      return currentDate.toLocaleDateString(locale, {
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric",
      });
    }
    // Week or other
    const startOfWeek = new Date(currentDate);
    const dayOfWeek = (startOfWeek.getDay() + 6) % 7; // Monday = 0
    startOfWeek.setDate(startOfWeek.getDate() - dayOfWeek);
    const endOfWeek = new Date(startOfWeek);
    endOfWeek.setDate(endOfWeek.getDate() + 6);

    return `${startOfWeek.toLocaleDateString(locale, { day: "numeric", month: "short" })} - ${endOfWeek.toLocaleDateString(locale, { day: "numeric", month: "short", year: "numeric" })}`;
  }, [currentDate, viewMode]);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "confirmed":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            {t.crm.status.confirmed}
          </span>
        );
      case "pending":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
            {t.crm.status.pending}
          </span>
        );
      case "completed":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-blue-100 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
            {t.crm.status.completed}
          </span>
        );
      case "cancelled":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-rose-100 dark:bg-rose-950/60 text-rose-700 dark:text-rose-300">
            <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
            {t.crm.status.cancelled}
          </span>
        );
      case "no_show":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
            <span className="w-1.5 h-1.5 rounded-full bg-slate-500" />
            {t.crm.status.noShow}
          </span>
        );
      default:
        return null;
    }
  };

  // Week days calculation
  const weekDays = useMemo(() => {
    const days = [];
    const startOfWeek = new Date(currentDate);
    const dayOfWeek = (startOfWeek.getDay() + 6) % 7;
    startOfWeek.setDate(startOfWeek.getDate() - dayOfWeek);

    for (let i = 0; i < 7; i++) {
      const d = new Date(startOfWeek);
      d.setDate(d.getDate() + i);
      days.push(d);
    }
    return days;
  }, [currentDate]);

  return (
    <div className="flex flex-col bg-white dark:bg-[#0B0F19] rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
      {/* Top Toolbar: Navigation & View Selectors */}
      <div className="p-4 border-b border-slate-200 dark:border-slate-800 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        {/* Left: Prev, Today, Next & Date display */}
        <div className="flex items-center gap-2">
          <div className="flex items-center bg-slate-100 dark:bg-slate-800 rounded-xl p-0.5">
            <button
              onClick={handlePrev}
              className="p-1.5 rounded-lg hover:bg-white dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 transition"
              title="Précédent"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={handleToday}
              className="px-2.5 py-1 text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-white dark:hover:bg-slate-700 rounded-lg transition"
            >
              {t.crm.calendar.today}
            </button>
            <button
              onClick={handleNext}
              className="p-1.5 rounded-lg hover:bg-white dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 transition"
              title="Suivant"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          <h3 className="text-sm md:text-base font-bold text-slate-900 dark:text-white capitalize ml-2">
            {formattedHeaderDate}
          </h3>
        </div>

        {/* View Mode Buttons */}
        <div className="flex items-center gap-1 bg-slate-100 dark:bg-slate-800/80 p-1 rounded-xl overflow-x-auto">
          {[
            { id: "day", label: t.crm.calendar.day, icon: CalendarIcon },
            { id: "week", label: t.crm.calendar.week, icon: CalendarDays },
            { id: "month", label: t.crm.calendar.month, icon: CalendarRange },
            { id: "agenda", label: t.crm.calendar.agenda, icon: Clock },
            { id: "kanban", label: t.crm.calendar.kanban, icon: Columns3 },
            { id: "list", label: t.crm.calendar.list, icon: List },
          ].map((mode) => {
            const Icon = mode.icon;
            const active = viewMode === mode.id;
            return (
              <button
                key={mode.id}
                onClick={() => setViewMode(mode.id as CalendarMode)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                  active
                    ? "bg-white dark:bg-slate-700 text-[#0076FF] dark:text-[#00D4FF] shadow-sm"
                    : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">{mode.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Secondary Filter Bar */}
      <div className="px-4 py-3 bg-slate-50 dark:bg-slate-900/40 border-b border-slate-200 dark:border-slate-800 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Service filter */}
          <select
            value={selectedServiceId}
            onChange={(e) => setSelectedServiceId(e.target.value)}
            className="text-xs px-2.5 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 focus:outline-none focus:border-[#0076FF]"
          >
            <option value="all">Tous les services</option>
            {services.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>

          {/* Employee filter */}
          <select
            value={selectedEmployeeId}
            onChange={(e) => setSelectedEmployeeId(e.target.value)}
            className="text-xs px-2.5 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 focus:outline-none focus:border-[#0076FF]"
          >
            <option value="all">Tous les employés</option>
            {employees.map((emp) => (
              <option key={emp.id} value={emp.id}>
                {emp.first_name} {emp.last_name}
              </option>
            ))}
          </select>

          {/* Status filter */}
          <select
            value={selectedStatus}
            onChange={(e) => setSelectedStatus(e.target.value)}
            className="text-xs px-2.5 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 focus:outline-none focus:border-[#0076FF]"
          >
            <option value="all">Tous les statuts</option>
            <option value="confirmed">{t.crm.status.confirmed}</option>
            <option value="pending">{t.crm.status.pending}</option>
            <option value="completed">{t.crm.status.completed}</option>
            <option value="cancelled">{t.crm.status.cancelled}</option>
            <option value="no_show">{t.crm.status.noShow}</option>
          </select>
        </div>

        {/* Client Search */}
        <div className="relative min-w-[200px] flex-1 sm:flex-initial">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Filtrer client, service, titre..."
            className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:border-[#0076FF]"
          />
        </div>
      </div>

      {/* Main Calendar View Area */}
      <div className="flex-1 overflow-x-auto min-h-[550px] relative">
        {isLoading && (
          <div className="absolute inset-0 z-20 bg-white/60 dark:bg-black/60 backdrop-blur-[1px] flex items-center justify-center">
            <div className="flex items-center gap-2.5 px-4 py-2 rounded-xl bg-white dark:bg-slate-800 shadow-md border border-slate-200 dark:border-slate-700">
              <div className="w-4 h-4 border-2 border-[#0076FF] border-t-transparent rounded-full animate-spin" />
              <span className="text-xs font-medium text-slate-700 dark:text-slate-300">
                Chargement des rendez-vous...
              </span>
            </div>
          </div>
        )}

        {/* --- WEEK VIEW (Default) --- */}
        {viewMode === "week" && (
          <div className="grid grid-cols-7 min-w-[800px] divide-x divide-slate-200 dark:divide-slate-800">
            {weekDays.map((day, idx) => {
              const dayStr = day.toISOString().split("T")[0];
              const isToday = new Date().toISOString().split("T")[0] === dayStr;

              const dayApps = filteredAppointments.filter((app) => {
                const appDateStr = new Date(app.start_time).toISOString().split("T")[0];
                return appDateStr === dayStr;
              });

              return (
                <div key={idx} className="flex flex-col min-h-[500px]">
                  {/* Day Column Header */}
                  <div
                    className={`p-2.5 text-center border-b border-slate-200 dark:border-slate-800 ${
                      isToday ? "bg-blue-50/50 dark:bg-blue-950/20" : ""
                    }`}
                  >
                    <span className="text-[11px] font-semibold text-slate-500 uppercase">
                      {day.toLocaleDateString("fr-CA", { weekday: "short" })}
                    </span>
                    <div
                      className={`w-7 h-7 mx-auto mt-0.5 rounded-full flex items-center justify-center text-xs font-bold ${
                        isToday
                          ? "bg-gradient-to-r from-[#0076FF] to-[#00D4FF] text-white shadow-sm"
                          : "text-slate-800 dark:text-slate-200"
                      }`}
                    >
                      {day.getDate()}
                    </div>
                  </div>

                  {/* Appointments Container */}
                  <div className="flex-1 p-2 space-y-2 bg-slate-50/30 dark:bg-slate-900/10">
                    {dayApps.length === 0 ? (
                      <div className="h-full flex items-center justify-center py-8">
                        <span className="text-[11px] text-slate-400 italic">Aucun RDV</span>
                      </div>
                    ) : (
                      dayApps.map((app) => {
                        const start = new Date(app.start_time);
                        const timeStr = `${String(start.getHours()).padStart(2, "0")}:${String(start.getMinutes()).padStart(2, "0")}`;
                        return (
                          <div
                            key={app.id}
                            onClick={() => onSelectAppointment(app)}
                            className="p-2.5 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm hover:shadow-md hover:border-[#0076FF] cursor-pointer transition text-left group"
                          >
                            <div className="flex items-center justify-between gap-1 mb-1">
                              <span className="text-[10px] font-bold text-[#0076FF] flex items-center gap-1">
                                <Clock className="w-3 h-3" />
                                {timeStr}
                              </span>
                              {getStatusBadge(app.status)}
                            </div>
                            <h4 className="text-xs font-bold text-slate-900 dark:text-white line-clamp-1 group-hover:text-[#0076FF] transition">
                              {app.client_name}
                            </h4>
                            <p className="text-[11px] text-slate-500 dark:text-slate-400 line-clamp-1">
                              {app.service_name || app.title}
                            </p>
                            {app.employee_name && (
                              <div className="mt-1.5 pt-1.5 border-t border-slate-100 dark:border-slate-700/60 flex items-center gap-1 text-[10px] text-slate-500">
                                <User className="w-3 h-3 text-slate-400" />
                                <span className="truncate">{app.employee_name}</span>
                              </div>
                            )}
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* --- DAY VIEW --- */}
        {viewMode === "day" && (
          <div className="p-4 max-w-4xl mx-auto space-y-3">
            {filteredAppointments.filter((app) => {
              const targetStr = currentDate.toISOString().split("T")[0];
              const appStr = new Date(app.start_time).toISOString().split("T")[0];
              return appStr === targetStr;
            }).length === 0 ? (
              <div className="text-center py-16">
                <CalendarIcon className="w-10 h-10 mx-auto text-slate-300 dark:text-slate-600 mb-2" />
                <p className="text-sm text-slate-500">Aucun rendez-vous pour cette journée.</p>
                <button
                  onClick={onNewAppointmentClick}
                  className="mt-3 px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-[#0076FF] text-white hover:bg-blue-600 transition"
                >
                  {t.crm.header.newAppointment}
                </button>
              </div>
            ) : (
              filteredAppointments
                .filter((app) => {
                  const targetStr = currentDate.toISOString().split("T")[0];
                  const appStr = new Date(app.start_time).toISOString().split("T")[0];
                  return appStr === targetStr;
                })
                .sort((a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime())
                .map((app) => {
                  const s = new Date(app.start_time);
                  const e = new Date(app.end_time);
                  const sStr = `${String(s.getHours()).padStart(2, "0")}:${String(s.getMinutes()).padStart(2, "0")}`;
                  const eStr = `${String(e.getHours()).padStart(2, "0")}:${String(e.getMinutes()).padStart(2, "0")}`;
                  return (
                    <div
                      key={app.id}
                      onClick={() => onSelectAppointment(app)}
                      className="p-4 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm hover:shadow-md hover:border-[#0076FF] cursor-pointer transition flex items-center justify-between gap-4"
                    >
                      <div className="flex items-center gap-4">
                        <div className="text-center min-w-[70px] pr-4 border-r border-slate-200 dark:border-slate-700">
                          <span className="text-sm font-bold text-slate-900 dark:text-white block">
                            {sStr}
                          </span>
                          <span className="text-[11px] text-slate-400 block">{eStr}</span>
                        </div>
                        <div>
                          <div className="flex items-center gap-2 mb-1">
                            <h4 className="text-sm font-bold text-slate-900 dark:text-white">
                              {app.client_name}
                            </h4>
                            {getStatusBadge(app.status)}
                          </div>
                          <p className="text-xs text-slate-500 dark:text-slate-400">
                            {app.service_name || app.title} • {app.duration_minutes} min
                          </p>
                        </div>
                      </div>

                      <div className="text-right">
                        <span className="text-sm font-bold text-emerald-600 dark:text-emerald-400 block">
                          {app.price} $
                        </span>
                        {app.employee_name && (
                          <span className="text-xs text-slate-400">{app.employee_name}</span>
                        )}
                      </div>
                    </div>
                  );
                })
            )}
          </div>
        )}

        {/* --- MONTH VIEW --- */}
        {viewMode === "month" && (
          <div className="p-4 text-center">
            <div className="grid grid-cols-7 gap-1 min-w-[700px]">
              {["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"].map((d) => (
                <div key={d} className="p-2 text-xs font-semibold text-slate-500 uppercase">
                  {d}
                </div>
              ))}
              {Array.from({ length: 35 }).map((_, i) => {
                const firstDayOfMonth = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1);
                const offset = (firstDayOfMonth.getDay() + 6) % 7;
                const dayDate = new Date(currentDate.getFullYear(), currentDate.getMonth(), i - offset + 1);
                const isCurrentMonth = dayDate.getMonth() === currentDate.getMonth();
                const dayStr = dayDate.toISOString().split("T")[0];
                const dayApps = filteredAppointments.filter(
                  (a) => new Date(a.start_time).toISOString().split("T")[0] === dayStr
                );

                return (
                  <div
                    key={i}
                    onClick={() => {
                      onDateChange(dayDate);
                      setViewMode("day");
                    }}
                    className={`min-h-[85px] p-2 rounded-xl border transition text-left cursor-pointer ${
                      isCurrentMonth
                        ? "bg-white dark:bg-slate-800/60 border-slate-200 dark:border-slate-800 hover:border-[#0076FF]"
                        : "bg-slate-50/50 dark:bg-slate-900/30 border-transparent opacity-40"
                    }`}
                  >
                    <span className="text-xs font-bold text-slate-700 dark:text-slate-300 block">
                      {dayDate.getDate()}
                    </span>
                    <div className="mt-1 space-y-1">
                      {dayApps.slice(0, 2).map((a) => (
                        <div
                          key={a.id}
                          className="text-[10px] px-1.5 py-0.5 rounded bg-blue-50 dark:bg-blue-950/60 text-[#0076FF] truncate font-medium"
                        >
                          {a.client_name}
                        </div>
                      ))}
                      {dayApps.length > 2 && (
                        <span className="text-[9px] text-slate-400 block">
                          +{dayApps.length - 2} autre(s)
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* --- KANBAN VIEW (By Status) --- */}
        {viewMode === "kanban" && (
          <div className="p-4 grid grid-cols-1 md:grid-cols-4 gap-4 min-w-[800px]">
            {[
              { status: "pending", title: t.crm.status.pending, color: "border-amber-400" },
              { status: "confirmed", title: t.crm.status.confirmed, color: "border-emerald-400" },
              { status: "completed", title: t.crm.status.completed, color: "border-blue-400" },
              { status: "cancelled", title: t.crm.status.cancelled, color: "border-rose-400" },
            ].map((col) => {
              const colApps = filteredAppointments.filter((a) => a.status === col.status);
              return (
                <div
                  key={col.status}
                  className="flex flex-col bg-slate-50 dark:bg-slate-900/50 rounded-xl p-3 border border-slate-200 dark:border-slate-800"
                >
                  <div className={`pb-2 mb-3 border-b-2 ${col.color} flex items-center justify-between`}>
                    <span className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider">
                      {col.title}
                    </span>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300 font-semibold">
                      {colApps.length}
                    </span>
                  </div>

                  <div className="flex-1 space-y-2.5 overflow-y-auto max-h-[600px]">
                    {colApps.map((app) => (
                      <div
                        key={app.id}
                        onClick={() => onSelectAppointment(app)}
                        className="p-3 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm hover:shadow-md hover:border-[#0076FF] cursor-pointer transition"
                      >
                        <div className="flex items-center justify-between text-[10px] text-slate-400 mb-1">
                          <span>{new Date(app.start_time).toLocaleDateString("fr-CA")}</span>
                          <span>{new Date(app.start_time).toLocaleTimeString("fr-CA", { hour: "2-digit", minute: "2-digit" })}</span>
                        </div>
                        <h4 className="text-xs font-bold text-slate-900 dark:text-white mb-0.5">
                          {app.client_name}
                        </h4>
                        <p className="text-[11px] text-slate-500 dark:text-slate-400 line-clamp-1">
                          {app.service_name || app.title}
                        </p>
                        <div className="mt-2 pt-2 border-t border-slate-100 dark:border-slate-700/60 flex items-center justify-between text-[10px]">
                          <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                            {app.price} $
                          </span>
                          <span className="text-slate-400">{app.employee_name || "Non assigné"}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* --- LIST & AGENDA VIEW --- */}
        {(viewMode === "list" || viewMode === "agenda") && (
          <div className="p-4">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                    <th className="py-3 px-4 font-semibold">Date & Heure</th>
                    <th className="py-3 px-4 font-semibold">Client</th>
                    <th className="py-3 px-4 font-semibold">Service / Objet</th>
                    <th className="py-3 px-4 font-semibold">Employé</th>
                    <th className="py-3 px-4 font-semibold">Statut</th>
                    <th className="py-3 px-4 font-semibold text-right">Tarif</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {filteredAppointments.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-8 text-center text-slate-400 italic">
                        Aucun rendez-vous ne correspond aux critères sélectionnés.
                      </td>
                    </tr>
                  ) : (
                    filteredAppointments.map((app) => (
                      <tr
                        key={app.id}
                        onClick={() => onSelectAppointment(app)}
                        className="hover:bg-slate-50 dark:hover:bg-slate-800/60 cursor-pointer transition"
                      >
                        <td className="py-3.5 px-4 font-medium text-slate-900 dark:text-white">
                          <div>{new Date(app.start_time).toLocaleDateString("fr-CA")}</div>
                          <div className="text-[11px] text-slate-400">
                            {new Date(app.start_time).toLocaleTimeString("fr-CA", { hour: "2-digit", minute: "2-digit" })}
                          </div>
                        </td>
                        <td className="py-3.5 px-4 font-bold text-slate-900 dark:text-white">
                          {app.client_name}
                        </td>
                        <td className="py-3.5 px-4 text-slate-600 dark:text-slate-300">
                          {app.service_name || app.title}
                        </td>
                        <td className="py-3.5 px-4 text-slate-500">
                          {app.employee_name || "—"}
                        </td>
                        <td className="py-3.5 px-4">{getStatusBadge(app.status)}</td>
                        <td className="py-3.5 px-4 text-right font-bold text-emerald-600 dark:text-emerald-400">
                          {app.price} $
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
