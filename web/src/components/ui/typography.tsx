import React from "react";

export function H1({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <h1 className={`text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight text-neutral-900 dark:text-neutral-50 ${className}`}>
      {children}
    </h1>
  );
}

export function H2({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <h2 className={`text-2xl sm:text-3xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-50 ${className}`}>
      {children}
    </h2>
  );
}

export function H3({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <h3 className={`text-xl sm:text-2xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-50 ${className}`}>
      {children}
    </h3>
  );
}

export function H4({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <h4 className={`text-lg font-medium tracking-tight text-neutral-900 dark:text-neutral-100 ${className}`}>
      {children}
    </h4>
  );
}

export function Text({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <p className={`text-sm sm:text-base text-neutral-700 dark:text-neutral-300 leading-relaxed ${className}`}>
      {children}
    </p>
  );
}

export function TextMuted({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={`text-xs sm:text-sm text-neutral-500 dark:text-neutral-400 ${className}`}>
      {children}
    </span>
  );
}

export function Badge({
  children,
  variant = "default",
  className = "",
}: {
  children: React.ReactNode;
  variant?: "default" | "success" | "warning" | "error" | "ai" | "outline";
  className?: string;
}) {
  const styles = {
    default: "bg-neutral-100 dark:bg-neutral-800 text-neutral-800 dark:text-neutral-200 border-neutral-200 dark:border-neutral-700",
    success: "bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800/60",
    warning: "bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800/60",
    error: "bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-400 border-rose-200 dark:border-rose-800/60",
    ai: "bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-400 border-blue-200 dark:border-blue-800/60 shadow-xs",
    outline: "bg-transparent text-neutral-700 dark:text-neutral-300 border-neutral-300 dark:border-neutral-700",
  };

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${styles[variant]} ${className}`}>
      {children}
    </span>
  );
}
