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
  Car,
  FileText,
} from "lucide-react";
import type { AppTranslations } from "@/lib/i18n/app-dictionary";
import { getAuthHeaders } from "@/lib/api-headers";
import type { AppointmentItem } from "./appointment-details-drawer";

interface ClientOption {
  id: string;
  first_name: string;
  last_name: string;
  email?: string | null;
  phone?: string | null;
}

interface ServiceOption {
  id: string;
  name: string;
  duration_minutes: number;
  price: number;
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
  const [clients, setClients] = useState<ClientOption[]>([]);
  const [services, setServices] = useState<ServiceOption[]>([]);
  const [employees, setEmployees] = useState<EmployeeOption[]>([]);
  const [isLoadingMeta, setIsLoadingMeta] = useState(false);

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

  // Industry specific (e.g. Garage)
  const [vehicleMake, setVehicleMake] = useState("");
  const [vehicleModel, setVehicleModel] = useState("");
  const [vehiclePlate, setVehiclePlate] = useState("");

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

      const dt = new Date(initialAppointment.start_time);
      const yyyy = dt.getFullYear();
      const mm = String(dt.getMonth() + 1).padStart(2, "0");
      const dd = String(dt.getDate()).padStart(2, "0");
      setStartDate(`${yyyy}-${mm}-${dd}`);

      const hh = String(dt.getHours()).padStart(2, "0");
      const min = String(dt.getMinutes()).padStart(2, "0");
      setStartTime(`${hh}:${min}`);

