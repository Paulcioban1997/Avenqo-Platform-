"use client";

import React from "react";

export function Skeleton({
  className = "",
  style,
}: {
  className?: string;
  style?: React.CSSProperties;
}) {
  return (
    <div
      style={style}
      className={`animate-pulse rounded-md bg-neutral-200/80 dark:bg-neutral-800/80 ${className}`}
    />
  );
}

export function CardSkeleton() {
  return (
    <div className="rounded-xl border border-neutral-200/80 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-6 space-y-4">
      <div className="flex items-center justify-between">
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-6 w-6 rounded-full" />
      </div>
      <Skeleton className="h-8 w-1/2" />
      <div className="space-y-2 pt-2">
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-4/5" />
      </div>
    </div>
  );
}

export function KPISkeleton() {
  return (
    <div className="rounded-2xl border border-slate-200/80 dark:border-white/[0.08] bg-white dark:bg-[#0B132B] p-5 flex flex-col justify-between min-h-[140px] space-y-3">
      <div className="flex items-center justify-between">
        <Skeleton className="h-3.5 w-24 rounded" />
        <Skeleton className="h-8 w-8 rounded-xl" />
      </div>
      <Skeleton className="h-7 w-32 rounded-md" />
      <div className="pt-2 border-t border-slate-100 dark:border-white/[0.06] flex items-center justify-between">
        <Skeleton className="h-3.5 w-16 rounded" />
        <Skeleton className="h-3 w-16 rounded" />
      </div>
    </div>
  );
}

export function ChartSkeleton({ height = 280 }: { height?: number }) {
  return (
    <div
      className="rounded-2xl border border-slate-200/80 dark:border-white/[0.08] bg-white dark:bg-[#0B132B] p-6 space-y-4"
      style={{ minHeight: height }}
    >
      <div className="flex items-center justify-between">
        <div className="space-y-1.5">
          <Skeleton className="h-4 w-36 rounded" />
          <Skeleton className="h-3 w-48 rounded" />
        </div>
        <Skeleton className="h-8 w-28 rounded-lg" />
      </div>
      <div className="flex items-end gap-3 pt-6 h-48">
        {[40, 65, 30, 85, 55, 95, 70, 60, 80, 45].map((h, i) => (
          <div key={i} className="flex-1 flex flex-col items-center gap-2 h-full justify-end">
            <Skeleton className="w-full rounded-t" style={{ height: `${h}%` }} />
            <Skeleton className="h-2.5 w-6" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function TableRowSkeleton({ columns = 4, rows = 5 }: { columns?: number; rows?: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, rIdx) => (
        <tr key={rIdx} className="border-b border-neutral-200/60 dark:border-neutral-800/60">
          {Array.from({ length: columns }).map((_, cIdx) => (
            <td key={cIdx} className="px-4 py-4">
              <Skeleton
                className="h-4"
                style={{ width: `${Math.max(40, 90 - ((rIdx + cIdx) % 4) * 15)}%` }}
              />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

export function TableSkeleton({ rows = 5, columns = 4 }: { rows?: number; columns?: number }) {
  return (
    <div className="rounded-2xl border border-slate-200/80 dark:border-white/[0.08] bg-white dark:bg-[#0B132B] overflow-hidden">
      <div className="p-4 border-b border-slate-200/80 dark:border-white/[0.08] flex items-center justify-between">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-8 w-40 rounded-lg" />
      </div>
      <div className="divide-y divide-slate-100 dark:divide-white/[0.06]">
        {Array.from({ length: rows }).map((_, r) => (
          <div key={r} className="p-4 flex items-center justify-between gap-4">
            {Array.from({ length: columns }).map((_, c) => (
              <Skeleton
                key={c}
                className="h-3.5"
                style={{ width: `${Math.max(40, 85 - ((r + c) % 3) * 20)}px` }}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export function AIInsightSkeleton() {
  return (
    <div className="rounded-2xl border border-blue-200/60 dark:border-[#0076FF]/30 bg-gradient-to-br from-blue-50/40 via-white to-indigo-50/30 dark:from-[#0B132B] dark:via-[#111D3D] dark:to-[#0B132B] p-5 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <Skeleton className="h-8 w-8 rounded-xl bg-blue-200/60 dark:bg-blue-900/40" />
          <Skeleton className="h-4 w-40 rounded" />
        </div>
        <Skeleton className="h-5 w-20 rounded-full" />
      </div>
      <Skeleton className="h-4 w-3/4 rounded" />
      <Skeleton className="h-3.5 w-full rounded" />
      <Skeleton className="h-3.5 w-5/6 rounded" />
      <div className="pt-2 flex items-center justify-between">
        <Skeleton className="h-3 w-28 rounded" />
        <Skeleton className="h-8 w-32 rounded-lg" />
      </div>
    </div>
  );
}
