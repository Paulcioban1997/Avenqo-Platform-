import { AppShell } from "@/components/shell/app-shell";
import { ModulesView } from "@/components/common/modules-view";

export const metadata = { title: "Mes modules | Avenqo", robots: { index: false, follow: false } };
export default function ModulesPage() { return <AppShell><ModulesView /></AppShell>; }
