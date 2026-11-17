import type { Metadata } from "next";
import { Suspense } from "react";
import { JoinWorkspaceView } from "@/components/auth/join-workspace-view";

export const metadata: Metadata = {
  title: "Rejoindre l'entreprise",
  description: "Acceptez une invitation Avenqo et créez votre accès.",
  robots: { index: false, follow: false },
};

export default function JoinPage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-[#070B16]" />}>
      <JoinWorkspaceView />
    </Suspense>
  );
}
