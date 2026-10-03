"use client";

import Link from "next/link";
import { Sparkles } from "lucide-react";

interface CreditMeterProps {
  remaining: number | null;
  limit: number | null;
  label: string;
  upgradeLabel: string;
  error?: string;
  loadingLabel?: string;
  retryLabel?: string;
  onRetry?: () => void;
}

export function CreditMeter({
  remaining,
  limit,
  label,
  upgradeLabel, error, loadingLabel = "…", retryLabel, onRetry,
}: CreditMeterProps) {
  const percentage = remaining !== null && limit
    ? Math.min(100, Math.round((remaining / limit) * 100))
    : null;

  return (
    <div className="p-3 rounded-2xl bg-white dark:bg-[#111D3D] border border-slate-200/80 dark:border-white/[0.08] shadow-2xs">
      <div className="flex items-center justify-between text-xs mb-1.5">
        <div className="flex items-center gap-1.5 font-bold text-slate-900 dark:text-[#F4F7FB]">
          <Sparkles className="w-3.5 h-3.5 text-[#0076FF]" />
          <span>{label}</span>
        </div>
        <span className="text-[11px] font-semibold text-slate-500 dark:text-[#94A3B8]">
          {percentage === null || error ? loadingLabel : `${percentage}%`}
        </span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-slate-100 dark:bg-white/[0.08] overflow-hidden mb-1.5">
        <div
          className="h-full rounded-full bg-gradient-to-r from-[#0076FF] to-[#00D4FF] transition-all duration-300"
          style={{ width: `${percentage ?? 0}%` }}
        />
      </div>
      {error && <div role="alert">{error} <button onClick={onRetry}>{retryLabel}</button></div>}
      <div className="flex items-center justify-between text-[10px] text-slate-400 dark:text-slate-500">
        <span>
          {remaining === null || limit === null
            ? "—"
            : `${remaining.toLocaleString()} / ${limit.toLocaleString()}`}
        </span>
        <Link href="/pricing" className="text-[#0076FF] hover:underline font-medium">
          {upgradeLabel}
        </Link>
      </div>
    </div>
  );
}
