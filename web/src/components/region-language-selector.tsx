"use client";

import { useEffect, useRef, useState } from "react";
import { Globe } from "lucide-react";
import { REGIONS, LOCALES } from "@/lib/i18n/locales";
import { useLocale } from "@/lib/i18n/locale-context";
import type { RegionCode } from "@/lib/i18n/types";
import { useOptionalSession } from "@/lib/session-context";

/** Sélecteur région → langue façon Salesforce, avec changement instantané dans tout le site. */
export function RegionLanguageSelector({ appearance = "marketing" }: { appearance?: "marketing" | "app" }) {
  const { locale, setLocale } = useLocale();
  const identity = useOptionalSession()?.identity;
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const active = LOCALES.find((entry) => entry.code === locale) ?? LOCALES[0];

  useEffect(() => {
    function onPointerDown(event: PointerEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  const byRegion = (region: RegionCode) => LOCALES.filter((entry) => entry.region === region);

  const appTrigger = appearance === "app";
  return (
    <div className={appTrigger ? "relative shrink-0" : "region-language-selector"} ref={rootRef}>
      <button
        type="button"
        className={appTrigger
          ? "inline-flex h-9 items-center gap-1 rounded-xl border border-slate-200/80 bg-slate-100 px-2 text-xs font-semibold text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0076FF] dark:border-white/10 dark:bg-[#111D3D] dark:text-[#F4F7FB]"
          : "region-language-trigger"}
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={active.nativeName}
      >
        <Globe size={15} />
        <span>{active.flag}</span>
        <span className={appTrigger ? "hidden max-w-[4.5rem] truncate sm:inline" : "region-language-code"}>{active.code.toUpperCase()}</span>
      </button>
      {open && (
        <div className={appTrigger
          ? "absolute end-0 top-full z-20 mt-1 max-h-80 w-[min(18rem,calc(100vw-1rem))] overflow-y-auto rounded-xl border border-slate-200 bg-white p-2 text-slate-800 shadow-lg dark:border-white/10 dark:bg-[#0B132B] dark:text-[#F4F7FB]"
          : "region-language-panel"} role="menu">
          {REGIONS.map((region) => {
            const entries = byRegion(region.code);
            if (entries.length === 0) return null;
            return (
              <div className={appTrigger ? "py-1" : "region-language-group"} key={region.code}>
                <div className={appTrigger ? "px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-slate-500" : "region-language-group-title"}>
                  {locale.startsWith("fr") ? region.label.fr : region.label.en}
                </div>
                {entries.map((entry) => (
                  <button
                    type="button"
                    key={entry.code}
                    className={appTrigger
                      ? "flex w-full items-center gap-2 rounded-lg px-2 py-2 text-start text-sm text-slate-800 hover:bg-slate-100 data-[active=true]:bg-blue-50 data-[active=true]:text-[#0B3A75] dark:text-[#F4F7FB] dark:hover:bg-white/10 dark:data-[active=true]:bg-[#172652]"
                      : "region-language-option"}
                    data-active={entry.code === locale}
                    role="menuitem"
                    onClick={() => {
                      setLocale(entry.code);
                      setOpen(false);
                      if (identity?.company.id) {
                        void fetch("/api/v1/auth/preferred-language", {
                          method: "PATCH",
                          credentials: "include",
                          headers: { "Content-Type": "application/json", "X-Requested-With": "avenqo-web" },
                          body: JSON.stringify({ preferred_language: entry.code }),
                        }).catch(() => undefined);
                      }
                    }}
                  >
                    <span className="region-language-flag">{entry.flag}</span>
                    <span className="region-language-name">{entry.nativeName}</span>
                  </button>
                ))}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
