"use client";

import React from "react";

export interface TrendSparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: "blue" | "emerald" | "violet" | "amber" | "rose";
  showGradient?: boolean;
  className?: string;
}

export function TrendSparkline({
  data,
  width = 160,
  height = 48,
  color = "blue",
  showGradient = true,
  className = "",
}: TrendSparklineProps) {
  if (!data || data.length < 2) {
    return <div className="text-xs text-neutral-400">Pas assez de données</div>;
  }

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min === 0 ? 1 : max - min;
  const padding = 4;

  const points = data.map((val, idx) => {
    const x = padding + (idx / (data.length - 1)) * (width - padding * 2);
    const y = height - padding - ((val - min) / range) * (height - padding * 2);
    return `${x},${y}`;
  });

  const pathD = `M ${points.join(" L ")}`;
  const areaD = `${pathD} L ${width - padding},${height} L ${padding},${height} Z`;

  const colorMap = {
    blue: {
      stroke: "#3b82f6",
      fill: "#3b82f6",
    },
    emerald: {
      stroke: "#10b981",
      fill: "#10b981",
    },
    violet: {
      stroke: "#8b5cf6",
      fill: "#8b5cf6",
    },
    amber: {
      stroke: "#f59e0b",
      fill: "#f59e0b",
    },
    rose: {
      stroke: "#f43f5e",
      fill: "#f43f5e",
    },
  }[color];

  const gradientId = `sparkline-gradient-${color}-${Math.random().toString(36).substring(2, 7)}`;

  return (
    <div className={`inline-block overflow-hidden ${className}`}>
      <svg width={width} height={height} className="overflow-visible">
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={colorMap.fill} stopOpacity={0.25} />
            <stop offset="100%" stopColor={colorMap.fill} stopOpacity={0.0} />
          </linearGradient>
        </defs>
        {showGradient && <path d={areaD} fill={`url(#${gradientId})`} />}
        <path
          d={pathD}
          fill="none"
          stroke={colorMap.stroke}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

export interface MiniBarChartProps {
  data: Array<{ label: string; value: number }>;
  height?: number;
  color?: "blue" | "emerald" | "violet" | "neutral";
  className?: string;
}

export function MiniBarChart({
  data,
  height = 96,
  color = "blue",
  className = "",
}: MiniBarChartProps) {
  if (!data || data.length === 0) return null;

  const maxValue = Math.max(...data.map((d) => d.value), 1);

  const barColor = {
    blue: "bg-blue-600 hover:bg-blue-500",
    emerald: "bg-emerald-600 hover:bg-emerald-500",
    violet: "bg-violet-600 hover:bg-violet-500",
    neutral: "bg-neutral-800 hover:bg-neutral-700 dark:bg-neutral-200 dark:hover:bg-white",
  }[color];

  return (
    <div className={`w-full flex items-end gap-2 pt-4 ${className}`} style={{ height: `${height}px` }}>
      {data.map((item, idx) => {
        const percentage = Math.max((item.value / maxValue) * 100, 4);
        return (
          <div key={idx} className="flex-1 flex flex-col items-center gap-1.5 h-full justify-end group">
            <div className="text-[10px] font-medium text-neutral-400 opacity-0 group-hover:opacity-100 transition-opacity">
              {item.value.toLocaleString()}
            </div>
            <div
              className={`w-full rounded-t-sm transition-all duration-300 ${barColor}`}
              style={{ height: `${percentage}%` }}
            />
            <span className="text-[10px] text-neutral-500 truncate w-full text-center">
              {item.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export interface ComparisonProgressProps {
  label: string;
  value: number;
  target: number;
  unit?: string;
  className?: string;
}

export function ComparisonProgress({
  label,
  value,
  target,
  unit = "",
  className = "",
}: ComparisonProgressProps) {
  const percentage = Math.min(Math.round((value / (target || 1)) * 100), 100);

  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      <div className="flex justify-between text-xs">
        <span className="font-medium text-neutral-700 dark:text-neutral-300">{label}</span>
        <span className="text-neutral-500 dark:text-neutral-400">
          {value.toLocaleString()} / {target.toLocaleString()} {unit} ({percentage}%)
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-neutral-100 dark:bg-neutral-800">
        <div
          className={`h-full transition-all duration-500 rounded-full ${
            percentage >= 100 ? "bg-emerald-500" : percentage >= 70 ? "bg-blue-500" : "bg-amber-500"
          }`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}
