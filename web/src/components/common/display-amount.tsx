"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api-request";
import { formatMoney } from "@/lib/money";

type DisplayQuote = {
  amount: number;
  currency: string;
  converted: boolean;
  unavailable: boolean;
  original_amount: number;
  original_currency: string;
  rate: number | null;
  rate_date: string | null;
  source: string | null;
  valuation: "current" | "transaction_date";
};

type QueuedItem = { id: string; amount: number; currency: string; on_date?: string };

const waiters = new Map<string, Array<(quote: DisplayQuote) => void>>();
let queued = new Map<string, QueuedItem>();
let timer: number | null = null;

function fallback(item: QueuedItem): DisplayQuote {
  return {
    amount: item.amount,
    currency: item.currency,
    converted: false,
    unavailable: false,
    original_amount: item.amount,
    original_currency: item.currency,
    rate: null,
    rate_date: null,
    source: null,
    valuation: item.on_date ? "transaction_date" : "current",
  };
}

function finish(id: string, quote: DisplayQuote) {
  const pending = waiters.get(id) || [];
  waiters.delete(id);
  pending.forEach((notify) => notify(quote));
}

async function flush() {
  const batch = [...queued.values()];
  queued = new Map();
  const slices: QueuedItem[][] = [];
  for (let index = 0; index < batch.length; index += 40) slices.push(batch.slice(index, index + 40));
  await Promise.all(slices.map(async (slice) => {
    try {
      const response = await apiFetch("/api/v1/fx/display", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items: slice }),
      });
      if (!response.ok) {
        slice.forEach((item) => finish(item.id, fallback(item)));
        return;
      }
      const body = await response.json();
      const byId = new Map<string, DisplayQuote>((body.items || []).map((item: DisplayQuote & { id: string }) => [item.id, item]));
      slice.forEach((item) => finish(item.id, byId.get(item.id) || fallback(item)));
    } catch {
      slice.forEach((item) => finish(item.id, fallback(item)));
    }
  }));
}

function useDisplayQuote(amount: number | null | undefined, currency: string | null | undefined, onDate?: string | null) {
  const valid = amount != null && Number.isFinite(amount) && Boolean(currency);
  const id = `${currency || ""}|${onDate || ""}|${amount ?? ""}`;
  const [loaded, setLoaded] = useState<{ id: string; quote: DisplayQuote } | null>(null);
  useEffect(() => {
    if (!valid || amount == null || !currency) return;
    let active = true;
    const waiter = (next: DisplayQuote) => {
      if (active) setLoaded({ id, quote: next });
    };
    waiters.set(id, [...(waiters.get(id) || []), waiter]);
    queued.set(id, { id, amount, currency, on_date: onDate || undefined });
    if (timer) window.clearTimeout(timer);
    timer = window.setTimeout(() => { void flush(); }, 30);
    return () => {
      active = false;
    };
  }, [valid, id, amount, currency, onDate]);
  return valid && loaded?.id === id ? loaded.quote : null;
}

export function DisplayAmount({
  amount,
  currency,
  locale,
  onDate,
  align = "start",
}: {
  amount: number | null | undefined;
  currency: string | null | undefined;
  locale: string;
  onDate?: string | null;
  align?: "start" | "end";
}) {
  const quote = useDisplayQuote(amount, currency, onDate);
  if (amount == null || !Number.isFinite(amount) || !currency) return <span>—</span>;
  const french = locale.toLowerCase().startsWith("fr");
  const original = formatMoney(amount, currency, locale);
  const converted = Boolean(quote?.converted && quote.currency && quote.currency !== currency);
  const primary = converted ? formatMoney(quote!.amount, quote!.currency, locale) : original;
  const valuation = quote?.valuation === "transaction_date"
    ? (french ? "Taux à la date de l'opération" : "Rate on the transaction date")
    : (french ? "Cours du jour, pas la date de chaque opération" : "Today's rate, not each transaction date");
  return (
    <span className={`inline-flex max-w-full flex-col ${align === "end" ? "items-end text-right" : "items-start text-left"}`}>
      <span>{primary}</span>
      {converted && (
        <span className="text-[10px] font-normal leading-snug text-slate-500 dark:text-slate-400">
          {original} · {quote?.source} · {quote?.rate} · {quote?.rate_date} · {valuation}
        </span>
      )}
      {quote?.unavailable && (
        <span className="text-[10px] font-normal leading-snug text-amber-700 dark:text-amber-400">
          {french ? "Conversion indisponible" : "Conversion unavailable"} · {original}
        </span>
      )}
    </span>
  );
}
