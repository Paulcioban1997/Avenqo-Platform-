"use client";

import { useEffect, useRef, useState } from "react";
import { Globe } from "lucide-react";
import { REGIONS, LOCALES } from "@/lib/i18n/locales";
import { useLocale } from "@/lib/i18n/locale-context";
import type { RegionCode } from "@/lib/i18n/types";

/** Sélecteur région → langue façon Salesforce, avec changement instantané dans tout le site. */
export function RegionLanguageSelector() {
  const { locale, setLocale } = useLocale();
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

  return (
    <div className="region-language-selector" ref={rootRef}>
      <button
        type="button"
        className="region-language-trigger"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="true"
        aria-expanded={open}
      >
        <Globe size={15} />
        <span>{active.flag}</span>
        <span className="region-language-code">{active.code.toUpperCase()}</span>
      </button>
      {open && (
        <div className="region-language-panel" role="menu">
          {REGIONS.map((region) => {
            const entries = byRegion(region.code);
            if (entries.length === 0) return null;
            return (
              <div className="region-language-group" key={region.code}>
                <div className="region-language-group-title">{region.label.fr}</div>
                {entries.map((entry) => (
                  <button
                    type="button"
                    key={entry.code}
                    className="region-language-option"
                    data-active={entry.code === locale}
                    role="menuitem"
                    onClick={() => {
                      setLocale(entry.code);
                      setOpen(false);
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
