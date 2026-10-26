"use client";

import React, { useState, useEffect } from "react";
import {
  X,
  Calendar,
  Clock,
  User,
  Wrench,
  DollarSign,
  AlertCircle,
  CheckCircle2,
  Plus,
  FileText,
} from "lucide-react";
import type { AppTranslations } from "@/lib/i18n/app-dictionary";
import { validDate, metricText } from "./crm-format";
import { getAuthHeaders } from "@/lib/api-headers";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";
import type { AppointmentItem } from "./appointment-details-drawer";

interface ClientOption {
  id: string;
  first_name: string;
  last_name: string;
  email?: string | null;
  phone?: string | null;
}

async function readApiError(response: Response): Promise<{ message: string; requestId?: string; isConflict?: boolean }> {
  const data = await response.json().catch(() => ({}));
  let message = "";
  if (Array.isArray(data.detail)) {
    message = data.detail
      .map((item: { loc?: unknown[]; msg?: string }) => {
        const field = Array.isArray(item.loc) ? item.loc.slice(1).join(".") : "";
        return field ? `${field}: ${item.msg}` : item.msg || "";
      })
      .filter(Boolean)
      .join("; ");
  } else if (typeof data.detail === "string") {
    if (data.detail === "OUTSIDE_WORKING_HOURS") {
      message = "Ce créneau est en dehors des heures d'ouverture de l'entreprise ou des horaires du collaborateur.";
    } else if (data.detail === "INVALID_WORKING_HOURS") {
      message = "Les horaires d'ouverture configurés sont invalides.";
    } else if (data.detail === "RESOURCE_NOT_AUTHORIZED") {
      message = "La ressource sélectionnée (service ou collaborateur) n'est pas autorisée.";
    } else {
      message = data.detail;
    }
  } else if (data.detail && typeof data.detail === "object") {
    if (data.detail.code === "APPOINTMENT_CONFLICT") {
      message = "Conflit d'horaire : ce créneau est déjà réservé dans le calendrier.";
    } else {
      message = data.detail.message || JSON.stringify(data.detail);
    }
  } else if (typeof data.error?.message === "string") {
    message = data.error.message;
  } else if (typeof data.message === "string") {
    message = data.message;
  }

  if (!message) {
    if (response.status === 401) {
      message = "Votre session a expiré. Reconnectez-vous.";
    } else if (response.status === 409) {
      message = "Conflit d'horaire détecté : ce créneau chevauche un rendez-vous existant.";
    } else if (response.status === 403) {
      message = "Action non autorisée pour votre rôle.";
    } else {
      message = `Erreur (${response.status}) lors de l'enregistrement du rendez-vous.`;
    }
  }

  return { message, requestId: data.request_id, isConflict: response.status === 409 };
}

interface ServiceOption {
  id: string;
  name: string;
  duration_minutes: number;
  price: number;
  category?: string | null;
  is_approved_by_owner?: boolean;
  is_published?: boolean;
}

interface EmployeeOption {
  id: string;
  first_name: string;
  last_name: string;
  color_code?: string | null;
}

interface NewAppointmentModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  initialAppointment?: AppointmentItem | null;
  t: AppTranslations;
}

