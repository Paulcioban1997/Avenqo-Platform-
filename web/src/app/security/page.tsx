import { AppShell } from "@/components/shell/app-shell";
import { SecurityView } from "@/components/security/security-view";

export const metadata = { title: "Centre de sécurité | Avenqo", robots: { index: false, follow: false } };
export default function SecurityPage() { return <AppShell><SecurityView /></AppShell>; }
