"use client";

import React, { useState, useEffect } from "react";
import {
  Users,
  ShieldCheck,
  Briefcase,
  Award,
  Calendar,
  CheckCircle2,
  Clock,
  AlertCircle,
  Plus,
  Search,
  Check,
  X,
  ChevronRight,
  ChevronDown,
  Sparkles,
  PhoneCall,
  Lock,
  Layers,
  ArrowRight,
} from "lucide-react";
import { apiFetch } from "@/lib/api-request";
import { getAuthHeaders } from "@/lib/api-headers";
import { useLocale } from "@/lib/i18n/locale-context";

interface HREmployeeItem {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone?: string | null;
  role: string;
  job_title: string;
  department: string;
  hierarchy_level: "executive" | "management" | "operational";
  is_active: boolean;
  has_voice_pin: boolean;
  open_tasks_count: number;
  completed_tasks_count: number;
}

interface HROverview {
  total_employees: number;
  active_employees: number;
  departments_count: number;
  departments: string[];
  hierarchy_breakdown: { executive: number; management: number; operational: number };
  tasks_metrics: { total: number; open: number; completed: number; overdue: number };
  pending_leaves_count: number;
  company_industry: string;
}

interface HRSOPRole {
  role_title: string;
  department: string;
  hierarchy_level: string;
  key_responsibilities: string[];
  standard_operating_procedure: string[];
  safety_and_compliance: string[];
  time_optimization_tips: string[];
  revenue_booster_actions: string[];
}

interface HRSectorSOPResponse {
  sector: string;
  sector_name: string;
  overview: string;
  job_descriptions: HRSOPRole[];
}

interface HRSkillItem {
  id: string;
  name: string;
  category: string;
  level: number;
  certified: boolean;
  status: "verified" | "self_declared" | "ai_suggested" | "not_assessed";
  evidence_url_or_note?: string | null;
  verified_at?: string | null;
  verified_by?: string | null;
  employee_id: string;
  employee_name: string;
}

interface HRPerformanceReviewItem {
  id: string;
  user_id: string;
  employee_name: string;
  reviewer_name: string;
  review_period: string;
  rating: number;
  strengths?: string | null;
  growth_areas?: string | null;
  goals?: string | null;
  ai_coach_notes?: string | null;
  is_demo?: boolean;
  data_sufficient?: boolean;
  created_at: string;
}

interface HRLeaveItem {
  id: string;
  user_id: string;
  employee_name: string;
  leave_type: string;
  start_date: string;
  end_date: string;
  days_count: number;
  reason?: string | null;
  status: "pending" | "approved" | "rejected";
  approved_by?: string | null;
  created_at: string;
}

