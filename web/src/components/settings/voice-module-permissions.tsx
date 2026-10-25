"use client";

import { useEffect, useState } from "react";
import { useLocale } from "@/lib/i18n/locale-context";
import { VOICE_PERMISSIONS_COPY } from "@/lib/i18n/voice-permissions-copy";

interface VoiceActionGrant {
  action_code: string;
  granted: boolean;
  locked: boolean;
  tools: string[];
}
interface VoiceModuleGrant {
  module_code: string;
  active: boolean;
  locked: boolean;
  actions: VoiceActionGrant[];
}
interface VoiceModulePermissions {
  modules: VoiceModuleGrant[];
}

export function VoiceModulePermissionsSection({
  tenantId,
  canManage,
}: {
  tenantId: string | undefined;
  canManage: boolean;
}) {
  const { locale } = useLocale();
  const copy = VOICE_PERMISSIONS_COPY[locale];
  const [data, setData] = useState<VoiceModulePermissions | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!tenantId || !canManage) return;
    const controller = new AbortController();
    queueMicrotask(async () => {
      try {
        const response = await fetch("/api/v1/voice/module-permissions", {
          signal: controller.signal,
          cache: "no-store",
        });
        if (response.ok && !controller.signal.aborted) {
          const payload = await response.json();
          if (Array.isArray(payload?.modules)) setData(payload);
        }
      } catch {
        /* keep last known state */
      }
    });
    return () => controller.abort();
  }, [tenantId, canManage]);

  async function toggle(module_code: string, action_code: string, granted: boolean) {
    setBusy(true);
    try {
      const response = await fetch("/api/v1/voice/module-permissions", {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-Requested-With": "avenqo-web" },
        body: JSON.stringify({ grants: [{ module_code, action_code, granted }] }),
      });
      if (response.ok) {
        const payload = await response.json();
        if (Array.isArray(payload?.modules)) setData(payload);
      }
    } finally {
      setBusy(false);
    }
  }

  if (!canManage || !Array.isArray(data?.modules)) return null;
  return (
    <section className="space-y-3 border-t border-slate-200 pt-4 text-sm dark:border-white/10">
      <h2 className="font-semibold">{copy.title}</h2>
      <p className="text-xs text-slate-500">{copy.description}</p>
      {data.modules
        .filter((module) => module.actions.length > 0)
        .map((module) => (
          <div key={module.module_code} className="space-y-1">
            <div className="font-medium">
              {module.module_code}
              {module.locked ? ` · ${copy.locked}` : ""}
            </div>
            {module.actions.map((action) => (
              <label key={action.action_code} className="flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  value={action.action_code}
                  disabled={busy || action.locked}
                  checked={action.granted}
                  onChange={(event) => void toggle(module.module_code, action.action_code, event.target.checked)}
                />
                <span>
                  {action.action_code}
                  {action.locked ? ` (${copy.moduleOff})` : ""}
                </span>
              </label>
            ))}
          </div>
        ))}
    </section>
  );
}
