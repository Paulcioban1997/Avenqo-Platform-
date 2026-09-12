"use client";

import React from "react";
import { Sparkles, CheckCircle2, AlertCircle, Inbox, RefreshCw } from "lucide-react";
import { Button } from "./button";

export interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}

export function EmptyState({
  icon = <Inbox className="w-8 h-8 text-neutral-400" />,
  title,
  description,
  actionLabel,
  onAction,
  className = "",
}: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center p-8 md:p-12 text-center rounded-2xl border border-dashed border-neutral-300 dark:border-neutral-800 bg-neutral-50/50 dark:bg-neutral-900/30 ${className}`}
    >
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-neutral-100 dark:bg-neutral-800 mb-4 shadow-xs">
        {icon}
      </div>
      <h3 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">{title}</h3>
      <p className="mt-1.5 text-sm text-neutral-500 dark:text-neutral-400 max-w-sm">{description}</p>
      {actionLabel && onAction && (
        <div className="mt-6">
          <Button variant="primary" size="sm" onClick={onAction}>
            {actionLabel}
          </Button>
        </div>
      )}
    </div>
  );
}

export interface SuccessStateProps {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}

export function SuccessState({
  title,
  description,
  actionLabel,
  onAction,
  className = "",
}: SuccessStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center p-8 md:p-10 text-center rounded-2xl border border-emerald-200 dark:border-emerald-900/50 bg-emerald-50/30 dark:bg-emerald-950/20 ${className}`}
    >
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-100 dark:bg-emerald-900/40 text-emerald-600 dark:text-emerald-400 mb-4 shadow-xs">
        <CheckCircle2 className="w-7 h-7" />
      </div>
      <h3 className="text-base font-semibold text-emerald-950 dark:text-emerald-100">{title}</h3>
      <p className="mt-1 text-sm text-emerald-700/80 dark:text-emerald-400/80 max-w-sm">
        {description}
      </p>
      {actionLabel && onAction && (
        <div className="mt-5">
          <Button variant="outline" size="sm" onClick={onAction}>
            {actionLabel}
          </Button>
        </div>
      )}
    </div>
  );
}

export interface ErrorStateProps {
  title?: string;
  error: string;
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
}

export function ErrorState({
  title = "Une erreur est survenue",
  error,
  onRetry,
  retryLabel = "Réessayer",
  className = "",
}: ErrorStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center p-8 md:p-10 text-center rounded-2xl border border-rose-200 dark:border-rose-900/50 bg-rose-50/30 dark:bg-rose-950/20 ${className}`}
    >
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-rose-100 dark:bg-rose-900/40 text-rose-600 dark:text-rose-400 mb-4 shadow-xs">
        <AlertCircle className="w-7 h-7" />
      </div>
      <h3 className="text-base font-semibold text-rose-950 dark:text-rose-100">{title}</h3>
      <p className="mt-1 text-sm text-rose-700/80 dark:text-rose-400/80 max-w-sm">{error}</p>
      {onRetry && (
        <div className="mt-5">
          <Button
            variant="outline"
            size="sm"
            onClick={onRetry}
            leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
          >
            {retryLabel}
          </Button>
        </div>
      )}
    </div>
  );
}

export interface AIStateProps {
  status: "thinking" | "completed" | "grounded" | "predicted";
  message?: string;
  modelBadge?: string;
  confidence?: number;
  className?: string;
}

export function AIState({
  status,
  message,
  modelBadge = "AVENQO AI v2.4",
  confidence,
  className = "",
}: AIStateProps) {
  const isThinking = status === "thinking";

  return (
    <div
      className={`relative overflow-hidden rounded-xl border border-blue-200/80 dark:border-blue-900/50 bg-gradient-to-r from-blue-50/60 via-indigo-50/30 to-violet-50/60 dark:from-blue-950/20 dark:via-indigo-950/10 dark:to-violet-950/20 p-4 transition-all duration-300 ${className}`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="relative flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-white shadow-xs">
            <Sparkles className={`w-4 h-4 ${isThinking ? "animate-spin" : ""}`} />
            {isThinking && (
              <span className="absolute -top-0.5 -right-0.5 flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-500"></span>
              </span>
            )}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-blue-900 dark:text-blue-300">
                {isThinking
                  ? "Raisonnement multi-agents en cours..."
                  : status === "grounded"
                  ? "Grounding confirmé sur données réelles"
                  : status === "predicted"
                  ? "Projection prédictive IA (non audité)"
                  : "Synthèse IA validée"}
              </span>
              <span className="inline-flex items-center rounded-full bg-blue-100 dark:bg-blue-900/60 px-2 py-0.5 text-[10px] font-medium text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
                {modelBadge}
              </span>
            </div>
            {message && (
              <p className="text-xs text-neutral-600 dark:text-neutral-400 mt-0.5">{message}</p>
            )}
          </div>
        </div>

        {typeof confidence === "number" && (
          <div className="text-right shrink-0">
            <span className="text-[10px] uppercase font-semibold text-neutral-400 dark:text-neutral-500 block">
              Confiance
            </span>
            <span className="text-xs font-bold text-blue-700 dark:text-blue-300">
              {(confidence * 100).toFixed(0)}%
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
