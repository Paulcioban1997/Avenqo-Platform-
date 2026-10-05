"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Database, File, Globe, LoaderCircle, Store } from "lucide-react";
import { useSession } from "@/lib/session-context";
import { useLocale } from "@/lib/i18n/locale-context";
import { getApplicationCatalog } from "@/lib/i18n/generated-app-catalogs";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
import { SOURCE_SELECTOR_COPY } from "@/lib/i18n/source-selector-copy";

export function GlobalSourceSelector() {
  const session = useSession();
  const { locale } = useLocale();
  const catalog = getApplicationCatalog(locale).company;
  const labels = catalog.connectorHub;
  const t = getAppTranslations(locale);
  const [title, all] = SOURCE_SELECTOR_COPY[locale];
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (open) container.current?.querySelector<HTMLButtonElement>('[role="menuitemradio"]:not(:disabled)')?.focus();
  }, [open]);
  useEffect(() => {
    const outside = (event: MouseEvent) => { if (!container.current?.contains(event.target as Node)) setOpen(false); };
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setOpen(false); container.current?.querySelector<HTMLButtonElement>('button[aria-haspopup]')?.focus(); }
      if ((event.key === "ArrowDown" || event.key === "ArrowUp") && container.current?.contains(document.activeElement)) {
        const buttons = Array.from(container.current.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]:not(:disabled)'));
        if (buttons.length) { event.preventDefault(); const current = buttons.indexOf(document.activeElement as HTMLButtonElement); buttons[(current + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length].focus(); }
      }
    };
    document.addEventListener("mousedown", outside); document.addEventListener("keydown", key);
    return () => { document.removeEventListener("mousedown", outside); document.removeEventListener("keydown", key); };
  }, []);
  const context = session.sourceContext;
  const selected = context?.sources.find(source => source.source_type === context.source_type && source.source_id === context.source_id);
  const ready = context?.sources.filter(source => source.status.toUpperCase() === "READY" && !!source.dataset_id) || [];
  const state = session.loading || !context && !session.sourceError ? "LOADING" : session.sourceError ? "SOURCE_ERROR" : context?.state || "NO_SOURCES";
  const label = state === "LOADING" ? catalog.connectionsLoading : context?.source_type === "all" ? all : selected?.display_name ? `${selected.provider ? `${selected.provider} — ` : ""}${selected.display_name}` : (state === "NO_SOURCES" ? t.common.insufficientData : labels.unavailable);
  const SourceIcon = context?.source_type === "all" ? Globe : selected?.source_type === "connector" ? Store : selected?.source_type === "dataset" ? File : Database;
  const status = state === "READY" ? labels.ready : state === "SOURCE_DISCONNECTED" ? labels.disconnected : state === "SOURCE_ERROR" ? labels.error : labels.unavailable;
  const choose = async (type: string, id: string | null) => {
    setBusy(true); setFailed(false);
    try { await session.selectSource(type, id); setOpen(false); }
    catch { setFailed(true); }
    finally { setBusy(false); }
  };
  return <div ref={container} className="relative min-w-0" data-source-state={state}>
    <button type="button" aria-label={title} aria-expanded={open} aria-haspopup="menu" title={`${title}: ${label} — ${status}`} onClick={() => setOpen(value => !value)} className="flex h-9 max-w-[80px] sm:max-w-[220px] items-center gap-1 rounded-md border border-emerald-200 bg-emerald-50 px-1.5 text-xs dark:border-emerald-900 dark:bg-emerald-950/30">
      {busy || state === "LOADING" ? <LoaderCircle size={15} className="shrink-0 animate-spin" /> : <SourceIcon size={15} className="shrink-0" />}<span className="min-w-0 truncate">{label}</span><span className={`h-1.5 w-1.5 shrink-0 rounded-full ${state === "READY" ? "bg-emerald-600" : "bg-amber-600"}`} /><ChevronDown size={13} className="shrink-0" />
    </button>
    {open && <div role="menu" aria-label={title} className="fixed start-4 top-16 z-50 max-h-[65vh] w-[min(340px,calc(100vw-32px))] overflow-y-auto rounded-md border border-gray-200 bg-white p-2 shadow-lg sm:absolute sm:start-0 sm:top-auto sm:mt-2 dark:border-gray-700 dark:bg-[#0B132B]">
      <div className="px-2 py-2 text-xs font-semibold">{title}</div>
      {state !== "READY" && <p role="status" className="px-2 py-2 text-xs text-amber-700 dark:text-amber-400">{state === "LOADING" ? catalog.connectionsLoading : state === "NO_SOURCES" ? t.common.insufficientData : status}</p>}
      {failed && <p role="alert" className="px-2 py-2 text-xs text-red-600">{labels.unavailable}</p>}
      {[["dataset", labels.fileImportTitle], ["connector", labels.commerceSources]].map(([type, group]) => <div key={type}><div className="px-2 pt-3 text-xs text-gray-500">{group}</div>{ready.filter(source => source.source_type === type).map(source => <button type="button" role="menuitemradio" aria-checked={context?.source_id === source.source_id && context?.source_type === source.source_type} disabled={busy} key={source.source_id} onClick={() => void choose(source.source_type, source.source_id)} className="flex w-full items-center gap-2 rounded px-2 py-3 text-start text-sm hover:bg-gray-100 dark:hover:bg-white/10">
        {type === "dataset" ? <File size={16} className="shrink-0" /> : <Store size={16} className="shrink-0" />}<span className="min-w-0 flex-1 break-words">{source.provider && <span className="capitalize">{source.provider} — </span>}{source.display_name}</span>{context?.source_id === source.source_id && <Check size={16} className="shrink-0" />}
      </button>)}</div>)}
      <button type="button" role="menuitemradio" aria-checked={context?.source_type === "all"} disabled={busy || !ready.some(source => source.enabled)} onClick={() => void choose("all", null)} className="mt-2 flex w-full items-center gap-2 border-t border-gray-200 px-2 py-3 text-start text-sm disabled:opacity-50 dark:border-gray-700"><Globe size={16} /><span className="flex-1">{all}</span>{context?.source_type === "all" && <Check size={16} />}</button>
    </div>}
  </div>;
}