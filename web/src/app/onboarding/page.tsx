"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api-request";
import { getAuthHeaders } from "@/lib/api-headers";

export default function OnboardingRootPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function routeToCurrentStep() {
      try {
        const headers = getAuthHeaders();
        const res = await apiFetch("/api/v1/onboarding/state", { headers });
        if (res.ok) {
          const data = await res.json();
          if (data.is_completed || data.status === "completed") {
            router.replace("/dashboard");
            return;
          }

          const step = data.current_step || "company";
          const validSteps = [
            "company",
            "modules",
            "design",
            "preview",
            "contracts",
            "subscription",
            "checkout",
            "complete",
          ];
          const targetStep = validSteps.includes(step) ? step : "company";
          router.replace(`/onboarding/${targetStep}`);
        } else {
          router.replace("/onboarding/company");
        }
      } catch (err) {
        console.error("Erreur de routage onboarding:", err);
        router.replace("/onboarding/company");
      }
    }

    void routeToCurrentStep();
  }, [router]);

  return (
    <div className="min-h-screen bg-[#060B13] flex items-center justify-center text-slate-400">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-[#0076FF] border-t-transparent rounded-full animate-spin" />
        <span className="text-xs font-semibold">Préparation de votre parcours Avenqo…</span>
      </div>
    </div>
  );
}
