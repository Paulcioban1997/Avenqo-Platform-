"use client";

import React, { useState } from "react";
import {
  X,
  Calendar,
  Clock,
  User,
  Phone,
  Mail,
  Wrench,
  DollarSign,
  CheckCircle,
  XCircle,
  FileText,
  CalendarSync,
  Car,
  Tag,
  AlertCircle,
} from "lucide-react";
import type { AppTranslations } from "@/lib/i18n/app-dictionary";

export interface AppointmentItem {
  id: string;
  client_id: string;
  client_name: string;
  client_phone?: string | null;
  client_email?: string | null;
  service_id?: string | null;
  service_name?: string | null;
  employee_id?: string | null;
  employee_name?: string | null;
  employee_color?: string | null;
  title: string;
  start_time: string;
  end_time: string;
  duration_minutes: number;
  status: "confirmed" | "pending" | "completed" | "cancelled" | "no_show";
  price: number;
  currency?: string;
  notes?: string | null;
  industry_data?: Record<string, any>;
  calendar_provider?: string | null;
  external_event_id?: string | null;
}

interface AppointmentDetailsDrawerProps {
  appointment: AppointmentItem | null;
  isOpen: boolean;
  onClose: () => void;
  onStatusChange: (id: string, newStatus: string) => Promise<void>;
  onRescheduleClick: (appointment: AppointmentItem) => void;
  t: AppTranslations;
}

