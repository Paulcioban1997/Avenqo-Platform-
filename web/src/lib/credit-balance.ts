export interface CreditBalancePayload {
  monthly_allocation?: number;
  monthly_included?: number;
  monthly_remaining?: number;
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
  const used = limit !== null && remaining !== null
    ? Math.max(0, limit - remaining)
    : null;

  return { remaining, limit, used };
}
