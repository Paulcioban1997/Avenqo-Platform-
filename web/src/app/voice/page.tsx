"use client";

import { AppShell } from "@/components/shell/app-shell";
import { VoiceModuleView } from "@/components/settings/voice-module-view";

export default function VoicePage() {
  return (
    <AppShell>
      <main className="mx-auto w-full max-w-5xl px-5 py-8 sm:px-8">
        <VoiceModuleView />
      </main>
    </AppShell>
  );
}
