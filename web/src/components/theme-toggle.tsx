"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

import { useLocale } from "@/lib/i18n/locale-context";

export function ThemeToggle() {
  const { locale } = useLocale();
  const isEn = locale === "en";
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const stored = window.localStorage.getItem("avenqo_theme_mode");
    if (stored === "dark" || (!stored && window.matchMedia("(prefers-color-scheme: dark)").matches)) {
      setTheme("dark");
      document.documentElement.classList.add("dark");
    } else {
      setTheme("light");
      document.documentElement.classList.remove("dark");
    }
  }, []);

  function toggle() {
    const next = theme === "light" ? "dark" : "light";
    setTheme(next);
    window.localStorage.setItem("avenqo_theme_mode", next);
    if (next === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }

  if (!mounted) {
    return (
      <div className="theme-toggle-placeholder" style={{ width: 34, height: 34 }} />
    );
  }

  const ariaLabel = theme === "dark"
    ? (isEn ? "Switch to light theme" : "Passer au thème clair")
    : (isEn ? "Switch to dark theme" : "Passer au thème sombre");

  const titleText = theme === "dark"
    ? (isEn ? "Light theme" : "Thème clair")
    : (isEn ? "Dark theme" : "Thème sombre");

  return (
    <button
      type="button"
      onClick={toggle}
      className="theme-toggle-btn"
      aria-label={ariaLabel}
      title={titleText}
      data-testid="theme-toggle-btn"
    >
      {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
    </button>
  );
}
