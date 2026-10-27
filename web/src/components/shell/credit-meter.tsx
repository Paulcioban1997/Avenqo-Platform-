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
  upgradeLabel,
  error,
  loadingLabel = "…",
  retryLabel,
  onRetry,
}: CreditMeterProps) {
  let percentageDisplay: string | null = null;
  let barWidth = 0;

  if (remaining !== null && limit && limit > 0) {
    const rawPct = (remaining / limit) * 100;
    barWidth = Math.min(100, Math.max(0, rawPct));

    if (remaining === limit) {
      percentageDisplay = "100 %";
    } else if (remaining === 0) {
      percentageDisplay = "0 %";
    } else if (rawPct > 99 && rawPct < 100) {
      percentageDisplay = `${rawPct.toFixed(2)} %`;
    } else if (rawPct > 0 && rawPct < 1) {
      percentageDisplay = `${rawPct.toFixed(2)} %`;
    } else {
      percentageDisplay = `${rawPct.toFixed(1)} %`;
    }
  }

  const used = remaining !== null && limit !== null ? Math.max(0, limit - remaining) : null;

  return (
    <div className="p-3 rounded-2xl bg-white dark:bg-[#111D3D] border border-slate-200/80 dark:border-white/[0.08] shadow-2xs">
      <div className="flex items-center justify-between text-xs mb-1.5">
        <div className="flex items-center gap-1.5 font-bold text-slate-900 dark:text-[#F4F7FB]">
          <Sparkles className="w-3.5 h-3.5 text-[#0076FF]" />
          <span>{label}</span>
        </div>
        <span
          className="text-[11px] font-mono font-bold text-[#0076FF] dark:text-[#00D4FF]"
          title={used !== null ? `Utilisés : ${used.toLocaleString()} crédits` : undefined}
        >
          {percentageDisplay === null || error ? loadingLabel : `${percentageDisplay} restants`}
        </span>
      </div>

      <div className="h-1.5 w-full rounded-full bg-slate-100 dark:bg-white/[0.08] overflow-hidden mb-1.5">
        <div
          className="h-full rounded-full bg-gradient-to-r from-[#0076FF] to-[#00D4FF] transition-all duration-300"
          style={{ width: `${barWidth}%` }}
        />
      </div>

      {error && (
        <div role="alert" className="text-[10px] text-rose-500 my-1 flex items-center justify-between">
          <span>{error}</span>
          {onRetry && (
            <button onClick={onRetry} className="underline text-blue-500">
              {retryLabel || "Réessayer"}
            </button>
          )}
        </div>
      )}

      <div className="flex items-center justify-between text-[10px] text-slate-400 dark:text-slate-500">
        <span className="font-mono">
          {remaining === null || limit === null
            ? "—"
            : `${remaining.toLocaleString()} / ${limit.toLocaleString()}`}
        </span>
        <Link href="/billing" className="text-[#0076FF] hover:underline font-semibold">
          {upgradeLabel}
        </Link>
      </div>
    </div>
  );
}