export function NewAppointmentModal({
  isOpen,
  onClose,
  onSuccess,
  initialAppointment,
  t,
}: NewAppointmentModalProps) {
  const { locale } = useLocale();
  const [clients, setClients] = useState<ClientOption[]>([]);
  const [services, setServices] = useState<ServiceOption[]>([]);
  const [employees, setEmployees] = useState<EmployeeOption[]>([]);
  const [isLoadingMeta, setIsLoadingMeta] = useState(false);
  const [requiresReconnect, setRequiresReconnect] = useState(false);

  // Custom Service inline creation state
  const [isCreatingService, setIsCreatingService] = useState(false);
  const [newServiceName, setNewServiceName] = useState("");
  const [newServiceDuration, setNewServiceDuration] = useState(60);
  const [newServicePrice, setNewServicePrice] = useState(75);
  const [isSavingService, setIsSavingService] = useState(false);

  // Form State
  const [clientId, setClientId] = useState("");
  const [isCreatingClient, setIsCreatingClient] = useState(false);
  const [newClientFirst, setNewClientFirst] = useState("");
  const [newClientLast, setNewClientLast] = useState("");
  const [newClientPhone, setNewClientPhone] = useState("");
  const [newClientEmail, setNewClientEmail] = useState("");

  const [serviceId, setServiceId] = useState("");
  const [employeeId, setEmployeeId] = useState("");
  const [title, setTitle] = useState("");
  const [startDate, setStartDate] = useState("");
  const [startTime, setStartTime] = useState("09:00");
  const [durationMinutes, setDurationMinutes] = useState(60);
  const [price, setPrice] = useState<number>(0);
  const [notes, setNotes] = useState("");

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflictWarning, setConflictWarning] = useState<string | null>(null);

  // Initialize or populate if editing/rescheduling
  useEffect(() => {
    if (!isOpen) return;

    fetchDropdownData();

    if (initialAppointment) {
      setClientId(initialAppointment.client_id || "");
      setServiceId(initialAppointment.service_id || "");
      setEmployeeId(initialAppointment.employee_id || "");
      setTitle(initialAppointment.title || "");
      setDurationMinutes(initialAppointment.duration_minutes || 60);
      setPrice(initialAppointment.price || 0);
      setNotes(initialAppointment.notes || "");

      const dt = validDate(initialAppointment.start_time);
      if (!dt) {
        setStartDate("");
        setStartTime("");
        setError(t.crm.modal.dateRequired);
        return;
      }
      const yyyy = dt.getFullYear();
      const mm = String(dt.getMonth() + 1).padStart(2, "0");
      const dd = String(dt.getDate()).padStart(2, "0");
      setStartDate(`${yyyy}-${mm}-${dd}`);

      const hh = String(dt.getHours()).padStart(2, "0");
      const min = String(dt.getMinutes()).padStart(2, "0");
      setStartTime(`${hh}:${min}`);

    } else {
      // Default to today
      const today = new Date();
      const yyyy = today.getFullYear();
      const mm = String(today.getMonth() + 1).padStart(2, "0");
      const dd = String(today.getDate()).padStart(2, "0");
      setStartDate(`${yyyy}-${mm}-${dd}`);
      setStartTime("10:00");
      setTitle("");
      setNotes("");
      setClientId("");
      setServiceId("");
      setEmployeeId("");
      setDurationMinutes(60);
      setPrice(0);
      setIsCreatingClient(false);
      setIsCreatingService(false);
    }
    setError(null);
    setConflictWarning(null);
  }, [isOpen, initialAppointment]);

  const fetchDropdownData = async () => {
    setIsLoadingMeta(true);
    try {
      const headers = getAuthHeaders();

      const [cRes, sRes, eRes, calRes] = await Promise.all([
        apiFetch("/api/v1/crm/clients?limit=100", { headers }),
        apiFetch("/api/v1/crm/services", { headers }),
        apiFetch("/api/v1/crm/employees", { headers }),
        apiFetch("/api/v1/crm/calendar/connection", { headers }).catch(() => null),
      ]);

      if (cRes.ok) {
        const cData = await cRes.json();
        setClients(Array.isArray(cData) ? cData : (cData.items || []));
      } else {
        const details = await readApiError(cRes);
        throw new Error(details.message);
      }
      if (sRes.ok) {
        const sData = await sRes.json();
        setServices(sData || []);
      }
      if (eRes.ok) {
        const eData = await eRes.json();
        setEmployees(eData || []);
      }
      if (calRes && calRes.ok) {
        const calData = await calRes.json();
        const needsReconnect = Boolean(
          calData.requires_reconnect ||
          calData.sync_status === "error" ||
          calData.sync_status === "revoked" ||
          (!calData.connected && calData.provider === "google") ||
          (calData.last_synced_at && (Date.now() - new Date(calData.last_synced_at).getTime()) >= 6 * 86400000)
        );
        setRequiresReconnect(needsReconnect);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t.crm.actions.mutationError);
    } finally {
      setIsLoadingMeta(false);
    }
  };

  const handleCreateCustomService = async () => {
    if (!newServiceName.trim()) return;
    setIsSavingService(true);
    try {
      const res = await apiFetch("/api/v1/crm/services", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({
          name: newServiceName.trim(),
          duration_minutes: Number(newServiceDuration) || 60,
          price: Number(newServicePrice) || 0,
          currency: "CAD",
          category: "retail",
        }),
      });
      if (res.ok) {
        const created = await res.json();
        const fullService = {
          id: created.id,
          name: created.name,
          duration_minutes: Number(newServiceDuration) || 60,
          price: created.price,
        };
        setServices((prev) => [...prev, fullService]);
        setServiceId(created.id);
        setDurationMinutes(fullService.duration_minutes);
        setPrice(fullService.price);
        if (!title) setTitle(fullService.name);
        setIsCreatingService(false);
        setNewServiceName("");
      }
    } catch {
      // ignore
    } finally {
      setIsSavingService(false);
    }
  };

  const handleServiceChange = (sid: string) => {
    const selected = services.find((s) => s.id === sid);
    if (selected) {
      const isApproved = selected.is_approved_by_owner ?? (selected.category !== "clinic");
      if (!isApproved) {
        setError(
          locale.startsWith("fr")
            ? "Ce service de démonstration n'a pas été approuvé par le propriétaire pour la réservation publique."
            : "This demo service has not been approved by the owner for public booking."
        );
        return;
      }
    }
    setError(null);
    setServiceId(sid);
    if (selected) {
      setDurationMinutes(selected.duration_minutes);
      setPrice(selected.price);
      if (!title) {
        setTitle(selected.name);
      }
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setConflictWarning(null);

    if (serviceId) {
      const selected = services.find((s) => s.id === serviceId);
      if (selected) {
        const isApproved = selected.is_approved_by_owner ?? (selected.category !== "clinic");
        if (!isApproved) {
          setError(
            locale.startsWith("fr")
              ? "Ce service de démonstration n'a pas été approuvé par le propriétaire pour la réservation publique."
              : "This demo service has not been approved by the owner for public booking."
          );
          return;
        }
      }
    }

    if (!startDate || !startTime) {
      setError(t.crm.modal.dateRequired || "Date et heure requises.");
      return;
    }

    setIsSubmitting(true);
    try {
      const headers: HeadersInit = {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
      };

      let finalClientId = clientId;

      // Inline client creation if selected
      if (isCreatingClient) {
        if (!newClientFirst || !newClientLast) {
          setError("Nom et prénom du client requis.");
          setIsSubmitting(false);
          return;
        }
        const clientRes = await apiFetch("/api/v1/crm/clients", {
          method: "POST",
          headers,
          body: JSON.stringify({
            first_name: newClientFirst,
            last_name: newClientLast,
            phone: newClientPhone || null,
            email: newClientEmail || null,
            preferred_language: locale,
          }),
        });
        if (!clientRes.ok) {
          const details = await readApiError(clientRes);
          throw new Error(details.message);
        }
        const newC = await clientRes.json();
        finalClientId = newC.id;
        const createdClient: ClientOption = {
          id: newC.id,
          first_name: newC.first_name || newClientFirst,
          last_name: newC.last_name || newClientLast,
          email: (newC.email ?? newClientEmail) || null,
          phone: (newC.phone ?? newClientPhone) || null,
        };
        setClients((current) => [createdClient, ...current.filter((client) => client.id !== createdClient.id)]);
        setClientId(createdClient.id);
        setIsCreatingClient(false);
      }

      if (!finalClientId) {
        setError(t.crm.modal.clientRequired || "Veuillez sélectionner un client.");
        setIsSubmitting(false);
        return;
      }

      const submittedStart = new Date(`${startDate}T${startTime}:00`);
      if (!Number.isFinite(submittedStart.getTime()) || !Number.isFinite(durationMinutes) || durationMinutes <= 0) {
        setError(t.crm.modal.dateRequired);
        return;
      }
      const startIso = submittedStart.toISOString();
      const endDt = new Date(new Date(startIso).getTime() + durationMinutes * 60000);
      const endIso = endDt.toISOString();

      const payload = {
        client_id: finalClientId,
        service_id: serviceId || null,
        employee_id: employeeId || null,
        title: title || "Rendez-vous CRM",
        start_time: startIso,
        end_time: endIso,
        duration_minutes: durationMinutes,
        price,
        notes: notes || null,
        industry_data: {},
      };

      let url = "/api/v1/crm/appointments";
      let method = "POST";

      if (initialAppointment) {
        url = `/api/v1/crm/appointments/${initialAppointment.id}`;
        method = "PUT";
      }

      const res = await apiFetch(url, {
        method,
        headers,
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const details = await readApiError(res);
        if (details.isConflict) {
          setConflictWarning(details.message);
          setIsSubmitting(false);
          return;
        }
        throw new Error(details.message);
      }

      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || "Une erreur est survenue.");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-2xl bg-white dark:bg-[#0B0F19] rounded-2xl border border-slate-200 dark:border-slate-800 shadow-2xl overflow-hidden max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-800">
          <div>
            <h2 className="text-lg font-bold text-slate-900 dark:text-white">
              {initialAppointment
                ? t.crm.modal.editAppointmentTitle || "Modifier le rendez-vous"
                : t.crm.header.newAppointment}
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              {t.crm.modal.subtitle || "Planification intelligente & synchronisation Google Calendar"}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 4-STEP BOOKING PROGRESSION: Service -> Disponibilité -> Coordonnées -> Confirmation */}
        <div className="px-6 py-2.5 bg-slate-50 dark:bg-slate-900/60 border-b border-slate-100 dark:border-white/[0.04] flex items-center justify-between text-[11px] font-bold text-slate-500 overflow-x-auto">
          <div className="flex items-center gap-1.5 text-[#0076FF]">
            <span className="w-5 h-5 rounded-full bg-blue-100 dark:bg-blue-950 text-[#0076FF] flex items-center justify-center text-[10px]">1</span>
            <span>{locale.startsWith("fr") ? "Prestation" : "Service"}</span>
          </div>
          <span className="text-slate-300">→</span>
          <div className="flex items-center gap-1.5 text-slate-700 dark:text-slate-300">
            <span className="w-5 h-5 rounded-full bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-400 flex items-center justify-center text-[10px]">2</span>
            <span>{locale.startsWith("fr") ? "Disponibilité" : "Time Slot"}</span>
          </div>
          <span className="text-slate-300">→</span>
          <div className="flex items-center gap-1.5 text-slate-700 dark:text-slate-300">
            <span className="w-5 h-5 rounded-full bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-400 flex items-center justify-center text-[10px]">3</span>
            <span>{locale.startsWith("fr") ? "Coordonnées" : "Contact Details"}</span>
          </div>
          <span className="text-slate-300">→</span>
          <div className="flex items-center gap-1.5 text-slate-700 dark:text-slate-300">
            <span className="w-5 h-5 rounded-full bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-400 flex items-center justify-center text-[10px]">4</span>
            <span>{locale.startsWith("fr") ? "Confirmation" : "Confirmation"}</span>
          </div>
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-5">
          {requiresReconnect && (
            <div className="p-3.5 rounded-xl bg-amber-50 dark:bg-amber-950/40 border border-amber-300 dark:border-amber-800 text-amber-900 dark:text-amber-200 text-xs flex items-start gap-2.5 shadow-xs">
              <AlertCircle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
              <div>
                <p className="font-bold">Reconnectez Google Calendar pour reprendre les réservations</p>
                <p className="text-[11px] text-amber-800 dark:text-amber-300/80 mt-0.5 leading-relaxed">
                  La synchronisation externe avec Google Calendar est actuellement indisponible. Pour protéger votre planning et empêcher toute double réservation, la création de créneaux est suspendue jusqu'à reconnexion.
                </p>
              </div>
            </div>
          )}

          {error && (
            <div className="p-3.5 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900/40 text-rose-700 dark:text-rose-300 text-xs flex items-start gap-2.5">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {conflictWarning && (
            <div className="p-3.5 rounded-xl bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900/40 text-amber-700 dark:text-amber-300 text-xs flex items-start gap-2.5">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{conflictWarning}</span>
            </div>
          )}

          {/* SECTION 1: PRESTATION & COLLABORATEUR */}
          <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                <Wrench className="w-3.5 h-3.5 text-[#0076FF]" />
                <span>1. {locale.startsWith("fr") ? "Prestation & Service" : "Service & Pricing"}</span>
              </h3>
              <button
                type="button"
                onClick={() => setIsCreatingService(!isCreatingService)}
                className="text-xs text-[#0076FF] hover:underline flex items-center gap-1 font-semibold"
              >
                <Plus className="w-3 h-3" />
                <span>{isCreatingService ? (locale.startsWith("fr") ? "Annuler l'ajout" : "Cancel") : (locale.startsWith("fr") ? "+ Nouvelle prestation" : "+ Add Service")}</span>
              </button>
            </div>

            {isCreatingService ? (
              <div className="p-3 rounded-xl bg-white dark:bg-slate-800 border border-blue-200 dark:border-blue-900/50 space-y-3">
                <p className="text-[11px] font-semibold text-slate-700 dark:text-slate-300">
                  {locale.startsWith("fr") ? "Configurer une prestation pour votre boutique" : "Configure a custom service"}
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  <div className="sm:col-span-2">
                    <label className="text-[10px] text-slate-500 font-semibold">{locale.startsWith("fr") ? "Nom de la prestation *" : "Service Name *"}</label>
                    <input
                      type="text"
                      value={newServiceName}
                      onChange={(e) => setNewServiceName(e.target.value)}
                      placeholder={locale.startsWith("fr") ? "Ex: Entretien équipement & fixations" : "e.g. Gear maintenance"}
                      className="w-full mt-1 px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-slate-500 font-semibold">{locale.startsWith("fr") ? "Tarif (CAD) *" : "Price (CAD) *"}</label>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={newServicePrice}
                      onChange={(e) => setNewServicePrice(parseFloat(e.target.value) || 0)}
                      className="w-full mt-1 px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white"
                    />
                  </div>
                </div>
                <div className="flex items-center justify-between pt-1">
                  <div className="flex items-center gap-2">
                    <label className="text-[10px] text-slate-500 font-semibold">{locale.startsWith("fr") ? "Durée :" : "Duration:"}</label>
                    <select
                      value={newServiceDuration}
                      onChange={(e) => setNewServiceDuration(parseInt(e.target.value) || 60)}
                      className="px-2 py-1 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white"
                    >
                      <option value={30}>30 min</option>
                      <option value={45}>45 min</option>
                      <option value={60}>60 min</option>
                      <option value={90}>90 min</option>
                      <option value={120}>120 min</option>
                    </select>
                  </div>
                  <button
                    type="button"
                    onClick={handleCreateCustomService}
                    disabled={isSavingService || !newServiceName.trim()}
                    className="px-3 py-1.5 text-xs font-bold rounded-lg bg-[#0076FF] text-white hover:bg-blue-600 disabled:opacity-50 transition"
                  >
                    {isSavingService ? (locale.startsWith("fr") ? "Enregistrement..." : "Saving...") : (locale.startsWith("fr") ? "Enregistrer prestation" : "Save service")}
                  </button>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1 block">
                    {t.crm.filters.service} *
                  </label>
                  <select
                    value={serviceId}
                    onChange={(e) => handleServiceChange(e.target.value)}
                    className="w-full px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                  >
                    <option value="">{locale.startsWith("fr") ? "Sélectionner une prestation..." : "Select a service..."}</option>
                    {services.map((s) => {
                      const isApproved = s.is_approved_by_owner ?? (s.category !== "clinic");
                      return (
                        <option
                          key={s.id}
                          value={s.id}
                          disabled={!isApproved}
                          className={!isApproved ? "text-slate-400 italic" : ""}
                        >
                          {s.name} ({metricText(s.duration_minutes, locale, t.common.insufficientData)} min — {metricText(s.price, locale, t.common.insufficientData, 2)} $)
                          {!isApproved
                            ? (locale.startsWith("fr") ? " [Démo non approuvée — Réservation bloquée]" : " [Unapproved Demo — Booking Blocked]")
                            : ""}
                        </option>
                      );
                    })}
                  </select>
                </div>

                <div>
                  <label className="text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1 block">
                    {t.crm.filters.employee} ({locale.startsWith("fr") ? "optionnel" : "optional"})
                  </label>
                  <select
                    value={employeeId}
                    onChange={(e) => setEmployeeId(e.target.value)}
                    className="w-full px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                  >
                    <option value="">{locale.startsWith("fr") ? "Tous les collaborateurs disponibles" : "Any available staff"}</option>
                    {employees.map((emp) => (
                      <option key={emp.id} value={emp.id}>
                        {emp.first_name} {emp.last_name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            )}
          </div>

          {/* SECTION 2: DISPONIBILITÉ & CRÉNEAU HORAIRE */}
          <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
              <Calendar className="w-3.5 h-3.5 text-[#0076FF]" />
              <span>2. {locale.startsWith("fr") ? "Date & Créneau horaire" : "Date & Time Slot"}</span>
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1 block">
                  {t.crm.calendar.day} *
                </label>
                <input
                  type="date"
                  required
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="w-full px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                />
              </div>
              <div>
                <label className="text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1 block">
                  {t.crm.calendar.agenda} *
                </label>
                <input
                  type="time"
                  required
                  value={startTime}
                  onChange={(e) => setStartTime(e.target.value)}
                  className="w-full px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                />
              </div>
              <div>
                <label className="text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1 block">
                  {locale.startsWith("fr") ? "Durée (minutes)" : "Duration (minutes)"}
                </label>
                <input
                  type="number"
                  min="5"
                  step="5"
                  value={durationMinutes}
                  onChange={(e) => setDurationMinutes(parseInt(e.target.value) || 30)}
                  className="w-full px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                />
              </div>
            </div>

            <div>
              <label className="text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1 block">
                {locale.startsWith("fr") ? "Objet du rendez-vous" : "Appointment Subject"}
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder={locale.startsWith("fr") ? "Ex: Ajustement matériel ski / snowboard" : "e.g. Consultation"}
                className="w-full px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
              />
            </div>
          </div>

          {/* SECTION 3: COORDONNÉES CLIENT */}
          <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                <User className="w-3.5 h-3.5 text-[#0076FF]" />
                <span>3. {locale.startsWith("fr") ? "Coordonnées du client" : "Client Contact Details"}</span>
              </h3>
              <button
                type="button"
                onClick={() => setIsCreatingClient(!isCreatingClient)}
                className="text-xs text-[#0076FF] hover:underline flex items-center gap-1 font-semibold"
              >
                <Plus className="w-3 h-3" />
                <span>{isCreatingClient ? (locale.startsWith("fr") ? "Sélectionner existant" : "Select existing") : (locale.startsWith("fr") ? "+ Nouveau client" : "+ New Client")}</span>
              </button>
            </div>

            {isCreatingClient ? (
              <div className="p-3.5 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] text-slate-500 font-semibold">{locale.startsWith("fr") ? "Prénom *" : "First Name *"}</label>
                  <input
                    type="text"
                    required
                    value={newClientFirst}
                    onChange={(e) => setNewClientFirst(e.target.value)}
                    placeholder={locale.startsWith("fr") ? "Ex: Jean" : "e.g. John"}
                    className="w-full mt-1 px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-slate-500 font-semibold">{locale.startsWith("fr") ? "Nom de famille *" : "Last Name *"}</label>
                  <input
                    type="text"
                    required
                    value={newClientLast}
                    onChange={(e) => setNewClientLast(e.target.value)}
                    placeholder={locale.startsWith("fr") ? "Ex: Tremblay" : "e.g. Smith"}
                    className="w-full mt-1 px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-slate-500 font-semibold">{locale.startsWith("fr") ? "Téléphone" : "Phone Number"}</label>
                  <input
                    type="tel"
                    value={newClientPhone}
                    onChange={(e) => setNewClientPhone(e.target.value)}
                    placeholder="514-555-0199"
                    className="w-full mt-1 px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-slate-500 font-semibold">{locale.startsWith("fr") ? "Courriel" : "Email Address"}</label>
                  <input
                    type="email"
                    value={newClientEmail}
                    onChange={(e) => setNewClientEmail(e.target.value)}
                    placeholder="client@exemple.com"
                    className="w-full mt-1 px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                  />
                </div>
              </div>
            ) : (
              <select
                value={clientId}
                onChange={(e) => setClientId(e.target.value)}
                required
                className="w-full px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
              >
                <option value="">{locale.startsWith("fr") ? "Sélectionner un dossier client existant..." : "Select existing client..."}</option>
                {clients.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.first_name} {c.last_name} {c.phone ? `(${c.phone})` : ""} {c.email ? `— ${c.email}` : ""}
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* SECTION 4: CONFIRMATION & TARIFICATION */}
          <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-[#0076FF]" />
              <span>4. {locale.startsWith("fr") ? "Tarif & Confirmation finale" : "Pricing & Final Confirmation"}</span>
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1 flex items-center gap-1">
                  <DollarSign className="w-3 h-3 text-emerald-500" />
                  <span>{locale.startsWith("fr") ? "Montant facturé (CAD)" : "Price (CAD)"}</span>
                </label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={price}
                  onChange={(e) => setPrice(parseFloat(e.target.value) || 0)}
                  className="w-full px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                />
              </div>

              <div>
                <label className="text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1 flex items-center gap-1">
                  <FileText className="w-3 h-3 text-slate-400" />
                  <span>{locale.startsWith("fr") ? "Notes & Instructions" : "Notes"}</span>
                </label>
                <input
                  type="text"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder={locale.startsWith("fr") ? "Ex: Matériel apporté en magasin" : "e.g. Specific instructions"}
                  className="w-full px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                />
              </div>
            </div>
          </div>

          {/* Form Actions */}
          <div className="flex items-center justify-between pt-4 border-t border-slate-200 dark:border-slate-800">
            <span className="text-[11px] text-slate-400">
              {requiresReconnect
                ? (locale.startsWith("fr") ? "Réservations suspendues (Google Calendar révoqué)" : "Bookings paused (Google Calendar revoked)")
                : (locale.startsWith("fr") ? "Vérification stricte de disponibilité appliquée" : "Strict availability checks applied")}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-xs font-semibold rounded-xl text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
              >
                {t.common.cancel}
              </button>
              <button
                type="submit"
                disabled={isSubmitting || requiresReconnect}
                className={`px-5 py-2 text-xs font-bold rounded-xl transition flex items-center gap-2 shadow-sm ${
                  requiresReconnect
                    ? "bg-slate-200 dark:bg-slate-800 text-slate-400 dark:text-slate-500 cursor-not-allowed"
                    : "bg-[#0076FF] hover:bg-blue-600 text-white"
                }`}
              >
                {isSubmitting ? (
                  <>
                    <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    <span>{locale.startsWith("fr") ? "Chargement..." : "Loading..."}</span>
                  </>
                ) : requiresReconnect ? (
                  <span>{locale.startsWith("fr") ? "Reconnexion requise" : "Reconnect required"}</span>
                ) : (
                  <>
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>{initialAppointment ? (locale.startsWith("fr") ? "Mettre à jour" : "Update") : (locale.startsWith("fr") ? "Confirmer la réservation" : "Confirm booking")}</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
