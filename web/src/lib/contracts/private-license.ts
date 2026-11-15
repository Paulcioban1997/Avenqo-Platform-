/** Ordinary SaaS plans do not require the private-server license. */
export function privateLicenseRequiredForPlan(planName: string | null | undefined): boolean {
  const plan = (planName ?? "").normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
  if (!plan.trim()) return false;
  return /\b(private[\s-]?server|on[\s-]?prem|dedicated[\s-]?server|serveur prive|licence privee)\b/.test(plan);
}
