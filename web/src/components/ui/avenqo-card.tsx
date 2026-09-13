"use client";

import React from "react";
import { ArrowDownRight, ArrowUpRight, Minus, Activity } from "lucide-react";
import { Skeleton } from "./skeleton";

export type CardVariant = "default" | "elevated" | "highlighted" | "glass";

export interface AvenqoCardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: CardVariant;
  hoverable?: boolean;
  children: React.ReactNode;
  className?: string;
}

export function AvenqoCard({
  variant = "default",
  hoverable = false,
  children,
  className = "",
  ...props
}: AvenqoCardProps) {
  const variantStyles = {
    default:
      "bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs text-slate-900 dark:text-[#F4F7FB]",
    elevated:
      "bg-white dark:bg-[#111D3D] border border-slate-200/90 dark:border-white/[0.12] shadow-md dark:shadow-[0_8px_32px_rgba(0,0,0,0.36)] text-slate-900 dark:text-[#F4F7FB]",
    highlighted:
      "bg-gradient-to-b from-blue-50/70 to-white dark:from-[#111D3D] dark:to-[#0B132B] border border-[#0076FF]/30 dark:border-[#0076FF]/40 shadow-sm dark:shadow-[0_0_24px_rgba(0,118,255,0.12)] text-slate-900 dark:text-[#F4F7FB]",
    glass:
      "bg-white/70 dark:bg-[#0B132B]/70 backdrop-blur-md border border-slate-200/60 dark:border-white/[0.08] shadow-sm text-slate-900 dark:text-[#F4F7FB]",
  }[variant];

  const hoverStyle = hoverable
    ? "transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md hover:border-slate-300 dark:hover:border-white/[0.18]"
    : "transition-colors duration-200";

  return (
    <div
      className={`rounded-2xl p-5 ${variantStyles} ${hoverStyle} ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

export interface MetricCardProps {
  title: string;
  value?: string | number | null;
  delta?: number | null; // e.g. +14.2 or -3.1
  period?: string; // e.g. "vs mois dernier"
  icon?: React.ReactNode;
  sparklineData?: number[];
  isLoading?: boolean;
  badge?: string;
  subtitle?: string;
  className?: string;
}

export function MetricCard({
  title,
  value,
  delta,
  period = "vs période préc.",
  icon,
  sparklineData,
  isLoading = false,
  badge,
  subtitle,
  className = "",
}: MetricCardProps) {
  if (isLoading || value === undefined || value === null) {
    return (
      <AvenqoCard variant="default" className={`p-5 flex flex-col justify-between min-h-[140px] ${className}`}>
        <div className="flex items-center justify-between mb-3">
          <Skeleton className="h-4 w-28" />
          <Skeleton className="h-8 w-8 rounded-xl" />
        </div>
        <Skeleton className="h-8 w-36 mb-2" />
        <div className="flex items-center gap-2">
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-3 w-24" />
        </div>
      </AvenqoCard>
    );
  }

  const isPositive = typeof delta === "number" && delta > 0;
  const isNegative = typeof delta === "number" && delta < 0;
  const isNeutral = typeof delta === "number" && delta === 0;

  return (
    <AvenqoCard variant="default" hoverable className={`p-5 flex flex-col justify-between min-h-[140px] group ${className}`}>
      <div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-[#94A3B8]">
            {title}
          </span>
          <div className="flex items-center gap-1.5">
            {badge && (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 dark:bg-[#0076FF]/15 dark:text-[#00D4FF] border border-blue-200 dark:border-[#0076FF]/30">
                {badge}
              </span>
            )}
            {icon && (
              <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-slate-100 dark:bg-[#111D3D] text-slate-600 dark:text-[#94A3B8] group-hover:text-[#0076FF] group-hover:bg-blue-50 dark:group-hover:bg-[#172652] transition-colors">
                {icon}
              </div>
            )}
          </div>
        </div>

        <div className="mt-2 flex items-baseline justify-between gap-3">
          <div className="text-2xl lg:text-3xl font-bold tracking-tight text-slate-900 dark:text-[#F4F7FB]">
            {value}
          </div>
        </div>

        {subtitle && (
          <p className="mt-0.5 text-xs text-slate-500 dark:text-[#94A3B8]">
            {subtitle}
          </p>
        )}
      </div>

      <div className="mt-3.5 pt-3 border-t border-slate-100 dark:border-white/[0.06] flex items-center justify-between text-xs">
        {typeof delta === "number" ? (
          <div className="flex items-center gap-1.5 font-medium">
            <span
              className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md text-[11px] font-semibold ${
                isPositive
                  ? "text-emerald-700 bg-emerald-50 dark:text-emerald-400 dark:bg-emerald-950/40"
                  : isNegative
                  ? "text-rose-700 bg-rose-50 dark:text-rose-400 dark:bg-rose-950/40"
                  : "text-slate-600 bg-slate-100 dark:text-slate-400 dark:bg-white/[0.06]"
              }`}
            >
              {isPositive && <ArrowUpRight size={13} />}
              {isNegative && <ArrowDownRight size={13} />}
              {isNeutral && <Minus size={13} />}
              {delta > 0 ? `+${delta}%` : `${delta}%`}
            </span>
            <span className="text-slate-500 dark:text-[#94A3B8] text-[11px] truncate max-w-[120px]">
              {period}
            </span>
          </div>
        ) : (
          <span className="text-slate-500 dark:text-[#94A3B8] text-[11px]">{period}</span>
        )}

        {sparklineData && sparklineData.length > 1 && (
          <div className="w-16 h-6 flex items-end">
            <MiniSparkline data={sparklineData} isPositive={isPositive} />
          </div>
        )}
      </div>
    </AvenqoCard>
  );
}

