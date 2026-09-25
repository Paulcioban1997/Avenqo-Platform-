"use client";

import React, { useState, useEffect } from "react";
import {
  Users,
  Search,
  Plus,
  Mail,
  Phone,
  Calendar,
  DollarSign,
  Tag,
  Clock,
  ChevronRight,
  X,
  FileText,
  MessageSquare,
  AlertCircle,
  Building,
  UserCheck,
} from "lucide-react";
import type { AppTranslations } from "@/lib/i18n/app-dictionary";
import { getAuthHeaders } from "@/lib/api-headers";

export interface ClientItem {
  id: string;
  first_name: string;
  last_name: string;
  email?: string | null;
  phone?: string | null;
  company_name?: string | null;
  status: string;
  total_revenue?: number;
  appointments_count?: number;
  created_at: string;
  tags?: string[];
  notes?: string | null;
}

interface CRMClientsViewProps {
  t: AppTranslations;
  onSelectClientAppointments?: (clientId: string) => void;
}

export function CRMClientsView({ t, onSelectClientAppointments }: CRMClientsViewProps) {
  const [clients, setClients] = useState<ClientItem[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedStatus, setSelectedStatus] = useState("all");
  const [isLoading, setIsLoading] = useState(false);
  const [selectedClient, setSelectedClient] = useState<ClientItem | null>(null);
  const [client360Data, setClient360Data] = useState<any>(null);
  const [isLoading360, setIsLoading360] = useState(false);

  // New Client Modal
  const [isNewClientOpen, setIsNewClientOpen] = useState(false);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [status, setStatus] = useState("active");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchClients();
  }, [selectedStatus]);

  const fetchClients = async () => {
    setIsLoading(true);
    try {
      const headers = getAuthHeaders();

      let url = "/api/v1/crm/clients?limit=100";
      if (selectedStatus !== "all") url += `&status=${selectedStatus}`;
      if (searchQuery) url += `&search=${encodeURIComponent(searchQuery)}`;

      const res = await fetch(url, { headers });
      if (res.ok) {
        const data = await res.json();
        setClients(Array.isArray(data) ? data : (data.items || []));
      }
    } catch {
      // Keep empty list on network error
    } finally {
      setIsLoading(false);
    }
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchClients();
  };

  const openClient360 = async (client: ClientItem) => {
    setSelectedClient(client);
    setIsLoading360(true);
    try {
      const headers = getAuthHeaders();

      const res = await fetch(`/api/v1/crm/clients/${client.id}/360`, { headers });
      if (res.ok) {
        const data = await res.json();
        setClient360Data(data);
      }
    } catch {
      setClient360Data(null);
    } finally {
      setIsLoading360(false);
    }
  };

  const handleCreateClient = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      const res = await fetch("/api/v1/crm/clients", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          first_name: firstName,
          last_name: lastName,
          email: email || null,
          phone: phone || null,
          company_name: companyName || null,
          status,
        }),
      });

      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || "Impossible de créer le client.");
      }

      setIsNewClientOpen(false);
      setFirstName("");
      setLastName("");
      setEmail("");
      setPhone("");
      setCompanyName("");
      fetchClients();
    } catch (err: any) {
      setError(err.message || "Erreur inconnue");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Top action bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-white dark:bg-[#0B0F19] p-4 rounded-2xl border border-slate-200 dark:border-slate-800">
        <form onSubmit={handleSearchSubmit} className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Rechercher nom, courriel, téléphone..."
            className="w-full pl-9 pr-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:border-[#0076FF]"
          />
        </form>

        <div className="flex items-center gap-2.5">
          <select
            value={selectedStatus}
            onChange={(e) => setSelectedStatus(e.target.value)}
            className="text-xs px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-700 dark:text-slate-200 focus:outline-none focus:border-[#0076FF]"
          >
            <option value="all">Tous les statuts</option>
            <option value="active">Actif</option>
            <option value="lead">Prospect / Lead</option>
            <option value="inactive">Inactif</option>
            <option value="vip">VIP</option>
          </select>

          <button
            onClick={() => setIsNewClientOpen(true)}
            className="px-4 py-2 text-xs font-semibold rounded-xl bg-gradient-to-r from-[#0076FF] to-[#00D4FF] text-white shadow-md hover:opacity-90 transition flex items-center gap-1.5"
          >
            <Plus className="w-4 h-4" />
            <span>Nouveau client</span>
          </button>
        </div>
      </div>

      {/* Clients Table */}
      <div className="bg-white dark:bg-[#0B0F19] rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                <th className="py-3 px-4 font-semibold">Client</th>
                <th className="py-3 px-4 font-semibold">Contact</th>
                <th className="py-3 px-4 font-semibold">Statut</th>
                <th className="py-3 px-4 font-semibold">Rendez-vous</th>
                <th className="py-3 px-4 font-semibold text-right">Revenus cumulés</th>
                <th className="py-3 px-4 text-center">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {isLoading ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-slate-400">
                    Chargement des fiches clients...
                  </td>
                </tr>
              ) : clients.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-slate-400">
                    Aucun client trouvé dans ce portefeuille.
                  </td>
                </tr>
              ) : (
                clients.map((client) => (
                  <tr
                    key={client.id}
                    onClick={() => openClient360(client)}
                    className="hover:bg-slate-50 dark:hover:bg-slate-800/50 cursor-pointer transition"
                  >
                    <td className="py-3.5 px-4">
                      <div className="font-bold text-slate-900 dark:text-white">
                        {client.first_name} {client.last_name}
                      </div>
                      {client.company_name && (
                        <div className="text-[11px] text-slate-400 flex items-center gap-1 mt-0.5">
                          <Building className="w-3 h-3" />
                          {client.company_name}
                        </div>
                      )}
                    </td>
                    <td className="py-3.5 px-4 space-y-0.5">
                      {client.phone && (
                        <div className="flex items-center gap-1.5 text-slate-600 dark:text-slate-300">
                          <Phone className="w-3 h-3 text-slate-400" />
                          <span>{client.phone}</span>
                        </div>
                      )}
                      {client.email && (
                        <div className="flex items-center gap-1.5 text-slate-500">
                          <Mail className="w-3 h-3 text-slate-400" />
                          <span>{client.email}</span>
                        </div>
                      )}
                    </td>
                    <td className="py-3.5 px-4">
                      <span
                        className={`inline-block px-2.5 py-0.5 rounded-full text-[10px] font-semibold capitalize ${
                          client.status === "vip"
                            ? "bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300"
                            : client.status === "active"
                              ? "bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300"
                              : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300"
                        }`}
                      >
                        {client.status}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-slate-700 dark:text-slate-300">
                      <span className="font-medium">{client.appointments_count || 0}</span>
                    </td>
                    <td className="py-3.5 px-4 text-right font-bold text-emerald-600 dark:text-emerald-400">
                      {(client.total_revenue || 0).toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}{" "}
                      $
                    </td>
                    <td className="py-3.5 px-4 text-center">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          openClient360(client);
                        }}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-[#0076FF] hover:bg-slate-100 dark:hover:bg-slate-800 transition"
                      >
                        <ChevronRight className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* CLIENT 360 DRAWER */}
      {selectedClient && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="w-full max-w-xl bg-white dark:bg-[#0B0F19] h-full shadow-2xl border-l border-slate-200 dark:border-slate-800 flex flex-col overflow-hidden animate-in slide-in-from-right duration-300">
            {/* Drawer Header */}
            <div className="p-5 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-[#0076FF] to-[#00D4FF] text-white flex items-center justify-center font-bold text-base">
                  {selectedClient.first_name[0]}
                  {selectedClient.last_name[0]}
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-white">
                    {selectedClient.first_name} {selectedClient.last_name}
                  </h3>
                  <span className="text-xs text-slate-400">
                    Fiche 360 Client • Avenqo CRM
                  </span>
                </div>
              </div>
              <button
                onClick={() => setSelectedClient(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Drawer Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {isLoading360 ? (
                <div className="py-16 text-center text-slate-400 text-xs">
                  Chargement de l'historique et des analyses...
                </div>
              ) : (
                <>
                  {/* Quick KPI stats */}
                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800">
                      <span className="text-[11px] text-slate-400 block mb-1">
                        Valeur vie client (LTV)
                      </span>
                      <span className="text-lg font-bold text-emerald-600 dark:text-emerald-400">
                        {(client360Data?.total_revenue || 0).toLocaleString(undefined, {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })}{" "}
                        $
                      </span>
                    </div>
                    <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800">
                      <span className="text-[11px] text-slate-400 block mb-1">
                        Rendez-vous totaux
                      </span>
                      <span className="text-lg font-bold text-[#0076FF]">
                        {client360Data?.appointments?.length || 0}
                      </span>
                    </div>
                  </div>

                  {/* Contact Info */}
                  <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 space-y-2 text-xs">
                    <h4 className="font-semibold text-slate-900 dark:text-white mb-2">
                      Coordonnées directes
                    </h4>
                    <div className="flex items-center gap-2 text-slate-600 dark:text-slate-300">
                      <Phone className="w-3.5 h-3.5 text-slate-400" />
                      <span>{selectedClient.phone || "Non renseigné"}</span>
                    </div>
                    <div className="flex items-center gap-2 text-slate-600 dark:text-slate-300">
                      <Mail className="w-3.5 h-3.5 text-slate-400" />
                      <span>{selectedClient.email || "Non renseigné"}</span>
                    </div>
                    {selectedClient.company_name && (
                      <div className="flex items-center gap-2 text-slate-600 dark:text-slate-300">
                        <Building className="w-3.5 h-3.5 text-slate-400" />
                        <span>{selectedClient.company_name}</span>
                      </div>
                    )}
                  </div>

                  {/* Appointments Timeline */}
                  <div className="space-y-3">
                    <h4 className="text-xs font-semibold text-slate-900 dark:text-white uppercase tracking-wider">
                      Historique des Rendez-vous
                    </h4>
                    {!client360Data?.appointments || client360Data.appointments.length === 0 ? (
                      <p className="text-xs text-slate-400 italic">Aucun rendez-vous passé ou futur.</p>
                    ) : (
                      <div className="space-y-2">
                        {client360Data.appointments.map((app: any) => (
                          <div
                            key={app.id}
                            className="p-3 rounded-xl bg-slate-50 dark:bg-slate-900/40 border border-slate-200 dark:border-slate-800 text-xs flex items-center justify-between"
                          >
                            <div>
                              <div className="font-semibold text-slate-900 dark:text-white">
                                {app.title}
                              </div>
                              <div className="text-[11px] text-slate-400 mt-0.5">
                                {new Date(app.start_time).toLocaleDateString("fr-CA")} à{" "}
                                {new Date(app.start_time).toLocaleTimeString("fr-CA", {
                                  hour: "2-digit",
                                  minute: "2-digit",
                                })}
                              </div>
                            </div>
                            <div className="text-right">
                              <span className="font-bold text-emerald-600 block">{app.price} $</span>
                              <span className="text-[10px] text-slate-400 capitalize">{app.status}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Notes */}
                  <div className="space-y-3">
                    <h4 className="text-xs font-semibold text-slate-900 dark:text-white uppercase tracking-wider">
                      Notes internes & Suivi
                    </h4>
                    {!client360Data?.notes || client360Data.notes.length === 0 ? (
                      <p className="text-xs text-slate-400 italic">Aucune note enregistrée pour ce client.</p>
                    ) : (
                      <div className="space-y-2">
                        {client360Data.notes.map((note: any) => (
                          <div
                            key={note.id}
                            className="p-3 rounded-xl bg-amber-50/50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/40 text-xs"
                          >
                            <p className="text-slate-800 dark:text-slate-200">{note.content}</p>
                            <span className="text-[10px] text-slate-400 mt-1 block">
                              {new Date(note.created_at).toLocaleDateString("fr-CA")}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* NEW CLIENT MODAL */}
      {isNewClientOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="w-full max-w-md bg-white dark:bg-[#0B0F19] rounded-2xl border border-slate-200 dark:border-slate-800 shadow-2xl p-6">
            <div className="flex items-center justify-between pb-4 border-b border-slate-200 dark:border-slate-800 mb-4">
              <h3 className="text-base font-bold text-slate-900 dark:text-white">
                Ajouter un nouveau client
              </h3>
              <button
                onClick={() => setIsNewClientOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {error && (
              <div className="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900/40 text-rose-700 dark:text-rose-300 text-xs mb-4 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <form onSubmit={handleCreateClient} className="space-y-3.5 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-slate-600 dark:text-slate-400 block mb-1 font-medium">
                    Prénom *
                  </label>
                  <input
                    type="text"
                    required
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                  />
                </div>
                <div>
                  <label className="text-slate-600 dark:text-slate-400 block mb-1 font-medium">
                    Nom *
                  </label>
                  <input
                    type="text"
                    required
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                  />
                </div>
              </div>

              <div>
                <label className="text-slate-600 dark:text-slate-400 block mb-1 font-medium">
                  Téléphone
                </label>
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="514-555-0100"
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                />
              </div>

              <div>
                <label className="text-slate-600 dark:text-slate-400 block mb-1 font-medium">
                  Courriel
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="client@domaine.ca"
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                />
              </div>

              <div>
                <label className="text-slate-600 dark:text-slate-400 block mb-1 font-medium">
                  Entreprise
                </label>
                <input
                  type="text"
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  placeholder="Ex: Transport ABC"
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                />
              </div>

              <div>
                <label className="text-slate-600 dark:text-slate-400 block mb-1 font-medium">
                  Statut
                </label>
                <select
                  value={status}
                  onChange={(e) => setStatus(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                >
                  <option value="active">Actif</option>
                  <option value="lead">Prospect / Lead</option>
                  <option value="vip">VIP</option>
                  <option value="inactive">Inactif</option>
                </select>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-200 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsNewClientOpen(false)}
                  className="px-4 py-2 text-slate-600 dark:text-slate-400 font-medium hover:text-slate-900 dark:hover:text-white"
                >
                  Annuler
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-5 py-2 rounded-xl bg-gradient-to-r from-[#0076FF] to-[#00D4FF] text-white font-medium shadow-md hover:opacity-90 disabled:opacity-50"
                >
                  {isSubmitting ? "Création..." : "Créer le client"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
