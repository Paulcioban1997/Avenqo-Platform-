"use client";

import React, { useState, useEffect } from "react";
import { Wrench, Plus, CheckCircle2, Clock, DollarSign, AlertCircle, RefreshCw } from "lucide-react";
import { getAuthHeaders } from "@/lib/api-headers";
import { useLocale } from "@/lib/i18n/locale-context";

interface ServiceItem {
  id: string;
  name: string;
  description?: string | null;
  duration_minutes: number;
  price: number;
  currency: string;
  category?: string | null;
  color_hex?: string;
  is_approved_by_owner?: boolean;
  is_published?: boolean;
}

export function CRMServicesSettings() {
  const { locale } = useLocale();
  const [services, setServices] = useState<ServiceItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isAdding, setIsAdding] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [durationMinutes, setDurationMinutes] = useState(60);
  const [price, setPrice] = useState(75);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    fetchServices();
  }, []);

  const fetchServices = async () => {
    setIsLoading(true);
    try {
      const headers = getAuthHeaders();
      const res = await fetch("/api/v1/crm/services", { headers });
      if (res.ok) {
        const data = await res.json();
        setServices(Array.isArray(data) ? data : []);
      }
    } catch {
      // ignore
    } finally {
      setIsLoading(false);
    }
  };

  const handleToggleApproval = async (serviceId: string) => {
    setError(null);
    setSuccess(null);
    try {
      const res = await fetch(`/api/v1/crm/services/${serviceId}/toggle-approval`, {
        method: "POST",
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        const updated = await res.json();
        setSuccess(
          updated.is_approved_by_owner
            ? (locale.startsWith("fr") ? "Prestation approuvée et publiée pour la réservation publique." : "Service approved and published for bookings.")
            : (locale.startsWith("fr") ? "Prestation désactivée de la réservation publique." : "Service disabled from public booking.")
        );
        fetchServices();
      } else {
        const err = await res.json().catch(() => ({}));
        setError(err.detail || (locale.startsWith("fr") ? "Action non autorisée." : "Action unauthorized."));
      }
    } catch {
      setError(locale.startsWith("fr") ? "Erreur réseau." : "Network error.");
    }
  };

  const handleCreateService = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setError(null);
    setSuccess(null);
    try {
      const headers = { "Content-Type": "application/json", ...getAuthHeaders() };
      const res = await fetch("/api/v1/crm/services", {
        method: "POST",
        headers,
        body: JSON.stringify({
          name: name.trim(),
          description: description.trim() || null,
          duration_minutes: Number(durationMinutes) || 60,
          price: Number(price) || 0,
          currency: "CAD",
          category: "retail",
          color_hex: "#0076FF",
        }),
      });
      if (res.ok) {
        setSuccess(locale.startsWith("fr") ? "Prestation ajoutée avec succès." : "Service added successfully.");
        setName("");
        setDescription("");
        setDurationMinutes(60);
        setPrice(75);
        setIsAdding(false);
        fetchServices();
      } else {
        const err = await res.json().catch(() => ({}));
        setError(err.message || err.detail || (locale.startsWith("fr") ? "Erreur lors de l'ajout." : "Failed to add service."));
      }
    } catch (err: any) {
      setError(err.message || "Erreur réseau.");
    }
  };

  return (
    <div className="p-5 rounded-2xl bg-white dark:bg-[#0B0F19] border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-950/50 flex items-center justify-center border border-blue-100 dark:border-blue-900/40">
            <Wrench className="w-5 h-5 text-[#0076FF]" />
          </div>
          <div>
            <h4 className="text-sm font-bold text-slate-900 dark:text-white">
              {locale.startsWith("fr") ? "Prestations & Tarifs configurés" : "Services & Rates Configuration"}
            </h4>
            <span className="text-xs text-slate-400">
              {locale.startsWith("fr")
                ? "Gérez les services offerts aux clients et leurs prix réels en CAD"
                : "Manage offered services and actual prices in CAD"}
            </span>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setIsAdding(!isAdding)}
          className="px-3.5 py-1.5 text-xs font-semibold rounded-xl bg-[#0076FF] text-white hover:bg-blue-600 transition flex items-center gap-1.5 shadow-sm"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>{isAdding ? (locale.startsWith("fr") ? "Fermer" : "Close") : (locale.startsWith("fr") ? "Nouvelle prestation" : "Add Service")}</span>
        </button>
      </div>

      {error && (
        <div className="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900/40 text-rose-700 dark:text-rose-300 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {success && (
        <div className="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900/40 text-emerald-700 dark:text-emerald-300 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{success}</span>
        </div>
      )}

      {isAdding && (
        <form onSubmit={handleCreateService} className="p-4 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-blue-200 dark:border-blue-900/40 space-y-3 animate-in fade-in">
          <h5 className="text-xs font-bold text-slate-900 dark:text-white">
            {locale.startsWith("fr") ? "Ajouter une prestation commerciale" : "Add a Commercial Service"}
          </h5>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="sm:col-span-2">
              <label className="text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1 block">
                {locale.startsWith("fr") ? "Intitulé du service *" : "Service Title *"}
              </label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={locale.startsWith("fr") ? "Ex: Entretien équipement & affûtage" : "e.g. Gear tuning"}
                className="w-full px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white"
              />
            </div>
            <div>
              <label className="text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1 block">
                {locale.startsWith("fr") ? "Tarif (CAD) *" : "Price (CAD) *"}
              </label>
              <input
                type="number"
                min="0"
                step="0.01"
                required
                value={price}
                onChange={(e) => setPrice(parseFloat(e.target.value) || 0)}
                className="w-full px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white"
              />
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="sm:col-span-2">
              <label className="text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1 block">
                {locale.startsWith("fr") ? "Description (optionnelle)" : "Description (optional)"}
              </label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={locale.startsWith("fr") ? "Ex: Réglage des fixations et fartage à chaud" : "e.g. Binding adjustment"}
                className="w-full px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white"
              />
            </div>
            <div>
              <label className="text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1 block">
                {locale.startsWith("fr") ? "Durée :" : "Duration:"}
              </label>
              <select
                value={durationMinutes}
                onChange={(e) => setDurationMinutes(parseInt(e.target.value) || 60)}
                className="w-full px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white"
              >
                <option value={15}>15 min</option>
                <option value={30}>30 min</option>
                <option value={45}>45 min</option>
                <option value={60}>60 min</option>
                <option value={90}>90 min</option>
                <option value={120}>120 min</option>
              </select>
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setIsAdding(false)}
              className="px-3 py-1.5 text-xs text-slate-500 hover:text-slate-700"
            >
              {locale.startsWith("fr") ? "Annuler" : "Cancel"}
            </button>
            <button
              type="submit"
              className="px-4 py-1.5 text-xs font-bold rounded-lg bg-[#0076FF] text-white hover:bg-blue-600 transition"
            >
              {locale.startsWith("fr") ? "Confirmer la prestation" : "Confirm Service"}
            </button>
          </div>
        </form>
      )}

      {/* Services List */}
      <div className="space-y-2">
        {isLoading ? (
          <div className="p-4 text-center text-xs text-slate-400">
            <RefreshCw className="w-4 h-4 animate-spin mx-auto mb-1 text-slate-400" />
            <span>{locale.startsWith("fr") ? "Chargement des prestations..." : "Loading services..."}</span>
          </div>
        ) : services.length === 0 ? (
          <p className="text-xs text-slate-400 italic p-3 text-center">
            {locale.startsWith("fr") ? "Aucune prestation configurée." : "No services configured yet."}
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {services.map((svc) => {
              const isApproved = svc.is_approved_by_owner ?? (svc.category !== "clinic");
              return (
                <div
                  key={svc.id}
                  className="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/30 flex items-start justify-between gap-3"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-bold text-slate-900 dark:text-white">{svc.name}</span>
                      {isApproved ? (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-200 border border-emerald-300 dark:border-emerald-800/60">
                          {locale.startsWith("fr") ? "Approuvé & Publié" : "Approved & Published"}
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-200 border border-amber-300 dark:border-amber-800/60">
                          {locale.startsWith("fr") ? "Démo non approuvée — Réservation bloquée" : "Unapproved Demo — Booking Blocked"}
                        </span>
                      )}
                    </div>
                    {svc.description && (
                      <p className="text-[11px] text-slate-500 dark:text-slate-400">{svc.description}</p>
                    )}
                    <div className="flex items-center gap-3 text-[11px] text-slate-400 pt-0.5">
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3 text-[#0076FF]" />
                        <span>{svc.duration_minutes} min</span>
                      </span>
                      <span className="flex items-center gap-1">
                        <DollarSign className="w-3 h-3 text-emerald-500" />
                        <span className="font-semibold text-slate-700 dark:text-slate-300">
                          {Number(svc.price).toFixed(2)} CAD
                        </span>
                      </span>
                    </div>
                  </div>

                  <div className="shrink-0 flex items-center">
                    {isApproved ? (
                      <button
                        type="button"
                        onClick={() => handleToggleApproval(svc.id)}
                        className="px-2.5 py-1 text-[11px] font-medium rounded-lg text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition border border-slate-200 dark:border-slate-700"
                        title={locale.startsWith("fr") ? "Suspendre la réservation publique" : "Disable from booking"}
                      >
                        {locale.startsWith("fr") ? "Désactiver" : "Disable"}
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => handleToggleApproval(svc.id)}
                        className="px-3 py-1 text-[11px] font-bold rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white transition flex items-center gap-1 shadow-sm"
                        title={locale.startsWith("fr") ? "Valider et publier pour les clients" : "Approve and publish"}
                      >
                        <CheckCircle2 className="w-3 h-3" />
                        <span>{locale.startsWith("fr") ? "Approuver et publier" : "Approve & Publish"}</span>
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
