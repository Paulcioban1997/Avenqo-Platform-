"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch, ApiRequestError } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";
import { useSession } from "@/lib/session-context";
import {
  Users,
  UserPlus,
  CheckCircle,
  Clock,
  Briefcase,
  Shield,
  Plus,
  AlertCircle,
  X,
  Sparkles,
  Calendar,
  Check,
  ChevronRight,
  Filter,
  RefreshCw,
  Mail,
  UserCheck,
} from "lucide-react";

type Member = {
  id: string;
  first_name: string;
  last_name: string;
  email?: string;
  role: string;
  job_title: string;
  department: string | null;
  responsibilities: string[];
};

type Task = {
  id: string;
  title: string;
  priority: string;
  status: string;
  due_at: string | null;
  assignee_user_id?: string;
};

type Briefing = {
  job_title: string;
  recommendations: string[];
  today_tasks: Task[];
  open_tasks: Task[];
  responsibilities: { title: string }[];
};

export function TeamWorkspace() {
  const { locale } = useLocale();
  const fr = locale.startsWith("fr");
  const { identity } = useSession();

  const [team, setTeam] = useState<Member[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [successNotice, setSuccessNotice] = useState("");

  // MODALS
  const [isInviteModalOpen, setIsInviteModalOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("user");
  const [inviteJobTitle, setInviteJobTitle] = useState("Employé");
  const [inviteDepartment, setInviteDepartment] = useState("");
  const [inviting, setInviting] = useState(false);
  const [inviteSuccessToken, setInviteSuccessToken] = useState<string | null>(null);

  const [isTaskModalOpen, setIsTaskModalOpen] = useState(false);
  const [taskTitle, setTaskTitle] = useState("");
  const [taskAssigneeId, setTaskAssigneeId] = useState("");
  const [taskPriority, setTaskPriority] = useState("medium");
  const [creatingTask, setCreatingTask] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [teamRes, taskRes, guideRes] = await Promise.all([
        apiFetch("/api/v1/workspace/team"),
        apiFetch("/api/v1/workspace/tasks"),
        apiFetch("/api/v1/workspace/guidance"),
      ]);
      if (teamRes.ok) setTeam(await teamRes.json());
      if (taskRes.ok) setTasks(await taskRes.json());
      if (guideRes.ok) setBriefing(await guideRes.json());
      setError("");
    } catch {
      setError(fr ? "Impossible de charger l'espace équipe." : "Unable to load the team workspace.");
    } finally {
      setLoading(false);
    }
  }, [fr]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim()) return;
    setInviting(true);
    setError("");
    setSuccessNotice("");
    setInviteSuccessToken(null);

    try {
      const response = await apiFetch("/api/v1/workspace/invitations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: inviteEmail.trim(),
          role: inviteRole,
          job_title: inviteJobTitle.trim() || "Collaborateur",
          department: inviteDepartment.trim() || undefined,
        }),
      });

      if (response.ok) {
        const payload = await response.json();
        setSuccessNotice(
          fr
            ? `Invitation envoyée avec succès à ${inviteEmail}`
            : `Invitation sent successfully to ${inviteEmail}`
        );
        if (payload?.token) {
          setInviteSuccessToken(payload.token);
        }
        setInviteEmail("");
        setInviteDepartment("");
        await load();
      }
    } catch (err) {
      if (err instanceof ApiRequestError) {
        if (err.status === 409) {
          setError(
            fr
              ? "Limite d'utilisateurs de votre forfait atteinte. Améliorez votre abonnement pour inviter plus d'employés."
              : "Subscription user limit reached. Upgrade your plan to invite more employees."
          );
        } else {
          setError(err.publicMessage || (fr ? "Échec de l'envoi de l'invitation." : "Failed to send invitation."));
        }
      } else {
        setError(fr ? "Erreur de connexion au serveur." : "Server connection error.");
      }
    } finally {
      setInviting(false);
    }
  };

  const handleCreateTask = async (e: React.FormEvent) => {
    e.preventDefault();
    const assignee = taskAssigneeId || identity?.user?.id;
    if (!assignee || !taskTitle.trim()) return;
    setCreatingTask(true);
    setError("");

    try {
      const response = await apiFetch("/api/v1/workspace/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          assignee_user_id: assignee,
          title: taskTitle.trim(),
          priority: taskPriority,
        }),
      });

      if (response.ok) {
        setIsTaskModalOpen(false);
        setTaskTitle("");
        await load();
      }
    } catch (err) {
      if (err instanceof ApiRequestError) {
        setError(err.publicMessage || (fr ? "Impossible de créer la tâche." : "Failed to create task."));
      } else {
        setError(fr ? "Erreur de création de tâche." : "Task creation error.");
      }
    } finally {
      setCreatingTask(false);
    }
  };

  const handleCompleteTask = async (taskId: string) => {
    try {
      const response = await apiFetch(`/api/v1/workspace/tasks/${taskId}/complete`, {
        method: "POST",
      });
      if (response.ok) {
        setTasks((prev) =>
          prev.map((t) => (t.id === taskId ? { ...t, status: "done" } : t))
        );
      }
    } catch {
      setError(fr ? "Impossible de terminer la tâche." : "Failed to complete task.");
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-7 animate-in fade-in duration-300">
      {/* HEADER */}
      <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-slate-200 dark:border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold uppercase tracking-widest text-[#0076FF] dark:text-[#00D4FF]">
              Avenqo Team Workspace
            </span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300 font-medium">
              {team.length} {fr ? "Collaborateurs" : "Team Members"}
            </span>
          </div>
          <h1 className="mt-1 text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">
            {fr ? "Équipe & Responsabilités" : "Team & Responsibilities"}
          </h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            {fr
              ? "Gestion des invitations, rôles, permissions et tâches assignées."
              : "Employee invitations, roles, permissions, and assigned tasks."}
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={() => void load()}
            disabled={loading}
            className="p-2.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 hover:bg-slate-50 transition"
            title={fr ? "Actualiser" : "Refresh"}
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>
          <button
            onClick={() => setIsTaskModalOpen(true)}
            className="flex items-center gap-2 px-3.5 py-2.5 text-xs font-bold rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200 hover:bg-slate-50 transition"
          >
            <Plus className="w-4 h-4" />
            <span>{fr ? "Nouvelle tâche" : "New Task"}</span>
          </button>
          <button
            id="invite-member-button"
            onClick={() => setIsInviteModalOpen(true)}
            className="flex items-center gap-2 px-4 py-2.5 text-xs font-bold rounded-xl bg-gradient-to-r from-[#0076FF] to-[#00D4FF] text-white shadow-md hover:shadow-lg transition"
          >
            <UserPlus className="w-4 h-4" />
            <span>{fr ? "Inviter un collaborateur" : "Invite Employee"}</span>
          </button>
        </div>
      </header>

      {error && (
        <div role="alert" className="flex items-center gap-2.5 p-4 rounded-xl border border-rose-200 bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {successNotice && (
        <div role="status" className="flex items-center gap-2.5 p-4 rounded-xl border border-emerald-200 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 text-sm">
          <CheckCircle className="w-4 h-4 shrink-0" />
          <span>{successNotice}</span>
        </div>
      )}

      {/* BRIEFING IA */}
      {briefing && (
        <section className="rounded-3xl border border-blue-100 dark:border-blue-900/40 bg-gradient-to-r from-blue-50/60 to-white dark:from-blue-950/20 dark:to-[#0B132B] p-6 shadow-xs space-y-3">
          <div className="flex items-center gap-2 text-blue-900 dark:text-blue-200 font-bold text-sm">
            <Sparkles className="w-4 h-4 text-[#0076FF]" />
            <span>{fr ? `Priorités du jour — ${briefing.job_title}` : `Today's Priorities — ${briefing.job_title}`}</span>
          </div>
          <ul className="space-y-1.5 text-xs sm:text-sm text-slate-700 dark:text-slate-300">
            {briefing.recommendations.map((item, idx) => (
              <li key={idx} className="flex items-center gap-2">
                <ChevronRight className="w-3.5 h-3.5 text-[#0076FF] shrink-0" />
                <span>{item}</span>
              </li>
            ))}
            {briefing.recommendations.length === 0 && (
              <li className="text-slate-500 italic">
                {fr ? "Aucune alerte opérationnelle en cours." : "No current operational alerts."}
              </li>
            )}
          </ul>
        </section>
      )}

      {/* GRID: TEAM & TASKS */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        {/* TEAM MEMBERS */}
        <section className="rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B132B] p-6 shadow-xs space-y-5">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800">
            <div className="flex items-center gap-2.5 font-bold text-slate-900 dark:text-white text-base">
              <Users className="w-5 h-5 text-[#0076FF]" />
              <span>{fr ? "Membres de l'entreprise" : "Team Members"}</span>
            </div>
            <span className="text-xs px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-mono">
              {team.length}
            </span>
          </div>

          <div className="divide-y divide-slate-100 dark:divide-slate-800/80">
            {team.map((member) => (
              <div key={member.id} className="py-3.5 flex items-center justify-between gap-3">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-blue-100 to-cyan-100 dark:from-blue-950 dark:to-slate-800 text-[#0076FF] dark:text-[#00D4FF] font-bold text-xs flex items-center justify-center shrink-0">
                    {`${member.first_name?.[0] || ""}${member.last_name?.[0] || ""}`.toUpperCase() || "U"}
                  </div>
                  <div className="min-w-0">
                    <p className="font-bold text-slate-900 dark:text-white text-sm truncate">
                      {member.first_name} {member.last_name}
                    </p>
                    <p className="text-xs text-slate-500 dark:text-slate-400 truncate mt-0.5">
                      {member.job_title} · {member.department || (fr ? "Général" : "General")}
                    </p>
                  </div>
                </div>

                <div className="shrink-0 flex items-center gap-2">
                  <span className="px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-[10px] font-bold text-slate-700 dark:text-slate-300 uppercase">
                    {member.role}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* TASKS LIST */}
        <section className="rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B132B] p-6 shadow-xs space-y-5">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800">
            <div className="flex items-center gap-2.5 font-bold text-slate-900 dark:text-white text-base">
              <Briefcase className="w-5 h-5 text-purple-600" />
              <span>{fr ? "Missions & Tâches assignées" : "Assigned Tasks"}</span>
            </div>
            <span className="text-xs px-2.5 py-1 rounded-full bg-purple-50 dark:bg-purple-950 text-purple-700 dark:text-purple-300 font-mono">
              {tasks.filter((t) => t.status !== "done").length} {fr ? "en cours" : "open"}
            </span>
          </div>

          {tasks.length === 0 && !loading && (
            <div className="py-8 text-center text-xs text-slate-400">
              {fr ? "Aucune tâche assignée pour le moment." : "No tasks assigned yet."}
            </div>
          )}

          <div className="divide-y divide-slate-100 dark:divide-slate-800/80">
            {tasks.map((task) => {
              const isDone = task.status === "done";
              return (
                <div key={task.id} className="py-3 flex items-center justify-between gap-3">
                  <div className="min-w-0 space-y-1">
                    <p className={`text-sm font-semibold truncate ${isDone ? "line-through text-slate-400" : "text-slate-900 dark:text-white"}`}>
                      {task.title}
                    </p>
                    <div className="flex items-center gap-2 text-[10px]">
                      <span className={`px-2 py-0.5 rounded-md font-bold uppercase ${
                        task.priority === "high"
                          ? "bg-rose-100 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300"
                          : "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300"
                      }`}>
                        {task.priority}
                      </span>
                    </div>
                  </div>

                  {!isDone ? (
                    <button
                      onClick={() => void handleCompleteTask(task.id)}
                      className="px-3 py-1.5 rounded-xl text-xs font-bold bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300 hover:bg-emerald-100 transition shrink-0"
                    >
                      {fr ? "Terminer" : "Complete"}
                    </button>
                  ) : (
                    <span className="text-emerald-600 flex items-center gap-1 text-xs shrink-0">
                      <Check className="w-4 h-4" />
                      <span>{fr ? "Terminée" : "Done"}</span>
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      </div>

      {/* INVITE MODAL */}
      {isInviteModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-200">
          <div className="w-full max-w-lg rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B132B] shadow-2xl p-6 sm:p-7 space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800">
              <div className="flex items-center gap-2.5">
                <div className="p-2.5 rounded-xl bg-blue-100 dark:bg-blue-950 text-[#0076FF]">
                  <UserPlus className="w-5 h-5" />
                </div>
                <h3 className="font-extrabold text-slate-900 dark:text-white text-lg">
                  {fr ? "Inviter un collaborateur" : "Invite Employee"}
                </h3>
              </div>
              <button
                onClick={() => setIsInviteModalOpen(false)}
                className="p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-xl"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleInvite} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1.5">
                  {fr ? "Courriel professionnel" : "Work Email"}
                </label>
                <input
                  type="email"
                  required
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  placeholder="collaborateur@votre-entreprise.ca"
                  className="w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1.5">
                    {fr ? "Rôle" : "Role"}
                  </label>
                  <select
                    value={inviteRole}
                    onChange={(e) => setInviteRole(e.target.value)}
                    className="w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm"
                  >
                    <option value="user">{fr ? "Employé standard" : "Standard User"}</option>
                    <option value="manager">{fr ? "Manager" : "Manager"}</option>
                    <option value="admin">{fr ? "Administrateur" : "Admin"}</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1.5">
                    {fr ? "Titre de poste" : "Job Title"}
                  </label>
                  <input
                    type="text"
                    value={inviteJobTitle}
                    onChange={(e) => setInviteJobTitle(e.target.value)}
                    placeholder={fr ? "ex: Réceptionniste" : "e.g. Receptionist"}
                    className="w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1.5">
                  {fr ? "Département (optionnel)" : "Department (optional)"}
                </label>
                <input
                  type="text"
                  value={inviteDepartment}
                  onChange={(e) => setInviteDepartment(e.target.value)}
                  placeholder={fr ? "ex: Ventes, Clinique, Support" : "e.g. Sales, Clinic, Support"}
                  className="w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm"
                />
              </div>

              {inviteSuccessToken && (
                <div className="p-3.5 rounded-xl bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-900 text-xs space-y-1">
                  <p className="font-bold text-blue-900 dark:text-blue-200">
                    {fr ? "Jeton d'invitation généré (Sandbox) :" : "Invitation Token Generated (Sandbox):"}
                  </p>
                  <p className="font-mono break-all text-blue-700 dark:text-blue-300 select-all">
                    {inviteSuccessToken}
                  </p>
                </div>
              )}

              <div className="flex justify-end gap-3 pt-3 border-t border-slate-100 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsInviteModalOpen(false)}
                  className="px-4 py-2 text-xs font-semibold rounded-xl text-slate-600 dark:text-slate-400"
                >
                  {fr ? "Fermer" : "Close"}
                </button>
                <button
                  type="submit"
                  disabled={inviting}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#0076FF] text-white font-bold text-xs shadow-md"
                >
                  {inviting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Mail className="w-4 h-4" />}
                  <span>{fr ? "Envoyer l'invitation" : "Send Invitation"}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* CREATE TASK MODAL */}
      {isTaskModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-200">
          <div className="w-full max-w-lg rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B132B] shadow-2xl p-6 sm:p-7 space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800">
              <div className="flex items-center gap-2.5">
                <div className="p-2.5 rounded-xl bg-purple-100 dark:bg-purple-950 text-purple-600">
                  <Briefcase className="w-5 h-5" />
                </div>
                <h3 className="font-extrabold text-slate-900 dark:text-white text-lg">
                  {fr ? "Créer une tâche" : "Create Task"}
                </h3>
              </div>
              <button
                onClick={() => setIsTaskModalOpen(false)}
                className="p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-xl"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateTask} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1.5">
                  {fr ? "Titre de la tâche" : "Task Title"}
                </label>
                <input
                  type="text"
                  required
                  value={taskTitle}
                  onChange={(e) => setTaskTitle(e.target.value)}
                  placeholder={fr ? "ex: Rappeler le client pour confirmation" : "e.g. Call client for confirmation"}
                  className="w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1.5">
                    {fr ? "Assigner à" : "Assign to"}
                  </label>
                  <select
                    value={taskAssigneeId}
                    onChange={(e) => setTaskAssigneeId(e.target.value)}
                    className="w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm"
                  >
                    <option value="">{fr ? "Moi-même (Par défaut)" : "Myself (Default)"}</option>
                    {team.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.first_name} {m.last_name} ({m.job_title})
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1.5">
                    {fr ? "Priorité" : "Priority"}
                  </label>
                  <select
                    value={taskPriority}
                    onChange={(e) => setTaskPriority(e.target.value)}
                    className="w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm"
                  >
                    <option value="low">{fr ? "Basse" : "Low"}</option>
                    <option value="medium">{fr ? "Moyenne" : "Medium"}</option>
                    <option value="high">{fr ? "Haute / Urgente" : "High / Urgent"}</option>
                  </select>
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-3 border-t border-slate-100 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsTaskModalOpen(false)}
                  className="px-4 py-2 text-xs font-semibold rounded-xl text-slate-600 dark:text-slate-400"
                >
                  {fr ? "Annuler" : "Cancel"}
                </button>
                <button
                  type="submit"
                  disabled={creatingTask}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-purple-600 text-white font-bold text-xs shadow-md"
                >
                  {creatingTask ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                  <span>{fr ? "Créer la mission" : "Create Task"}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
