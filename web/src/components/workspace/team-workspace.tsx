"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";
import { useSession } from "@/lib/session-context";

type Member = { id: string; first_name: string; last_name: string; role: string; job_title: string; department: string | null; responsibilities: string[] };
type Task = { id: string; title: string; priority: string; status: string; due_at: string | null };
type Briefing = { job_title: string; recommendations: string[]; today_tasks: Task[]; open_tasks: Task[]; responsibilities: { title: string }[] };

export function TeamWorkspace() {
  const { locale } = useLocale();
  const fr = locale.startsWith("fr");
  const { identity } = useSession();
  const [team, setTeam] = useState<Member[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [title, setTitle] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
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
      setError(fr ? "Impossible de charger l’espace équipe." : "Unable to load the team workspace.");
    }
  }, [fr]);

  useEffect(() => { void load(); }, [load]);

  const createTask = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!identity?.user.id || !title.trim()) return;
    const response = await apiFetch("/api/v1/workspace/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ assignee_user_id: identity.user.id, title }),
    });
    if (!response.ok) setError(fr ? "Tâche refusée." : "Task rejected.");
    else { setTitle(""); await load(); }
  };

  const invite = async (event: React.FormEvent) => {
    event.preventDefault();
    const response = await apiFetch("/api/v1/workspace/invitations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: inviteEmail, job_title: "Employee" }),
    });
    if (response.status === 409) setError(fr ? "Limite d’utilisateurs du forfait atteinte." : "Plan user limit reached.");
    else if (!response.ok) setError(fr ? "Invitation refusée." : "Invitation rejected.");
    else { setInviteEmail(""); await load(); }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <h1 className="text-3xl font-bold">{fr ? "Équipe et responsabilités" : "Team and responsibilities"}</h1>
      {error && <p role="alert" className="text-sm text-rose-500">{error}</p>}
      {briefing && (
        <section className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-[#0B132B]">
          <h2 className="font-semibold">{fr ? "Priorités du jour" : "Today’s priorities"}</h2>
          <p className="mt-1 text-sm text-slate-500">{briefing.job_title}</p>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm">
            {briefing.recommendations.map((item) => <li key={item}>{item}</li>)}
            {briefing.recommendations.length === 0 && <li>{fr ? "Aucune alerte en cours." : "No current alerts."}</li>}
          </ul>
        </section>
      )}
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-[#0B132B]">
          <h2 className="font-semibold">{fr ? "Équipe" : "Team"}</h2>
          <ul className="mt-3 divide-y divide-slate-200 text-sm dark:divide-white/10">
            {team.map((member) => (
              <li key={member.id} className="py-3">
                <p className="font-medium">{member.first_name} {member.last_name}</p>
                <p className="text-slate-500">{member.job_title} · {member.role}{member.department ? ` · ${member.department}` : ""}</p>
              </li>
            ))}
          </ul>
          <form onSubmit={invite} className="mt-4 flex gap-2">
            <input className="flex-1 rounded-xl border bg-transparent px-3 py-2" type="email" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} placeholder={fr ? "Courriel" : "Email"} required />
            <button className="rounded-xl bg-blue-600 px-4 text-sm text-white">{fr ? "Inviter" : "Invite"}</button>
          </form>
        </section>
        <section className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-[#0B132B]">
          <h2 className="font-semibold">{fr ? "Tâches" : "Tasks"}</h2>
          <form onSubmit={createTask} className="mt-3 flex gap-2">
            <input className="flex-1 rounded-xl border bg-transparent px-3 py-2" value={title} onChange={(e) => setTitle(e.target.value)} placeholder={fr ? "Nouvelle tâche" : "New task"} />
            <button className="rounded-xl bg-blue-600 px-4 text-sm text-white">{fr ? "Ajouter" : "Add"}</button>
          </form>
          <ul className="mt-4 divide-y divide-slate-200 text-sm dark:divide-white/10">
            {tasks.map((task) => (
              <li key={task.id} className="flex items-center justify-between py-3">
                <span>{task.title}</span>
                {task.status !== "done" && (
                  <button className="text-cyan-600" onClick={() => void apiFetch(`/api/v1/workspace/tasks/${task.id}/complete`, { method: "POST" }).then(load)}>
                    {fr ? "Terminer" : "Done"}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
