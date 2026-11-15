"use client";

import React from "react";

export type StepState = "completed" | "current" | "blocked" | "upcoming";

export interface CompactStep {
  id: string;
  label: string;
  state: StepState;
  stateLabel: string;
}

export function CompactStepper({
  label,
  steps,
  onSelect,
}: {
  label: string;
  steps: CompactStep[];
  onSelect?: (id: string) => void;
}) {
  return (
    <ol aria-label={label} className="grid w-full min-w-0 grid-cols-4 gap-1 sm:gap-2">
      {steps.map((step, index) => {
        const tone = {
          completed: "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-100",
          current: "border-[#0076FF] bg-blue-50 text-[#0B3A75] dark:border-[#00D4FF] dark:bg-[#111D3D] dark:text-[#E8F4FF]",
          blocked: "border-amber-400 bg-amber-50 text-amber-950 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-100",
          upcoming: "border-slate-200 bg-white text-slate-600 dark:border-white/10 dark:bg-white/[0.03] dark:text-slate-300",
        }[step.state];
        const mark = {
          completed: "bg-emerald-700 text-white dark:bg-emerald-500 dark:text-[#06210f]",
          current: "bg-[#0076FF] text-white",
          blocked: "bg-amber-700 text-white dark:bg-amber-400 dark:text-[#2A1B00]",
          upcoming: "bg-slate-200 text-slate-700 dark:bg-white/10 dark:text-slate-200",
        }[step.state];
        return (
          <li key={step.id} className="min-w-0">
            <button
              type="button"
              onClick={() => onSelect?.(step.id)}
              aria-current={step.state === "current" || step.state === "blocked" ? "step" : undefined}
              title={`${step.label} — ${step.stateLabel}`}
              className={`flex w-full min-w-0 items-center gap-1.5 rounded-xl border px-1.5 py-1.5 text-start transition-colors hover:border-[#0076FF]/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0076FF] sm:gap-2 sm:px-2 ${tone}`}
            >
              <span className={`grid h-6 w-6 shrink-0 place-items-center rounded-full text-[11px] font-bold ${mark}`}>
                {index + 1}
              </span>
              <span className="min-w-0">
                <span className="block truncate text-[11px] font-semibold sm:text-xs">{step.label}</span>
                <span className="block truncate text-[10px] opacity-80">{step.stateLabel}</span>
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
