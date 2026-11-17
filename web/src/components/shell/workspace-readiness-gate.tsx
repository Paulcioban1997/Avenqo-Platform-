"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";
import { getContractsUi } from "@/lib/i18n/contracts-ui-copy";

const REACHABLE = ["/settings", "/billing", "/onboarding", "/team", "/employees", "/legal", "/support"];

type Access = {
  workspace_open?: boolean;
  legacy_session?: boolean;
  invited_member?: boolean;
  contracts_path?: string;
  checkout_path?: string;
};

export function WorkspaceReadinessGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/";
  const { locale } = useLocale();
  const copy = getContractsUi(locale).copy;
  const [access, setAccess] = useState<Access | null>(null);
  const [failed, setFailed] = useState(false);
  const reachable = REACHABLE.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));

  useEffect(() => {
    let cancelled = false;
    apiFetch("/api/v1/onboarding/workspace-access")
      .then(async (response) => {
        if (!response.ok) {
          if (!cancelled) setFailed(true);
          return;
        }
        const payload = await response.json();
        if (!cancelled) setAccess(payload);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  if (reachable || failed || !access || access.workspace_open || access.invited_member) {
    return <>{children}</>;
  }

  return (
    <section className="mx-auto max-w-xl space-y-4 rounded-2xl border border-slate-200 bg-white p-6 dark:border-white/10 dark:bg-[#0B132B]">
      <h2 className="text-lg font-bold text-slate-900 dark:text-white">{copy.gateTitle}</h2>
      <p className="text-sm leading-relaxed text-slate-700 dark:text-slate-200">{copy.gateBody}</p>
      <div className="flex flex-wrap gap-2">
        <Link href={access.contracts_path || "/settings/contracts"} className="inline-flex h-9 items-center rounded-xl bg-[#0076FF] px-3 text-xs font-semibold text-white">
          {copy.gateContracts}
        </Link>
        <Link href={access.checkout_path || "/onboarding/checkout"} className="inline-flex h-9 items-center rounded-xl border border-slate-300 px-3 text-xs font-semibold text-slate-800 dark:border-white/15 dark:text-white">
          {copy.gateCheckout}
        </Link>
      </div>
    </section>
  );
}