export function HRWorkspace() {
  const { locale } = useLocale();
  const [activeTab, setActiveTab] = useState<"overview" | "team" | "sops" | "skills" | "leaves">("overview");
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState<HROverview | null>(null);
  const [employees, setEmployees] = useState<HREmployeeItem[]>([]);
  const [sopsData, setSopsData] = useState<HRSectorSOPResponse | null>(null);
  const [skills, setSkills] = useState<HRSkillItem[]>([]);
  const [leaves, setLeaves] = useState<HRLeaveItem[]>([]);
  const [selectedSector, setSelectedSector] = useState<string>("automobile");
  const [moduleInactive, setModuleInactive] = useState(false);

  // Filters & Search
  const [teamSearch, setTeamSearch] = useState("");
  const [hierarchyFilter, setHierarchyFilter] = useState<string>("all");

  // Leave Modal
  const [isLeaveModalOpen, setIsLeaveModalOpen] = useState(false);
  const [leaveForm, setLeaveForm] = useState({
    leave_type: "vacation",
    start_date: "",
    end_date: "",
    days_count: 1,
    reason: "",
  });
  const [leaveSubmitting, setLeaveSubmitting] = useState(false);

  async function loadHRData() {
    try {
      setLoading(true);
      const headers = getAuthHeaders();

      const [resOverview, resEmployees, resSOPs, resSkills, resLeaves] = await Promise.all([
        apiFetch("/api/v1/hr/overview", { headers }),
        apiFetch("/api/v1/hr/employees", { headers }),
        apiFetch(`/api/v1/hr/job-descriptions?sector=${selectedSector}`, { headers }),
        apiFetch("/api/v1/hr/skills", { headers }),
        apiFetch("/api/v1/hr/leaves", { headers }),
      ]);

      if (resOverview.status === 403) {
        const errData = await resOverview.json().catch(() => ({}));
        if (JSON.stringify(errData).includes("module_inactive")) {
          setModuleInactive(true);
          setLoading(false);
          return;
        }
      }

      if (resOverview.ok) setOverview(await resOverview.json());
      if (resEmployees.ok) setEmployees(await resEmployees.json());
      if (resSOPs.ok) setSopsData(await resSOPs.json());
      if (resSkills.ok) setSkills(await resSkills.json());
      if (resLeaves.ok) setLeaves(await resLeaves.json());
    } catch (err) {
      console.error("Erreur de chargement des données RH:", err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadHRData();
  }, [selectedSector]);

  async function handleLeaveStatusUpdate(leaveId: string, status: "approved" | "rejected") {
    try {
      const headers = getAuthHeaders();
      const res = await apiFetch(`/api/v1/hr/leaves/${leaveId}/status`, {
        method: "PUT",
        headers,
        body: JSON.stringify({ status }),
      });
      if (res.ok) {
        setLeaves((prev) =>
          prev.map((l) => (l.id === leaveId ? { ...l, status } : l))
        );
      }
    } catch (err) {
      console.error("Erreur mise à jour statut congé:", err);
    }
  }

  async function handleCreateLeave(e: React.FormEvent) {
    e.preventDefault();
    try {
      setLeaveSubmitting(true);
      const headers = getAuthHeaders();
      const res = await apiFetch("/api/v1/hr/leaves", {
        method: "POST",
        headers,
        body: JSON.stringify({
          leave_type: leaveForm.leave_type,
          start_date: new Date(leaveForm.start_date).toISOString(),
          end_date: new Date(leaveForm.end_date).toISOString(),
          days_count: Number(leaveForm.days_count),
          reason: leaveForm.reason || undefined,
        }),
      });
      if (res.ok) {
        const newLeave = await res.json();
        setLeaves((prev) => [newLeave, ...prev]);
        setIsLeaveModalOpen(false);
        setLeaveForm({ leave_type: "vacation", start_date: "", end_date: "", days_count: 1, reason: "" });
      }
    } catch (err) {
      console.error("Erreur création congé:", err);
    } finally {
      setLeaveSubmitting(false);
    }
  }

  const filteredEmployees = employees.filter((emp) => {
    if (hierarchyFilter !== "all" && emp.hierarchy_level !== hierarchyFilter) return false;
    if (teamSearch.trim()) {
      const q = teamSearch.toLowerCase();
      const fullName = `${emp.first_name} ${emp.last_name}`.toLowerCase();
      return (
        fullName.includes(q) ||
        emp.email.toLowerCase().includes(q) ||
        emp.job_title.toLowerCase().includes(q) ||
        emp.department.toLowerCase().includes(q)
      );
    }
    return true;
  });

  return (
    <div className="space-y-6 max-w-7xl mx-auto px-4 sm:px-6 py-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-white/[0.08]">
        <div>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center text-white shadow-lg shadow-blue-500/20">
              <Users className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-xl font-extrabold text-white">
                Ressources Humaines & Hiérarchie d'Entreprise
              </h1>
              <p className="text-xs text-slate-400 mt-0.5">
                Organigramme, standards opératoires (SOP) métiers universels, gestion des compétences et coaching vocal.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-blue-500/10 text-blue-400 border border-blue-500/20">
            <Sparkles className="w-3.5 h-3.5" />
            Voice Coach Intégré
          </span>
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <ShieldCheck className="w-3.5 h-3.5" />
            RBAC Strict Délimité
          </span>
        </div>
      </div>

      {/* Tabs */}
      {moduleInactive ? (
        <div className="p-8 rounded-3xl bg-[#0B132B]/80 border border-white/[0.08] text-center max-w-xl mx-auto space-y-4 my-8">
          <div className="w-12 h-12 rounded-2xl bg-blue-500/10 text-blue-400 flex items-center justify-center mx-auto border border-blue-500/20">
            <Layers className="w-6 h-6" />
          </div>
          <h3 className="text-lg font-bold text-white">Module HR AI non activé</h3>
          <p className="text-xs text-slate-400 leading-relaxed">
            Le module Ressources Humaines (Hiérarchie d'équipe, SOPs métiers universels, gestion des compétences et congés)
            n'est pas activé pour cette entreprise. Vous pouvez l'activer directement dans vos paramètres selon vos quotas.
          </p>
          <a
            href="/settings"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold bg-[#0076FF] hover:bg-blue-600 text-white transition shadow-sm"
          >
            <span>Gérer les modules dans Paramètres</span>
            <ArrowRight className="w-4 h-4" />
          </a>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-2 border-b border-white/[0.08] overflow-x-auto pb-px">
            {[
              { key: "overview", label: "Vue d'ensemble", icon: Layers },
              { key: "team", label: "Organigramme & Équipe", icon: Users },
              { key: "sops", label: "Fiches de poste & SOPs", icon: Briefcase },
              { key: "skills", label: "Matrice de Compétences", icon: Award },
              { key: "leaves", label: "Congés & Absences", icon: Calendar },
            ].map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.key;
              return (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key as any)}
                  className={`flex items-center gap-2 px-4 py-2.5 rounded-t-xl text-xs font-bold transition border-b-2 whitespace-nowrap ${
                    isActive
                      ? "border-[#0076FF] text-[#0076FF] bg-blue-500/10"
                      : "border-transparent text-slate-400 hover:text-white hover:bg-white/[0.02]"
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  <span>{tab.label}</span>
                  {tab.key === "leaves" && overview && overview.pending_leaves_count > 0 && (
                    <span className="w-4 h-4 rounded-full bg-amber-500 text-black text-[10px] font-extrabold flex items-center justify-center">
                      {overview.pending_leaves_count}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

      {/* TAB 1: OVERVIEW */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          {/* Key Metrics Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="p-5 rounded-2xl bg-[#0B132B]/80 border border-white/[0.08] shadow-lg space-y-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Effectif Total</span>
              <div className="flex items-baseline justify-between">
                <span className="text-2xl font-extrabold text-white">{overview?.total_employees || 0}</span>
                <span className="text-xs font-bold text-emerald-400">
                  {overview?.active_employees || 0} actifs
                </span>
              </div>
              <p className="text-[11px] text-slate-500">
                {overview?.departments_count || 1} département(s) configuré(s)
              </p>
            </div>

            <div className="p-5 rounded-2xl bg-[#0B132B]/80 border border-white/[0.08] shadow-lg space-y-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Répartition Hiérarchique</span>
              <div className="flex items-baseline gap-2">
                <span className="text-xs font-extrabold px-2 py-0.5 rounded bg-purple-500/20 text-purple-300">
                  {overview?.hierarchy_breakdown.executive || 0} Dir.
                </span>
                <span className="text-xs font-extrabold px-2 py-0.5 rounded bg-blue-500/20 text-blue-300">
                  {overview?.hierarchy_breakdown.management || 0} Mgr.
                </span>
                <span className="text-xs font-extrabold px-2 py-0.5 rounded bg-slate-700/50 text-slate-300">
                  {overview?.hierarchy_breakdown.operational || 0} Opér.
                </span>
              </div>
              <p className="text-[11px] text-slate-500">Isolation stricte des données selon le grade</p>
            </div>

            <div className="p-5 rounded-2xl bg-[#0B132B]/80 border border-white/[0.08] shadow-lg space-y-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Tâches d'Équipe</span>
              <div className="flex items-baseline justify-between">
                <span className="text-2xl font-extrabold text-white">{overview?.tasks_metrics.open || 0}</span>
                <span className="text-xs font-bold text-blue-400">
                  {overview?.tasks_metrics.completed || 0} clôturées
                </span>
              </div>
              <p className="text-[11px] text-slate-500">
                {overview?.tasks_metrics.overdue || 0} en retard
              </p>
            </div>

            <div className="p-5 rounded-2xl bg-[#0B132B]/80 border border-white/[0.08] shadow-lg space-y-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Congés en Attente</span>
              <div className="flex items-baseline justify-between">
                <span className="text-2xl font-extrabold text-amber-400">{overview?.pending_leaves_count || 0}</span>
                <button
                  type="button"
                  onClick={() => setActiveTab("leaves")}
                  className="text-xs font-bold text-[#0076FF] hover:underline"
                >
                  Examiner →
                </button>
              </div>
              <p className="text-[11px] text-slate-500">Demandes soumises par les collaborateurs</p>
            </div>
          </div>

          {/* Performance & Voice Coach Synergy Card */}
          <div className="p-6 rounded-2xl bg-gradient-to-br from-[#0B1536] via-[#0A1026] to-[#070D1F] border border-blue-500/20 shadow-xl space-y-4">
            <div className="flex items-start justify-between flex-wrap gap-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <PhoneCall className="w-5 h-5 text-[#00D4FF]" />
                  <h3 className="text-sm font-extrabold text-white">
                    Synergie Voice AI Coach & Ressources Humaines
                  </h3>
                </div>
                <p className="text-xs text-slate-300 max-w-2xl leading-relaxed">
                  Chaque employé appelant le numéro d'entreprise avec son NIP vocal reçoit des conseils méthodologiques
                  pas-à-pas pour optimiser ses tâches journalières (gain moyen de 25% de productivité), tout en étant
                  motivé pour accélérer le chiffre d'affaires. L'employeur n'a plus besoin d'organiser des réunions de recadrage constantes.
                </p>
              </div>

              <div className="flex items-center gap-3">
                <div className="p-3 rounded-xl bg-slate-900/80 border border-white/10 text-center">
                  <span className="text-[10px] uppercase font-bold text-slate-400 block">Secteur Actif</span>
                  <span className="text-xs font-extrabold text-white">{overview?.company_industry || "Automobile"}</span>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-3 border-t border-white/[0.06]">
              <div className="flex items-start gap-2.5 text-xs text-slate-300">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                <span>
                  <strong>Accompagnement continu :</strong> le collaborateur demande comment faire une tâche et Voice lui donne la meilleure méthode.
                </span>
              </div>
              <div className="flex items-start gap-2.5 text-xs text-slate-300">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                <span>
                  <strong>Isolation hiérarchique :</strong> l'employé n'a jamais accès aux marges nettes ou au salaire de la direction.
                </span>
              </div>
              <div className="flex items-start gap-2.5 text-xs text-slate-300">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                <span>
                  <strong>Autonomie & Motivation :</strong> valorisation des accomplissements et rituels quotidiens de progression.
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: ORGANIGRAMME & TEAM */}
      {activeTab === "team" && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2 flex-wrap">
              <div className="relative">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  type="text"
                  value={teamSearch}
                  onChange={(e) => setTeamSearch(e.target.value)}
                  placeholder="Rechercher un collaborateur, poste ou courriel..."
                  className="pl-9 pr-4 py-2 rounded-xl text-xs bg-slate-900 border border-white/10 text-white placeholder-slate-500 focus:outline-none focus:border-[#0076FF]"
                />
              </div>

              <div className="flex items-center gap-1 bg-slate-900 p-1 rounded-xl border border-white/10">
                {[
                  { id: "all", label: "Tous" },
                  { id: "executive", label: "Direction" },
                  { id: "management", label: "Encadrement" },
                  { id: "operational", label: "Opérations" },
                ].map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    onClick={() => setHierarchyFilter(f.id)}
                    className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition ${
                      hierarchyFilter === f.id
                        ? "bg-[#0076FF] text-white"
                        : "text-slate-400 hover:text-white"
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>

            <span className="text-xs text-slate-400 font-medium">
              {filteredEmployees.length} collaborateur(s)
            </span>
          </div>

          {/* Team Cards Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredEmployees.map((emp) => {
              const hierBadge =
                emp.hierarchy_level === "executive"
                  ? { bg: "bg-purple-500/20 text-purple-300 border-purple-500/30", label: "Direction / Exécutif" }
                  : emp.hierarchy_level === "management"
                  ? { bg: "bg-blue-500/20 text-blue-300 border-blue-500/30", label: "Management / Chef" }
                  : { bg: "bg-slate-700/40 text-slate-300 border-slate-600/40", label: "Opérationnel / Terrain" };

              return (
                <div
                  key={emp.id}
                  className="p-5 rounded-2xl bg-[#0B132B]/80 border border-white/[0.08] space-y-4 hover:border-white/20 transition shadow-lg flex flex-col justify-between"
                >
                  <div className="space-y-3">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-full bg-slate-800 border border-white/10 text-white font-bold flex items-center justify-center text-sm">
                          {emp.first_name?.[0] || emp.email[0].toUpperCase()}
                        </div>
                        <div>
                          <h4 className="text-sm font-bold text-white">
                            {emp.first_name} {emp.last_name}
                          </h4>
                          <span className="text-xs text-slate-400 block">{emp.job_title}</span>
                        </div>
                      </div>

                      <span
                        className={`text-[10px] font-extrabold uppercase px-2 py-0.5 rounded-full border ${hierBadge.bg}`}
                      >
                        {hierBadge.label}
                      </span>
                    </div>

                    <div className="space-y-1 text-xs text-slate-400 pt-1">
                      <div className="flex items-center justify-between">
                        <span>Département :</span>
                        <span className="text-white font-medium">{emp.department}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span>Courriel :</span>
                        <span className="text-white font-mono">{emp.email}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span>Téléphone :</span>
                        <span className="text-white font-mono">{emp.phone || "Non configuré"}</span>
                      </div>
                    </div>
                  </div>

                  <div className="pt-3 border-t border-white/[0.06] flex items-center justify-between text-xs">
                    <div className="flex items-center gap-1.5">
                      <Lock className="w-3.5 h-3.5 text-blue-400" />
                      <span className={emp.has_voice_pin ? "text-emerald-400 font-bold" : "text-slate-500"}>
                        {emp.has_voice_pin ? "NIP Vocal Actif" : "Sans NIP vocal"}
                      </span>
                    </div>
                    <span className="text-slate-400">
                      <strong className="text-white">{emp.open_tasks_count}</strong> tâche(s) ouverte(s)
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* TAB 3: SOPS & JOB DESCRIPTIONS */}
      {activeTab === "sops" && (
        <div className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-2xl bg-[#0B132B]/80 border border-white/[0.08]">
            <div className="space-y-0.5">
              <h3 className="text-sm font-bold text-white">
                Standards Opératoires d'Excellence (SOPs) & Fiches de Poste
              </h3>
              <p className="text-xs text-slate-400">
                Processus éprouvés par secteur d'activité, règles de sécurité, astuces de gain de temps et leviers de chiffre d'affaires.
              </p>
            </div>

            <select
              value={selectedSector}
              onChange={(e) => setSelectedSector(e.target.value)}
              className="px-3 py-2 rounded-xl text-xs font-bold bg-slate-900 border border-white/10 text-white focus:outline-none focus:border-[#0076FF]"
            >
              <option value="automobile">Automobile & Mécanique 🚗</option>
              <option value="construction">Construction & Rénovation 🔨</option>
              <option value="beaute">Coiffure & Esthétique ✂️</option>
              <option value="commerce">Commerce & Vente au Détail 🛍️</option>
              <option value="general">Services Généraux & Entreprises 🏢</option>
            </select>
          </div>

          {sopsData && (
            <div className="space-y-6">
              {sopsData.job_descriptions.map((role, idx) => (
                <div
                  key={idx}
                  className="rounded-2xl bg-[#0B132B]/80 border border-white/[0.08] p-6 space-y-5 shadow-xl"
                >
                  <div className="flex items-center justify-between flex-wrap gap-2 pb-3 border-b border-white/[0.06]">
                    <div>
                      <h4 className="text-base font-extrabold text-white">{role.role_title}</h4>
                      <span className="text-xs text-[#0076FF] font-semibold">{role.department}</span>
                    </div>
                    <span className="text-[10px] font-extrabold uppercase px-2.5 py-1 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
                      Niveau : {role.hierarchy_level}
                    </span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* Responsabilités Clés */}
                    <div className="space-y-2">
                      <h5 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                        <Briefcase className="w-3.5 h-3.5 text-blue-400" />
                        <span>Missions & Responsabilités Clés</span>
                      </h5>
                      <ul className="space-y-1.5 text-xs text-slate-300">
                        {role.key_responsibilities.map((r, i) => (
                          <li key={i} className="flex items-start gap-2">
                            <span className="text-[#0076FF] font-bold">•</span>
                            <span>{r}</span>
                          </li>
                        ))}
                      </ul>
                    </div>

                    {/* SOP Pas-à-Pas */}
                    <div className="space-y-2">
                      <h5 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                        <Clock className="w-3.5 h-3.5 text-emerald-400" />
                        <span>Procédure Opératoire Standard (SOP)</span>
                      </h5>
                      <ol className="space-y-1.5 text-xs text-slate-300">
                        {role.standard_operating_procedure.map((p, i) => (
                          <li key={i} className="flex items-start gap-2">
                            <span className="text-emerald-400 font-bold">{i + 1}.</span>
                            <span>{p}</span>
                          </li>
                        ))}
                      </ol>
                    </div>

                    {/* Optimisation Temps (-20% à -30%) */}
                    <div className="space-y-2 p-4 rounded-xl bg-blue-950/30 border border-blue-500/20">
                      <h5 className="text-xs font-bold text-[#00D4FF] flex items-center gap-2">
                        <Sparkles className="w-4 h-4" />
                        <span>Astuces d'Optimisation du Temps (-25%)</span>
                      </h5>
                      <ul className="space-y-1 text-xs text-slate-300">
                        {role.time_optimization_tips.map((tip, i) => (
                          <li key={i} className="flex items-start gap-2">
                            <span className="text-[#00D4FF]">⚡</span>
                            <span>{tip}</span>
                          </li>
                        ))}
                      </ul>
                    </div>

                    {/* Leviers Chiffre d'Affaires */}
                    <div className="space-y-2 p-4 rounded-xl bg-emerald-950/30 border border-emerald-500/20">
                      <h5 className="text-xs font-bold text-emerald-400 flex items-center gap-2">
                        <Award className="w-4 h-4" />
                        <span>Leviers d'Augmentation du Chiffre d'Affaires</span>
                      </h5>
                      <ul className="space-y-1 text-xs text-slate-300">
                        {role.revenue_booster_actions.map((act, i) => (
                          <li key={i} className="flex items-start gap-2">
                            <span className="text-emerald-400">📈</span>
                            <span>{act}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 4: SKILLS MATRIX */}
      {activeTab === "skills" && (
        <div className="space-y-4">
          <div className="p-4 rounded-2xl bg-[#0B132B]/80 border border-white/[0.08] flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-white">Matrice des Compétences & Certifications</h3>
              <p className="text-xs text-slate-400">
                Cartographie des aptitudes techniques, relationnelles et de conformité par collaborateur.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {skills.map((skill) => (
              <div
                key={skill.id}
                className="p-4 rounded-2xl bg-[#0B132B]/80 border border-white/[0.08] space-y-3"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <h4 className="text-xs font-bold text-white">{skill.name}</h4>
                    <span className="text-[11px] text-slate-400">{skill.employee_name}</span>
                  </div>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-300 border border-blue-500/20">
                    {skill.category}
                  </span>
                </div>

                <div className="flex items-center justify-between pt-1">
                  <div className="flex items-center gap-1 text-amber-400 text-sm">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <span key={i} className={i < skill.level ? "text-amber-400" : "text-slate-700"}>
                        ★
                      </span>
                    ))}
                  </div>

                  <div className="flex items-center gap-1.5 flex-wrap justify-end">
                    {skill.status === "verified" || skill.certified ? (
                      <span className="text-[10px] font-extrabold uppercase px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1">
                        <Check className="w-3 h-3" />
                        <span>Vérifié</span>
                      </span>
                    ) : skill.status === "self_declared" ? (
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20">
                        Auto-déclaré
                      </span>
                    ) : skill.status === "ai_suggested" ? (
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-purple-500/10 text-purple-300 border border-purple-500/20">
                        Suggéré IA
                      </span>
                    ) : (
                      <span className="text-[10px] text-slate-400 px-2 py-0.5 rounded bg-white/[0.04] border border-white/[0.06]">
                        Non Évalué
                      </span>
                    )}
                  </div>
                </div>

                {skill.evidence_url_or_note && (
                  <p className="text-[11px] text-slate-400 bg-black/20 p-2 rounded-lg border border-white/[0.04] italic">
                    Preuve : {skill.evidence_url_or_note}
                  </p>
                )}
                {skill.verified_by && (
                  <p className="text-[10px] text-emerald-400/80">
                    Certifié par {skill.verified_by}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* TAB 5: LEAVES MANAGEMENT */}
      {activeTab === "leaves" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-white">Gestion des Congés & Absences</h3>
              <p className="text-xs text-slate-400">
                Validation des congés payés, maladies et autorisations d'absence.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setIsLeaveModalOpen(true)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-bold bg-[#0076FF] hover:bg-blue-600 text-white transition shadow-sm"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Demander un congé</span>
            </button>
          </div>

          <div className="rounded-2xl bg-[#0B132B]/80 border border-white/[0.08] overflow-hidden">
            {leaves.length === 0 ? (
              <div className="p-8 text-center text-xs text-slate-400">
                Aucune demande de congé enregistrée pour le moment.
              </div>
            ) : (
              <div className="divide-y divide-white/[0.06]">
                {leaves.map((l) => (
                  <div key={l.id} className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <strong className="text-xs text-white">{l.employee_name}</strong>
                        <span className="text-[10px] font-extrabold uppercase px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                          {l.leave_type}
                        </span>
                      </div>
                      <p className="text-xs text-slate-400">
                        Du {new Date(l.start_date).toLocaleDateString()} au {new Date(l.end_date).toLocaleDateString()} ({l.days_count} jour(s))
                        {l.reason ? ` · ${l.reason}` : ""}
                      </p>
                    </div>

                    <div className="flex items-center gap-3">
                      <span
                        className={`text-xs font-bold px-2.5 py-1 rounded-full ${
                          l.status === "approved"
                            ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                            : l.status === "rejected"
                            ? "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                            : "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                        }`}
                      >
                        {l.status === "approved" ? "Approuvé" : l.status === "rejected" ? "Refusé" : "En attente"}
                      </span>

                      {l.status === "pending" && (
                        <div className="flex items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => handleLeaveStatusUpdate(l.id, "approved")}
                            className="p-1.5 rounded-lg bg-emerald-500/20 hover:bg-emerald-500 text-emerald-300 hover:text-white transition"
                            title="Approuver"
                          >
                            <Check className="w-4 h-4" />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleLeaveStatusUpdate(l.id, "rejected")}
                            className="p-1.5 rounded-lg bg-rose-500/20 hover:bg-rose-500 text-rose-300 hover:text-white transition"
                            title="Refuser"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
        </>
      )}

      {/* LEAVE REQUEST MODAL */}
      {isLeaveModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#0B132B] border border-white/10 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-white/[0.08] pb-3">
              <h4 className="text-sm font-bold text-white">Demande de Congé / Absence</h4>
              <button
                type="button"
                onClick={() => setIsLeaveModalOpen(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateLeave} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-300 font-bold mb-1">Type de congé</label>
                <select
                  value={leaveForm.leave_type}
                  onChange={(e) => setLeaveForm((prev) => ({ ...prev, leave_type: e.target.value }))}
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-white/10 text-white"
                >
                  <option value="vacation">Congé payé / Vacances</option>
                  <option value="sickness">Maladie</option>
                  <option value="rtt">RTT / Repos compensatoire</option>
                  <option value="training">Formation</option>
                  <option value="unpaid">Congé sans solde</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-300 font-bold mb-1">Date début</label>
                  <input
                    type="date"
                    required
                    value={leaveForm.start_date}
                    onChange={(e) => setLeaveForm((prev) => ({ ...prev, start_date: e.target.value }))}
                    className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-white/10 text-white"
                  />
                </div>
                <div>
                  <label className="block text-slate-300 font-bold mb-1">Date fin</label>
                  <input
                    type="date"
                    required
                    value={leaveForm.end_date}
                    onChange={(e) => setLeaveForm((prev) => ({ ...prev, end_date: e.target.value }))}
                    className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-white/10 text-white"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-300 font-bold mb-1">Nombre de jours ouvrés</label>
                <input
                  type="number"
                  min="0.5"
                  step="0.5"
                  required
                  value={leaveForm.days_count}
                  onChange={(e) => setLeaveForm((prev) => ({ ...prev, days_count: parseFloat(e.target.value) }))}
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-white/10 text-white"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-bold mb-1">Motif / Commentaire (Optionnel)</label>
                <textarea
                  rows={2}
                  value={leaveForm.reason}
                  onChange={(e) => setLeaveForm((prev) => ({ ...prev, reason: e.target.value }))}
                  placeholder="Ex: Vacances familiales..."
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-white/10 text-white resize-none"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-white/[0.08]">
                <button
                  type="button"
                  onClick={() => setIsLeaveModalOpen(false)}
                  className="px-4 py-2 rounded-xl text-slate-400 hover:text-white font-bold"
                >
                  Annuler
                </button>
                <button
                  type="submit"
                  disabled={leaveSubmitting}
                  className="px-4 py-2 rounded-xl bg-[#0076FF] hover:bg-blue-600 text-white font-bold disabled:opacity-50"
                >
                  {leaveSubmitting ? "Envoi..." : "Soumettre la demande"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