export function AppointmentDetailsDrawer({
  appointment,
  isOpen,
  onClose,
  onStatusChange,
  onRescheduleClick,
  t,
}: AppointmentDetailsDrawerProps) {
  const [isUpdating, setIsUpdating] = useState(false);

  if (!isOpen || !appointment) return null;

  const startDt = new Date(appointment.start_time);
  const endDt = new Date(appointment.end_time);

  const statusColors = {
    confirmed: "bg-blue-100 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300 border-blue-200 dark:border-blue-800",
    pending: "bg-amber-100 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300 border-amber-200 dark:border-amber-800",
    completed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800",
    cancelled: "bg-rose-100 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300 border-rose-200 dark:border-rose-800",
    no_show: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border-slate-200 dark:border-slate-700",
  }[appointment.status] || "bg-slate-100 text-slate-700";

  const handleStatus = async (status: string) => {
    setIsUpdating(true);
    try {
      await onStatusChange(appointment.id, status);
    } finally {
      setIsUpdating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      {/* Backdrop */}
      <div
        onClick={onClose}
        className="absolute inset-0 bg-slate-900/40 dark:bg-black/60 backdrop-blur-xs transition-opacity animate-in fade-in"
      />

      {/* Slide-over panel */}
      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-md bg-white dark:bg-[#0B132B] border-l border-slate-200/80 dark:border-white/[0.08] shadow-2xl flex flex-col justify-between animate-in slide-in-from-right duration-200">
          {/* Header */}
          <div className="p-6 border-b border-slate-200/80 dark:border-white/[0.08] flex items-center justify-between">
            <div className="space-y-1">
              <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold border ${statusColors}`}>
                {t.crm.appointmentStatuses[appointment.status as keyof typeof t.crm.appointmentStatuses] || appointment.status}
              </span>
              <h2 className="text-lg font-bold text-slate-900 dark:text-[#F4F7FB] mt-1">
                {appointment.title}
              </h2>
            </div>
            <button
              onClick={onClose}
              className="p-2 rounded-xl text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/[0.06] transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Body Content */}
          <div className="p-6 overflow-y-auto flex-1 space-y-6 text-sm">
            {/* Calendar & Time */}
            <div className="flex items-start gap-3 p-3.5 rounded-xl bg-slate-50 dark:bg-[#111D3D] border border-slate-200/60 dark:border-white/[0.06]">
              <Calendar className="w-4 h-4 text-[#0076FF] mt-0.5" />
              <div>
                <p className="font-semibold text-slate-800 dark:text-slate-200">
                  {startDt.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
                </p>
                <p className="text-xs text-slate-500 dark:text-[#94A3B8] flex items-center gap-1 mt-0.5">
                  <Clock className="w-3.5 h-3.5" />
                  {startDt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} - {endDt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} ({appointment.duration_minutes} min)
                </p>
              </div>
            </div>

            {/* Client Info */}
            <div className="space-y-2">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Client</h3>
              <div className="p-4 rounded-xl border border-slate-200/80 dark:border-white/[0.08] bg-white dark:bg-[#060B13]/40 space-y-2">
                <div className="flex items-center gap-2 text-slate-900 dark:text-[#F4F7FB] font-semibold">
                  <User className="w-4 h-4 text-blue-500" />
                  <span>{appointment.client_name}</span>
                </div>
                {appointment.client_phone && (
                  <div className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-400">
                    <Phone className="w-3.5 h-3.5 text-slate-400" />
                    <span>{appointment.client_phone}</span>
                  </div>
                )}
                {appointment.client_email && (
                  <div className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-400">
                    <Mail className="w-3.5 h-3.5 text-slate-400" />
                    <span>{appointment.client_email}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Service & Employee */}
            <div className="grid grid-cols-2 gap-3">
              <div className="p-3.5 rounded-xl border border-slate-200/80 dark:border-white/[0.08] bg-white dark:bg-[#060B13]/40">
                <span className="text-xs text-slate-400">Prestation</span>
                <p className="font-semibold text-slate-900 dark:text-[#F4F7FB] mt-0.5 truncate">
                  {appointment.service_name || "Service standard"}
                </p>
                <p className="text-xs text-[#0076FF] font-bold mt-1">
                  {appointment.price.toFixed(2)} {appointment.currency || "CAD"}
                </p>
              </div>
              <div className="p-3.5 rounded-xl border border-slate-200/80 dark:border-white/[0.08] bg-white dark:bg-[#060B13]/40">
                <span className="text-xs text-slate-400">Collaborateur</span>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <span
                    className="w-2.5 h-2.5 rounded-full"
                    style={{ backgroundColor: appointment.employee_color || "#00D4FF" }}
                  />
                  <p className="font-semibold text-slate-900 dark:text-[#F4F7FB] truncate">
                    {appointment.employee_name || "Non assigné"}
                  </p>
                </div>
              </div>
            </div>

            {/* Industry Specific (Garage, Clinic, Salon) */}
            {appointment.industry_data && Object.keys(appointment.industry_data).length > 0 && (
              <div className="space-y-2">
                <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                  <Car className="w-3.5 h-3.5 text-blue-500" /> Spécifications Métier
                </h3>
                <div className="p-3.5 rounded-xl border border-slate-200/80 dark:border-white/[0.08] bg-slate-50/50 dark:bg-[#111D3D]/30 space-y-1.5 text-xs">
                  {Object.entries(appointment.industry_data).map(([key, val]) => (
                    <div key={key} className="flex justify-between py-0.5">
                      <span className="text-slate-500 capitalize">{key.replace("_", " ")}:</span>
                      <span className="font-medium text-slate-800 dark:text-slate-200">{String(val)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Notes */}
            {appointment.notes && (
              <div className="space-y-1.5">
                <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                  <FileText className="w-3.5 h-3.5" /> Notes
                </h3>
                <p className="p-3.5 rounded-xl bg-slate-50 dark:bg-[#111D3D] text-xs text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
                  {appointment.notes}
                </p>
              </div>
            )}

            {/* External Calendar Sync Status */}
            <div className="p-3.5 rounded-xl border border-slate-200/80 dark:border-white/[0.08] flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <CalendarSync className="w-4 h-4 text-blue-500" />
                <span className="font-medium text-slate-700 dark:text-slate-300">
                  {appointment.external_event_id ? "Synchronisé Google Calendar" : "Calendrier local"}
                </span>
              </div>
              {appointment.external_event_id && (
                <span className="text-emerald-500 font-semibold flex items-center gap-1">
                  <CheckCircle className="w-3.5 h-3.5" /> Connecté
                </span>
              )}
            </div>
          </div>

          {/* Footer Action Buttons */}
          <div className="p-6 border-t border-slate-200/80 dark:border-white/[0.08] bg-slate-50/50 dark:bg-[#0B132B] space-y-2.5">
            <div className="grid grid-cols-2 gap-2">
              <button
                disabled={isUpdating}
                onClick={() => onRescheduleClick(appointment)}
                className="w-full py-2.5 px-3 rounded-xl border border-slate-200 dark:border-white/[0.12] bg-white dark:bg-[#111D3D] hover:bg-slate-100 dark:hover:bg-[#172652] text-xs font-semibold text-slate-800 dark:text-[#F4F7FB] transition-colors"
              >
                {t.crm.actions.reschedule}
              </button>
              {appointment.status !== "completed" && (
                <button
                  disabled={isUpdating}
                  onClick={() => handleStatus("completed")}
                  className="w-full py-2.5 px-3 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold shadow-xs transition-colors flex items-center justify-center gap-1.5"
                >
                  <CheckCircle className="w-3.5 h-3.5" />
                  {t.crm.actions.markCompleted}
                </button>
              )}
            </div>

            {appointment.status !== "cancelled" && (
              <button
                disabled={isUpdating}
                onClick={() => handleStatus("cancelled")}
                className="w-full py-2 px-3 rounded-xl border border-rose-200 dark:border-rose-900/40 text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/30 text-xs font-semibold transition-colors flex items-center justify-center gap-1.5"
              >
                <XCircle className="w-3.5 h-3.5" />
                {t.crm.actions.cancel}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
