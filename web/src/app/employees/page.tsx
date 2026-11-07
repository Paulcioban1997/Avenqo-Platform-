import { AppShell } from "@/components/shell/app-shell";
import { TeamWorkspace } from "@/components/workspace/team-workspace";
import type { Metadata } from "next";

export const metadata: Metadata = { title: "Équipe | Avenqo", robots: { index: false, follow: false } };

export default function EmployeesPage() {
  return (
    <AppShell>
      <TeamWorkspace />
    </AppShell>
  );
}
