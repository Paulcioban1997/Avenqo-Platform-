"use client";

import React from "react";

export function Table({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className="relative w-full overflow-x-auto rounded-xl border border-neutral-200/80 dark:border-neutral-800 bg-white dark:bg-neutral-900/60 shadow-xs">
      <table className={`w-full text-left text-sm text-neutral-600 dark:text-neutral-400 ${className}`}>
        {children}
      </table>
    </div>
  );
}

export function TableHeader({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <thead
      className={`bg-neutral-50/80 dark:bg-neutral-800/40 text-xs font-semibold uppercase tracking-wider text-neutral-500 dark:text-neutral-400 border-b border-neutral-200/80 dark:border-neutral-800 ${className}`}
    >
      {children}
    </thead>
  );
}

export function TableBody({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <tbody className={`divide-y divide-neutral-200/60 dark:divide-neutral-800/60 ${className}`}>
      {children}
    </tbody>
  );
}

export function TableRow({
  children,
  className = "",
  onClick,
}: {
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
}) {
  return (
    <tr
      onClick={onClick}
      className={`transition-colors duration-150 hover:bg-neutral-50/60 dark:hover:bg-neutral-800/30 ${
        onClick ? "cursor-pointer" : ""
      } ${className}`}
    >
      {children}
    </tr>
  );
}

export function TableHead({
  children,
  className = "",
  align = "left",
}: {
  children: React.ReactNode;
  className?: string;
  align?: "left" | "center" | "right";
}) {
  const alignClass = {
    left: "text-left",
    center: "text-center",
    right: "text-right",
  }[align];

  return (
    <th scope="col" className={`px-4 py-3 font-semibold ${alignClass} ${className}`}>
      {children}
    </th>
  );
}

export function TableCell({
  children,
  className = "",
  align = "left",
}: {
  children: React.ReactNode;
  className?: string;
  align?: "left" | "center" | "right";
}) {
  const alignClass = {
    left: "text-left",
    center: "text-center",
    right: "text-right",
  }[align];

  return (
    <td className={`px-4 py-3.5 text-neutral-800 dark:text-neutral-200 ${alignClass} ${className}`}>
      {children}
    </td>
  );
}

export function TableEmpty({
  colSpan,
  message = "Aucune donnée disponible",
  description,
}: {
  colSpan: number;
  message?: string;
  description?: string;
}) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-4 py-12 text-center">
        <div className="flex flex-col items-center justify-center gap-1">
          <p className="text-sm font-medium text-neutral-700 dark:text-neutral-300">{message}</p>
          {description && (
            <p className="text-xs text-neutral-400 dark:text-neutral-500">{description}</p>
          )}
        </div>
      </td>
    </tr>
  );
}