function MiniSparkline({ data, isPositive }: { data: number[]; isPositive?: boolean }) {
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min === 0 ? 1 : max - min;
  const width = 64;
  const height = 24;

  const points = data.map((val, idx) => {
    const x = (idx / (data.length - 1)) * width;
    const y = height - ((val - min) / range) * (height - 4) - 2;
    return `${x},${y}`;
  });

  const strokeColor = isPositive ? "#10B981" : "#0076FF";

  return (
    <svg width={width} height={height} className="overflow-visible">
      <polyline
        fill="none"
        stroke={strokeColor}
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points.join(" ")}
      />
    </svg>
  );
}

export type StatusBadgeType =
  | "connected"
  | "syncing"
  | "needs_attention"
  | "disconnected"
  | "coming_soon"
  | "active"
  | "pending";

export interface StatusBadgeProps {
  status: StatusBadgeType;
  label?: string;
  className?: string;
  size?: "sm" | "md";
}

export function StatusBadge({
  status,
  label,
  className = "",
  size = "md",
}: StatusBadgeProps) {
  const config = {
    connected: {
      defaultLabel: "Connecté",
      dot: "bg-emerald-500",
      pill: "bg-emerald-50 text-emerald-700 border-emerald-200/80 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-900/60",
      ping: false,
    },
    syncing: {
      defaultLabel: "Synchronisation...",
      dot: "bg-[#0076FF]",
      pill: "bg-blue-50 text-blue-700 border-blue-200/80 dark:bg-[#0076FF]/15 dark:text-[#00D4FF] dark:border-[#0076FF]/30",
      ping: true,
    },
    needs_attention: {
      defaultLabel: "Attention requise",
      dot: "bg-amber-500",
      pill: "bg-amber-50 text-amber-800 border-amber-200/80 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-900/60",
      ping: false,
    },
    disconnected: {
      defaultLabel: "Déconnecté",
      dot: "bg-slate-400 dark:bg-slate-500",
      pill: "bg-slate-50 text-slate-600 border-slate-200 dark:bg-white/[0.04] dark:text-slate-400 dark:border-white/[0.08]",
      ping: false,
    },
    coming_soon: {
      defaultLabel: "Bientôt disponible",
      dot: "bg-violet-400",
      pill: "bg-violet-50 text-violet-700 border-violet-200/80 dark:bg-violet-950/40 dark:text-violet-300 dark:border-violet-900/60",
      ping: false,
    },
    active: {
      defaultLabel: "Actif",
      dot: "bg-emerald-500",
      pill: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-900/60",
      ping: false,
    },
    pending: {
      defaultLabel: "En attente",
      dot: "bg-amber-500",
      pill: "bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-900/60",
      ping: false,
    },
  }[status];

  const sizeStyles =
    size === "sm" ? "px-2 py-0.5 text-[10px]" : "px-2.5 py-1 text-xs";

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-medium border ${config.pill} ${sizeStyles} ${className}`}
    >
      <span className="relative flex h-2 w-2">
        {config.ping && (
          <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${config.dot}`} />
        )}
        <span className={`relative inline-flex rounded-full h-2 w-2 ${config.dot}`} />
      </span>
      <span>{label || config.defaultLabel}</span>
    </span>
  );
}
