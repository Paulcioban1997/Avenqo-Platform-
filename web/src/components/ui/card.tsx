import React from "react";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

export function Card({
  children,
  className = "",
  hoverable = false,
}: {
  children: React.ReactNode;
  className?: string;
  hoverable?: boolean;
}) {
  return (
    <div
      className={`rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/90 text-neutral-950 dark:text-neutral-50 shadow-xs transition-all duration-200 ${
        hoverable ? "hover:border-neutral-300 dark:hover:border-neutral-700 hover:shadow-sm" : ""
      } ${className}`}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={`flex flex-col space-y-1.5 p-5 pb-3 ${className}`}>{children}</div>;
}

export function CardTitle({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <h3 className={`text-base font-semibold leading-none tracking-tight text-neutral-900 dark:text-neutral-100 ${className}`}>{children}</h3>;
}

export function CardDescription({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <p className={`text-xs text-neutral-500 dark:text-neutral-400 ${className}`}>{children}</p>;
}

export function CardContent({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={`p-5 pt-0 ${className}`}>{children}</div>;
}

export function CardFooter({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={`flex items-center p-5 pt-0 border-t border-neutral-100 dark:border-neutral-800/60 mt-3 text-xs text-neutral-500 dark:text-neutral-400 ${className}`}>{children}</div>;
}

export function StatCard({
  title,
  value,
  subtitle,
  change,
  changeType = "neutral",
  icon,
}: {
  title: string;
  value: string | number;
  subtitle?: string;
  change?: string;
  changeType?: "positive" | "negative" | "neutral";
  icon?: React.ReactNode;
}) {
  const trendColor = {
    positive: "text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/40",
    negative: "text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-950/40",
    neutral: "text-neutral-600 dark:text-neutral-400 bg-neutral-100 dark:bg-neutral-800",
  }[changeType];

  return (
    <Card hoverable className="p-5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
          {title}
        </span>
        {icon && (
          <div className="p-2 rounded-lg bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-300">
            {icon}
          </div>
        )}
      </div>
      <div className="mt-3 flex items-baseline gap-2">
        <span className="text-2xl sm:text-3xl font-bold tracking-tight text-neutral-900 dark:text-neutral-50">
          {value}
        </span>
        {change && (
          <span className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-xs font-semibold ${trendColor}`}>
            {changeType === "positive" && <ArrowUpRight className="w-3 h-3" />}
            {changeType === "negative" && <ArrowDownRight className="w-3 h-3" />}
            {changeType === "neutral" && <Minus className="w-3 h-3" />}
            {change}
          </span>
        )}
      </div>
      {subtitle && (
        <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
          {subtitle}
        </p>
      )}
    </Card>
  );
}
