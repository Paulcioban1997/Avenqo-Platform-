export interface CreditBalancePayload {
  billing_period?: string;
  purchased_total_available?: number;
  total_available?: number;
  monthly_allocation?: number;
  monthly_included?: number;
  monthly_remaining?: number;
  monthly_used?: number;
  total_remaining?: number;
  purchased_remaining?: number;
}

export interface CreditBalanceViewModel {
  remaining: number | null;
  limit: number | null;
  used: number | null;
}

export function creditBalanceViewModel(
  balance: CreditBalancePayload,
): CreditBalanceViewModel {
  const monthlyLimit = balance.monthly_included ?? balance.monthly_allocation ?? null;
  const limit = monthlyLimit === null ? null : monthlyLimit + (balance.purchased_remaining ?? 0);
  const remaining = balance.total_remaining ?? balance.monthly_remaining ?? null;
  const used = balance.monthly_used ?? (limit !== null && balance.monthly_remaining !== undefined
    ? Math.max(0, (monthlyLimit ?? 0) - balance.monthly_remaining)
    : null);

  return { remaining, limit, used };
}
