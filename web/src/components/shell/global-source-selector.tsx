"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown, Database, File, Globe, LoaderCircle, Store } from "lucide-react";
import { useSession } from "@/lib/session-context";
import { useLocale } from "@/lib/i18n/locale-context";
import { getApplicationCatalog } from "@/lib/i18n/generated-app-catalogs";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
import { SOURCE_SELECTOR_COPY } from "@/lib/i18n/source-selector-copy";

export function GlobalSourceSelector({ wide = false }: { wide?: boolean }) {
  const session = useSession();
  const { locale } = useLocale();
  const catalog = getApplicationCatalog(locale).company;
  const labels = catalog.connectorHub;
  const t = getAppTranslations(locale);
  const [title, all] = SOURCE_SELECTOR_COPY[locale];
  const tipId = useId();
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
  const ready = (context?.sources ?? session.sourceChoices ?? []).filter(source => source.status.toUpperCase() === "READY" && !!source.dataset_id);
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
  const describedBy = label.length > 18 ? tipId : undefined;
  return <div ref={container} className="group/source relative min-w-0 max-w-full" data-source-state={state}>
    <button type="button" aria-label={`${title}: ${label}. ${status}`} aria-describedby={describedBy} aria-expanded={open} aria-haspopup="menu" title={label} onClick={() => setOpen(value => !value)} className={`flex h-9 min-w-0 items-center gap-1.5 rounded-xl border border-slate-200/80 bg-slate-100 px-2 text-xs font-semibold text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0076FF] dark:border-white/10 dark:bg-[#111D3D] dark:text-[#F4F7FB] ${wide ? "w-full" : "w-full max-w-full"}`}>
      {busy || state === "LOADING" ? <LoaderCircle size={15} className="shrink-0 animate-spin" /> : <SourceIcon size={15} className="shrink-0 text-[#0076FF]" />}<span className="min-w-0 flex-1 truncate text-start">{label}</span><span className={`h-1.5 w-1.5 shrink-0 rounded-full ${state === "READY" ? "bg-emerald-600" : "bg-amber-600"}`} /><ChevronDown size={13} className="shrink-0" />
    </button>
    {describedBy && <span id={describedBy} role="tooltip" className="pointer-events-none absolute start-0 top-full z-20 mt-1 hidden w-max max-w-[min(18rem,calc(100vw-1.5rem))] rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs text-slate-800 shadow-md group-hover/source:block group-focus-within/source:block dark:border-white/10 dark:bg-[#111D3D] dark:text-[#F4F7FB]">{label}</span>}
    {open && <div role="menu" aria-label={title} className="absolute start-0 top-full z-20 mt-1 max-h-[65vh] w-[min(20rem,calc(100vw-1.5rem))] overflow-y-auto rounded-xl border border-slate-200 bg-white p-2 shadow-lg dark:border-white/10 dark:bg-[#0B132B]">
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