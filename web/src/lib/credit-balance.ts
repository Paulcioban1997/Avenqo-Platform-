export interface CreditBalancePayload {
  monthly_allocation?: number;
  monthly_included?: number;
  monthly_remaining?: number;
  monthly_used?: number;
  total_remaining?: number;
}

export interface CreditBalanceViewModel {
  remaining: number | null;
  limit: number | null;
  used: number | null;
}

export function creditBalanceViewModel(
  balance: CreditBalancePayload,
): CreditBalanceViewModel {
  const limit = balance.monthly_included ?? balance.monthly_allocation ?? null;
  const remaining = balance.monthly_remaining ?? balance.total_remaining ?? null;
  const used = balance.monthly_used ?? (limit !== null && balance.monthly_remaining !== undefined
    ? Math.max(0, limit - balance.monthly_remaining)
    : null);

  return { remaining, limit, used };
}
