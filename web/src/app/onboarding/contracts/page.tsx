"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { OnboardingWizardLayout } from "@/components/onboarding/onboarding-wizard-layout";
import { getAuthHeaders } from "@/lib/api-headers";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";
import { getOnboardingCopy } from "@/lib/i18n/onboarding-multistep-copy";
import { getContractsUi } from "@/lib/i18n/contracts-ui-copy";

type ContractRow = {
  contract_type: string;
  title: string;
  version: string;
  status: string;
  approval_status?: string;
  signable?: boolean;
};

type Access = {
  saas_accepted?: boolean;
  private_license_required?: boolean;
  stripe_confirmed?: boolean;
};

function reviewed(row: ContractRow) {
  const approval = (row.approval_status || "").toUpperCase();
  return approval.includes("LEGAL_REVIEW") || approval === "UNDER_REVIEW" || approval.startsWith("UNDER_REVIEW");
}

export default function OnboardingContractsPage() {
  const router = useRouter();
  const { locale } = useLocale();
  const copy = getOnboardingCopy(locale);
  const contractsCopy = getContractsUi(locale).copy;
  const [loading, setLoading] = useState(true);
  const [saveStatus, setSaveStatus] = useState<"saving" | "saved" | "idle">("idle");
  const [rows, setRows] = useState<ContractRow[]>([]);
  const [access, setAccess] = useState<Access>({});

  useEffect(() => {
    async function load() {
      try {
        const headers = getAuthHeaders();
        const [contractsRes, accessRes] = await Promise.all([
          apiFetch("/api/v1/contracts", { headers }),
          apiFetch("/api/v1/onboarding/workspace-access", { headers }),
        ]);
        if (contractsRes.ok) setRows(await contractsRes.json());
        if (accessRes.ok) setAccess(await accessRes.json());
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, []);

  const downloadPdf = async (contractType: string) => {
    const response = await apiFetch(`/api/v1/contracts/${contractType}/download`, { headers: getAuthHeaders() });
    const bytes = await response.arrayBuffer();
    const blob = new Blob([bytes], { type: "application/pdf" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${contractType}.pdf`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const continueNext = async () => {
    if (!access.saas_accepted) return;
    setSaveStatus("saving");
    try {
      const headers = getAuthHeaders();
      await apiFetch("/api/v1/onboarding/step/contracts", {
        method: "PUT",
        headers,
        body: JSON.stringify({ accepted_contract_types: [] }),
      });
      setSaveStatus("saved");
      router.push(access.stripe_confirmed ? "/onboarding/complete" : "/onboarding/subscription");
    } catch {
      setSaveStatus("idle");
    }
  };

  if (loading) {
    return <div className="flex min-h-screen items-center justify-center bg-[#060B13] text-slate-400">{contractsCopy.pdfLoading}</div>;
  }

  return (
    <OnboardingWizardLayout
      currentStepIndex={5}
      title={copy.contracts.title}
      subtitle={copy.contracts.subtitle}
      onNext={() => void continueNext()}
      nextLabel={copy.navigation.continue}
      isNextDisabled={!access.saas_accepted}
      saveStatus={saveStatus}
    >
      <div className="space-y-4">
        <p className="text-sm text-slate-300">{contractsCopy.gateBody}</p>
        <p className="text-xs text-slate-400">{contractsCopy.optionalSaas}</p>
        {rows.map((row) => (
          <article key={row.contract_type} className="rounded-2xl border border-white/10 bg-[#0B132B] p-4">
            <h3 className="text-sm font-bold text-white">{row.title}</h3>
            <p className="mt-1 text-xs text-slate-400">{contractsCopy.versionLabel} {row.version}</p>
            <p className="mt-2 text-xs text-amber-200">
              {reviewed(row) ? contractsCopy.legalReviewBanner : contractsCopy.approvalNotFinal}
            </p>
            {reviewed(row) ? (
              <p className="mt-1 text-xs text-amber-100/90">{contractsCopy.legalReviewExplain}</p>
            ) : null}
            <div className="mt-3 flex flex-wrap gap-2">
              <Link href="/settings/contracts" className="rounded-lg border border-white/15 px-3 py-1.5 text-xs text-white">{contractsCopy.consult}</Link>
              <button type="button" onClick={() => void downloadPdf(row.contract_type)} className="rounded-lg border border-white/15 px-3 py-1.5 text-xs text-white">{contractsCopy.download}</button>
              {row.signable && !reviewed(row) ? (
                <Link href="/settings/contracts" className="rounded-lg bg-[#0076FF] px-3 py-1.5 text-xs text-white">{contractsCopy.sign}</Link>
              ) : null}
            </div>
          </article>
        ))}
      </div>
    </OnboardingWizardLayout>
  );
}
