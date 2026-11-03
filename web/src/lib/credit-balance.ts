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
  monthlyAllocation: number | null;
  monthlyRemaining: number | null;
  monthlyUsed: number | null;
  purchasedRemaining: number;
}

export function creditBalanceViewModel(
  balance: CreditBalancePayload,
): CreditBalanceViewModel {
  const monthlyAllocation = balance.monthly_included ?? balance.monthly_allocation ?? null;
  const purchasedRemaining = balance.purchased_remaining ?? balance.purchased_total_available ?? 0;
  const limit = monthlyAllocation === null ? null : monthlyAllocation + purchasedRemaining;
  const remaining = balance.total_remaining ?? balance.monthly_remaining ?? null;
  const monthlyUsed = balance.monthly_used ?? (monthlyAllocation !== null && balance.monthly_remaining !== undefined
    ? Math.max(0, (monthlyAllocation ?? 0) - balance.monthly_remaining)
    : null);
  const monthlyRemaining = balance.monthly_remaining ?? (monthlyAllocation !== null && monthlyUsed !== null
    ? Math.max(0, monthlyAllocation - monthlyUsed)
    : null);
  const used = monthlyUsed;

  const result = {
    remaining,
    limit,
    used,
  } as CreditBalanceViewModel;

  Object.defineProperties(result, {
    monthlyAllocation: { value: monthlyAllocation, enumerable: false, writable: true, configurable: true },
    monthlyRemaining: { value: monthlyRemaining, enumerable: false, writable: true, configurable: true },
    monthlyUsed: { value: monthlyUsed, enumerable: false, writable: true, configurable: true },
    purchasedRemaining: { value: purchasedRemaining, enumerable: false, writable: true, configurable: true },
  });

  return result;
}
