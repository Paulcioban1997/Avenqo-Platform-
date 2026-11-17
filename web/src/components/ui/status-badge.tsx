import React from "react";

const TONES = {
  neutral: "border-slate-300 bg-slate-100 text-slate-800 dark:border-white/15 dark:bg-white/10 dark:text-slate-100",
  success: "border-emerald-300 bg-emerald-50 text-emerald-950 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-100",
  warning: "border-amber-300 bg-amber-50 text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100",
  info: "border-sky-300 bg-sky-50 text-sky-950 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-100",
  gold: "border-[#C4A35A]/60 bg-[#C4A35A]/12 text-[#6E5210] dark:border-[#E6C36A]/50 dark:bg-[#C4A35A]/15 dark:text-[#F3DE9A]",
} as const;

export function StatusBadge({
  tone = "neutral",
  children,
}: {
  tone?: keyof typeof TONES;
  children: React.ReactNode;
}) {
  return (
    <span className={`inline-flex max-w-full items-center truncate rounded-full border px-2 py-0.5 text-[10px] font-semibold leading-4 ${TONES[tone]}`}>
      {children}
    </span>
  );
}