      if (initialAppointment.industry_data?.vehicle) {
        setVehicleMake(initialAppointment.industry_data.vehicle.make || "");
        setVehicleModel(initialAppointment.industry_data.vehicle.model || "");
        setVehiclePlate(initialAppointment.industry_data.vehicle.plate || "");
      }
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
      setVehicleMake("");
      setVehicleModel("");
      setVehiclePlate("");
    }
    setError(null);
    setConflictWarning(null);
  }, [isOpen, initialAppointment]);

  const fetchDropdownData = async () => {
    setIsLoadingMeta(true);
    try {
      const headers = getAuthHeaders();

      const [cRes, sRes, eRes] = await Promise.all([
        fetch("/api/v1/crm/clients?limit=100", { headers }),
        fetch("/api/v1/crm/services", { headers }),
        fetch("/api/v1/crm/employees", { headers }),
      ]);

      if (cRes.ok) {
        const cData = await cRes.json();
        setClients(Array.isArray(cData) ? cData : (cData.items || []));
      }
      if (sRes.ok) {
        const sData = await sRes.json();
        setServices(sData || []);
      }
      if (eRes.ok) {
        const eData = await eRes.json();
        setEmployees(eData || []);
      }
    } catch {
      // Silently continue
    } finally {
      setIsLoadingMeta(false);
    }
  };

  const handleServiceChange = (sid: string) => {
    setServiceId(sid);
    const selected = services.find((s) => s.id === sid);
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
        const clientRes = await fetch("/api/v1/crm/clients", {
          method: "POST",
          headers,
          body: JSON.stringify({
            first_name: newClientFirst,
            last_name: newClientLast,
            phone: newClientPhone || null,
            email: newClientEmail || null,
          }),
        });
        if (!clientRes.ok) {
          const errData = await clientRes.json().catch(() => ({}));
          throw new Error(errData.detail || "Erreur lors de la création du client.");
        }
        const newC = await clientRes.json();
        finalClientId = newC.id;
      }

      if (!finalClientId) {
        setError(t.crm.modal.clientRequired || "Veuillez sélectionner un client.");
        setIsSubmitting(false);
        return;
      }

      const startIso = new Date(`${startDate}T${startTime}:00`).toISOString();
      const endDt = new Date(new Date(startIso).getTime() + durationMinutes * 60000);
      const endIso = endDt.toISOString();

      const industryData: Record<string, any> = {};
      if (vehicleMake || vehicleModel || vehiclePlate) {
        industryData.vehicle = {
          make: vehicleMake,
          model: vehicleModel,
          plate: vehiclePlate,
        };
      }

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
        industry_data: Object.keys(industryData).length > 0 ? industryData : null,
      };

      let url = "/api/v1/crm/appointments";
      let method = "POST";

      if (initialAppointment) {
        url = `/api/v1/crm/appointments/${initialAppointment.id}`;
        method = "PUT";
      }

      const res = await fetch(url, {
        method,
        headers,
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        if (res.status === 409) {
          setConflictWarning(data.detail || "Conflit d'horaire détecté.");
          setIsSubmitting(false);
          return;
        }
        throw new Error(data.detail || "Erreur lors de l'enregistrement du rendez-vous.");
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

        {/* Content */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-5">
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

          {/* Client Selection */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                <User className="w-3.5 h-3.5 text-[#0076FF]" />
                {t.crm.clients.client} *
              </label>
              <button
                type="button"
                onClick={() => setIsCreatingClient(!isCreatingClient)}
                className="text-xs text-[#0076FF] hover:underline flex items-center gap-1 font-medium"
              >
                <Plus className="w-3 h-3" />
                {isCreatingClient ? "Sélectionner un existant" : "+ Nouveau client"}
              </button>
            </div>

            {isCreatingClient ? (
              <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] text-slate-500">Prénom *</label>
                  <input
                    type="text"
                    required
                    value={newClientFirst}
                    onChange={(e) => setNewClientFirst(e.target.value)}
                    placeholder="Marc"
                    className="w-full mt-1 px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-slate-500">Nom *</label>
                  <input
                    type="text"
                    required
                    value={newClientLast}
                    onChange={(e) => setNewClientLast(e.target.value)}
                    placeholder="Tremblay"
                    className="w-full mt-1 px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-slate-500">Téléphone</label>
                  <input
                    type="tel"
                    value={newClientPhone}
                    onChange={(e) => setNewClientPhone(e.target.value)}
                    placeholder="514-555-0199"
                    className="w-full mt-1 px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-slate-500">Courriel</label>
                  <input
                    type="email"
                    value={newClientEmail}
                    onChange={(e) => setNewClientEmail(e.target.value)}
                    placeholder="marc@example.ca"
                    className="w-full mt-1 px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                  />
                </div>
              </div>
            ) : (
              <select
                value={clientId}
                onChange={(e) => setClientId(e.target.value)}
                required
                className="w-full px-3.5 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
              >
                <option value="">Sélectionnez un client...</option>
                {clients.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.first_name} {c.last_name} {c.phone ? `(${c.phone})` : ""}
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* Service & Employee */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5 mb-1.5">
                <Wrench className="w-3.5 h-3.5 text-[#00D4FF]" />
                {t.crm.filters.service}
              </label>
              <select
                value={serviceId}
                onChange={(e) => handleServiceChange(e.target.value)}
                className="w-full px-3.5 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
              >
                <option value="">Aucun service prédéfini</option>
                {services.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} ({s.duration_minutes} min — {s.price} $)
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5 mb-1.5">
                <User className="w-3.5 h-3.5 text-violet-500" />
                {t.crm.filters.employee}
              </label>
              <select
                value={employeeId}
                onChange={(e) => setEmployeeId(e.target.value)}
                className="w-full px-3.5 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
              >
                <option value="">Non assigné / Tout employé</option>
                {employees.map((emp) => (
                  <option key={emp.id} value={emp.id}>
                    {emp.first_name} {emp.last_name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Title / Purpose */}
          <div>
            <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5 mb-1.5">
              <FileText className="w-3.5 h-3.5 text-slate-400" />
              Objet ou Titre du rendez-vous
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Ex: Changement de pneus d'hiver / Consultation"
              className="w-full px-3.5 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
            />
          </div>

          {/* Date, Time & Duration */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5 mb-1.5">
                <Calendar className="w-3.5 h-3.5 text-[#0076FF]" />
                Date *
              </label>
              <input
                type="date"
                required
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full px-3.5 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5 mb-1.5">
                <Clock className="w-3.5 h-3.5 text-[#00D4FF]" />
                Heure de début *
              </label>
              <input
                type="time"
                required
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                className="w-full px-3.5 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5 mb-1.5">
                <Clock className="w-3.5 h-3.5 text-slate-400" />
                Durée (min)
              </label>
              <input
                type="number"
                min="5"
                step="5"
                value={durationMinutes}
                onChange={(e) => setDurationMinutes(parseInt(e.target.value) || 30)}
                className="w-full px-3.5 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
              />
            </div>
          </div>

          {/* Price */}
          <div>
            <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5 mb-1.5">
              <DollarSign className="w-3.5 h-3.5 text-emerald-500" />
              Tarif facturé (CAD)
            </label>
            <input
              type="number"
              min="0"
              step="0.01"
              value={price}
              onChange={(e) => setPrice(parseFloat(e.target.value) || 0)}
              className="w-full px-3.5 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
            />
          </div>

          {/* Industry Data (Garage / Vehicle) */}
          <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-900/40 border border-slate-200 dark:border-slate-800 space-y-2.5">
            <div className="flex items-center gap-1.5 text-xs font-medium text-slate-700 dark:text-slate-300">
              <Car className="w-4 h-4 text-slate-500" />
              <span>Détails spécifiques (Optionnel - ex: Véhicule atelier)</span>
            </div>
            <div className="grid grid-cols-3 gap-2.5">
              <div>
                <label className="text-[10px] text-slate-400">Marque</label>
                <input
                  type="text"
                  placeholder="Toyota"
                  value={vehicleMake}
                  onChange={(e) => setVehicleMake(e.target.value)}
                  className="w-full mt-1 px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:outline-none"
                />
              </div>
              <div>
                <label className="text-[10px] text-slate-400">Modèle</label>
                <input
                  type="text"
                  placeholder="RAV4 2022"
                  value={vehicleModel}
                  onChange={(e) => setVehicleModel(e.target.value)}
                  className="w-full mt-1 px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:outline-none"
                />
              </div>
              <div>
                <label className="text-[10px] text-slate-400">Immatriculation</label>
                <input
                  type="text"
                  placeholder="ABC 123"
                  value={vehiclePlate}
                  onChange={(e) => setVehiclePlate(e.target.value)}
                  className="w-full mt-1 px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:outline-none"
                />
              </div>
            </div>
          </div>

          {/* Notes */}
          <div>
            <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5 mb-1.5">
              <FileText className="w-3.5 h-3.5 text-slate-400" />
              Notes & Consignes
            </label>
            <textarea
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Instructions pour le technicien, demandes particulières..."
              className="w-full px-3.5 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
            />
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-200 dark:border-slate-800">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-xs font-medium text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition"
            >
              Annuler
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-5 py-2 text-xs font-medium rounded-xl bg-gradient-to-r from-[#0076FF] to-[#00D4FF] text-white shadow-md hover:opacity-90 disabled:opacity-50 transition flex items-center gap-2"
            >
              {isSubmitting ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Enregistrement...</span>
                </>
              ) : (
                <>
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>
                    {initialAppointment
                      ? "Enregistrer les modifications"
                      : "Créer le rendez-vous"}
                  </span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
