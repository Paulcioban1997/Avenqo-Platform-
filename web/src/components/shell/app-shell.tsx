"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  ShoppingBag,
  Network,
  ReceiptText,
  Megaphone,
  Mic2,
  FileScan,
  MessagesSquare,
  Zap,
  LineChart,
  Plug,
  Database,
  Settings,
  Sparkles,
  Search,
  Bell,
  ChevronDown,
  Building2,
  CreditCard,
  LogOut,
  Menu,
  X,
  Check,
  Globe,
  Sliders,
  ShieldAlert,
  Layers,
  Users,
} from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";
import { RegionLanguageSelector } from "@/components/region-language-selector";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
import { CommandPalette } from "./command-palette";
import { AvenqoCopilot } from "./avenqo-copilot";
import { CreditMeter } from "./credit-meter";
import { useSession, type OrganizationItem } from "@/lib/session-context";
import { GlobalSourceSelector } from "./global-source-selector";
import { apiFetch } from "@/lib/api-request";
import { accessibleSurface, readableText } from "@/lib/themes/theme-contrast";
import { RequestFailure } from "@/components/ui/request-failure";
import { getApplicationCatalog } from "@/lib/i18n/generated-app-catalogs";
import { getWorkspaceChrome } from "@/lib/i18n/workspace-chrome-copy";
import { WorkspaceReadinessGate } from "@/components/shell/workspace-readiness-gate";

export interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const { locale } = useLocale();
  const t = getAppTranslations(locale);
  const chrome = getWorkspaceChrome(locale).copy;

  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [isCopilotOpen, setIsCopilotOpen] = useState(false);
  const session = useSession();
  const currentUser = session.identity?.user ?? null;
  const activeTenant = session.identity?.company.name ?? "";
  const organizations = session.identity?.organizations ?? [];
  const activeDataSources = session.activeDataSources;
  const catalog = getApplicationCatalog(locale);
  const [isTenantMenuOpen, setIsTenantMenuOpen] = useState(false);
  const [isNotifMenuOpen, setIsNotifMenuOpen] = useState(false);
  const [unreadNotifsCount, setUnreadNotifsCount] = useState(0);

  const aiCreditsRemaining = session.credits.remaining;
  const aiCreditsLimit = session.credits.limit;

  const [activeModuleKeys, setActiveModuleKeys] = useState<string[] | null>(null);
  const [entitlementsStatus, setEntitlementsStatus] = useState<"loading" | "success" | "error">("loading");
  const [tenantBrand, setTenantBrand] = useState<{
    company_logo_url?: string;
    company_emblem_url?: string;
    logo_placement?: string;
    primary_color?: string;
    secondary_color?: string;
    accent_color?: string;
    mode?: string;
  } | null>(null);

  const loadModuleEntitlements = useCallback(async () => {
    setEntitlementsStatus("loading");
    try {
      const response = await apiFetch("/api/v1/modules/entitlements");
      if (response.ok) {
        const data = await response.json();
        if (Array.isArray(data?.active_modules)) {
          setActiveModuleKeys(data.active_modules);
          setEntitlementsStatus("success");
          return;
        }
      }
      setEntitlementsStatus("error");
    } catch {
      setEntitlementsStatus("error");
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const apply = (data: typeof tenantBrand) => {
      if (!cancelled && data) setTenantBrand(data);
    };
    const onBrand = (event: Event) => apply((event as CustomEvent).detail);
    window.addEventListener("avenqo-branding", onBrand);
    void apiFetch("/api/v1/onboarding/branding")
      .then(async (response) => {
        if (response.ok) apply(await response.json());
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
      window.removeEventListener("avenqo-branding", onBrand);
    };
  }, []);

  useEffect(() => {
    if (!tenantBrand) return;
    const hex = (value: string | undefined, fallback: string) =>
      value && /^#[0-9a-fA-F]{3,8}$/.test(value) ? value : fallback;
    const primary = hex(tenantBrand?.primary_color, "#0076FF");
    const secondary = hex(tenantBrand?.secondary_color, "#0B132B");
    const accent = hex(tenantBrand?.accent_color, "#00D4FF");
    const onSecondary = readableText(secondary);
    const buttonSurface = accessibleSurface(primary);
    const onButton = readableText(buttonSurface);
    const mode = onSecondary === "#F8FAFC" ? "dark" : "light";
    document.documentElement.dataset.tenantTheme = mode;
    document.documentElement.classList.toggle("dark", mode === "dark");
    let style = document.getElementById("tenant-brand-style");
    if (!style) {
      style = document.createElement("style");
      style.id = "tenant-brand-style";
      document.head.appendChild(style);
    }
    style.textContent = `
      html[data-tenant-theme] { --tenant-primary: ${primary}; --tenant-secondary: ${secondary}; --tenant-accent: ${accent}; --tenant-on-secondary: ${onSecondary}; --tenant-on-primary: ${onButton}; }
      html[data-tenant-theme] .min-h-screen,
      html[data-tenant-theme] header,
      html[data-tenant-theme] aside { background-color: ${secondary} !important; color: ${onSecondary}; }
      html[data-tenant-theme] .bg-\\[\\#0076FF\\] { background-color: ${buttonSurface} !important; color: ${onButton} !important; }
      html[data-tenant-theme] .text-\\[\\#0076FF\\] { color: ${primary} !important; }
      html[data-tenant-theme] .border-\\[\\#0076FF\\] { border-color: ${primary} !important; }
      html[data-tenant-theme] .ring-\\[\\#0076FF\\] { --tw-ring-color: ${primary} !important; }
      html[data-tenant-theme] .text-\\[\\#00D4FF\\] { color: ${accent} !important; }
    `;
  }, [tenantBrand]);

  useEffect(() => {
    void loadModuleEntitlements();
    const handleSourceChanged = () => {
      void loadModuleEntitlements();
    };
    window.addEventListener("avenqo:sources-changed", handleSourceChanged);
    return () => window.removeEventListener("avenqo:sources-changed", handleSourceChanged);
  }, [loadModuleEntitlements]);

  const handleSwitchTenant = async (org: OrganizationItem) => {
    try {
      const res = await apiFetch("/api/v1/auth/switch-tenant", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ company_id: org.id }),
      });
      if (res.ok) {
        const channel = new BroadcastChannel("avenqo-session");
        channel.postMessage("tenant-changed");
        channel.close();
        setIsTenantMenuOpen(false);
        window.location.reload();
      }
    } catch {}
  };

  const handleSignOut = async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST", headers: { "X-Requested-With": "avenqo-web" }, signal: AbortSignal.timeout(15_000) });
    } catch {}
    if (typeof BroadcastChannel !== "undefined") {
      const channel = new BroadcastChannel("avenqo-session");
      channel.postMessage("session-ended");
      channel.close();
    }
    localStorage.removeItem("avenqo_token");
    localStorage.removeItem("avenqo_access_token");
    localStorage.removeItem("avenqo_refresh_token");
    window.location.href = "/login?session_expired=1";
  };

  // Navigation modules with dynamic entitlement filtering
  type NavItem = {
    href: string;
    label: string;
    icon: React.ComponentType<{ className?: string }>;
    moduleKey?: string;
    badge?: string;
    permissions?: string[];
  };
  const granted = currentUser?.permissions;
  const allows = (permissions?: string[]) => Boolean(granted && (!permissions || permissions.some((permission) => granted.includes(permission))));
  const showCopilot = allows(["ai:use"]);

  const allMainModules: NavItem[] = [
    { href: "/dashboard", label: t.navigation.dashboard, icon: LayoutDashboard, permissions: ["data:read"] },
    { href: "/retail", label: t.navigation.retailAi, icon: ShoppingBag, moduleKey: "retail", permissions: ["retail:read"] },
    { href: "/crm", label: t.navigation.crmAi, icon: Network, moduleKey: "crm", permissions: ["crm:appointments:read", "crm:clients:read"] },
    { href: "/accounting", label: t.navigation.accountingAi, icon: ReceiptText, moduleKey: "accounting", permissions: ["accounting:read"] },
  ];

  const filterByEntitlements = (item: NavItem) => {
    if (granted && item.permissions && !item.permissions.some((permission) => granted.includes(permission))) return false;
    if (!item.moduleKey) return true;
    // 2. Strict backend authorization: only show if backend explicitly returned this module key
    if (entitlementsStatus === "success" && activeModuleKeys) {
      return activeModuleKeys.includes(item.moduleKey);
    }
    // 3. During loading or upon network/server error: do NOT arbitrarily expose unentitled modules
    return false;
  };

  const mainModules = allMainModules.filter(filterByEntitlements);

  const allAiModules: NavItem[] = [
    { href: "/marketing", label: t.navigation.marketingAi, icon: Megaphone, moduleKey: "marketing", permissions: ["marketing:read"] },
    { href: "/voice", label: t.navigation.voiceAi, icon: Mic2, moduleKey: "voice", permissions: ["modules:manage"] },
    { href: "/ocr", label: t.navigation.ocrAi, icon: FileScan, moduleKey: "ocr", permissions: ["ai:use"] },
    { href: "/legal", label: chrome.legal, icon: FileScan, moduleKey: "legal", permissions: ["ai:use"] },
    { href: "/chatbots", label: t.navigation.chatbotsAi, icon: MessagesSquare, moduleKey: "chatbots", permissions: ["ai:use"] },
    { href: "/automations", label: t.navigation.automations, icon: Zap, moduleKey: "workflow", permissions: ["ai:use", "modules:manage"] },
    { href: "/trading", label: "Trading", icon: LineChart, moduleKey: "trading", permissions: ["trading:read"] },
  ];

  const aiModules = allAiModules.filter(filterByEntitlements);

  const platformModules = [
    { href: "/workspace/modules", label: chrome.modules, icon: Sparkles, permissions: ["modules:manage"] },
    { href: "/connections", label: t.navigation.connections, icon: Plug, permissions: ["data:manage"] },
    { href: "/data", label: t.navigation.dataHub, icon: Database, permissions: ["data:read"] },
    { href: "/employees", label: t.navigation.team, icon: Users },
    { href: "/billing", label: t.navigation.billing, icon: CreditCard, permissions: ["billing:manage"] },
    { href: "/settings/contracts", label: chrome.contracts, icon: FileScan, permissions: ["billing:manage"] },
    { href: "/settings", label: t.navigation.settings, icon: Settings, permissions: ["company:manage"] },
    { href: "/security", label: chrome.security, icon: ShieldAlert, permissions: ["company:manage"] },
  ].filter((item) => !granted || !item.permissions || item.permissions.some((permission) => granted.includes(permission)));

  // Global Ctrl+K / Cmd+K listener
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setIsCommandPaletteOpen((prev) => !prev);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const placement = tenantBrand?.logo_placement === "header" || tenantBrand?.logo_placement === "sidebar"
    ? tenantBrand.logo_placement
    : "both";
  const brandMark = tenantBrand?.company_logo_url || tenantBrand?.company_emblem_url || "";
  const showHeaderLogo = Boolean(brandMark) && (placement === "header" || placement === "both");
  const showSidebarLogo = Boolean(brandMark) && (placement === "sidebar" || placement === "both");
  const openSearch = () => setIsCommandPaletteOpen(true);
  const searchField = (testId: string) => (
    <button
      type="button"
      data-testid={testId}
      onClick={openSearch}
      className="flex h-9 w-full min-w-0 items-center gap-2 rounded-xl border border-slate-200/80 bg-slate-100 px-3 text-xs text-slate-600 hover:bg-slate-200/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0076FF] dark:border-white/10 dark:bg-[#111D3D] dark:text-[#C5D0E0] dark:hover:bg-[#172652]"
    >
      <Search className="h-3.5 w-3.5 shrink-0" />
      <span className="min-w-0 flex-1 truncate text-start">{t.shell.searchPlaceholder}</span>
      <kbd className="hidden shrink-0 rounded border border-slate-200 bg-white px-1.5 py-0.5 font-mono text-[10px] text-slate-600 xl:inline dark:border-white/10 dark:bg-white/10 dark:text-slate-200">
        {t.shell.commandPaletteShortcut}
      </kbd>
    </button>
  );

  return (
    <div className="min-h-screen bg-[#F8FAFC] dark:bg-[#060B13] text-slate-900 dark:text-[#F4F7FB] flex flex-col font-sans transition-colors duration-200">
      {/* Universal Topbar */}
      <header data-testid="app-header" className="sticky top-0 z-40 w-full min-w-0 border-b border-slate-200/80 bg-white/90 shadow-xs backdrop-blur-md dark:border-white/[0.08] dark:bg-[#0B132B]/90">
        <div className="grid w-full min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-2 px-2 py-2 sm:px-4 lg:grid-cols-[minmax(0,auto)_minmax(8rem,1fr)_auto] lg:px-6">
        <div className="flex min-w-0 items-center gap-1.5 sm:gap-2">
          {/* Mobile menu toggle */}
          <button
            onClick={() => setIsSidebarOpen((prev) => !prev)}
            aria-label={isSidebarOpen ? t.shell.collapseSidebar : t.shell.expandSidebar}
            className="lg:hidden shrink-0 p-1.5 sm:p-2 rounded-xl text-slate-500 hover:text-slate-800 dark:text-[#94A3B8] dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/[0.06] transition-colors"
          >
            {isSidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>

          {/* Official Avenqo brand logo or custom tenant logo for mobile/topbar */}
          <Link href="/dashboard" className="flex shrink-0 items-center gap-2 group">
            {showHeaderLogo ? (
              <img
                src={brandMark}
                alt={activeTenant || t.brand.name}
                className="w-8 h-8 rounded-xl object-contain border border-slate-200/80 dark:border-white/10 group-hover:scale-105 transition-transform"
              />
            ) : (
              <Image
                src="/brand/avenqo-icon.png"
                alt="Avenqo"
                width={32}
                height={32}
                className="rounded-xl object-contain shadow-xs shadow-blue-500/20 group-hover:scale-105 transition-transform"
              />
            )}
            <span className="hidden min-w-0 max-w-[8rem] truncate text-base font-extrabold tracking-tight text-slate-900 xl:inline-block dark:text-[#F4F7FB]">
              {showHeaderLogo ? activeTenant : t.brand.name}
            </span>
          </Link>

          {/* Tenant Indicator / Switcher Pill */}
          {organizations.length > 1 ? (
            <div className="relative min-w-0">
              <button
                onClick={() => setIsTenantMenuOpen((prev) => !prev)}
                className="flex h-9 min-w-0 items-center gap-1 rounded-xl border border-slate-200/60 bg-slate-100 px-1.5 text-xs font-semibold text-slate-700 sm:gap-2 sm:px-2 dark:border-white/[0.08] dark:bg-[#111D3D] dark:text-[#F4F7FB]"
              >
                <Building2 className="h-3.5 w-3.5 shrink-0 text-[#0076FF]" />
                <span className="max-w-[5.5rem] truncate sm:max-w-[8rem] lg:max-w-[11rem] xl:max-w-[14rem]" title={activeTenant}>{activeTenant}</span>
                <ChevronDown className="w-3 h-3 text-slate-400" />
              </button>

              {isTenantMenuOpen && (
                <div
                  className="absolute start-0 z-20 mt-2 w-[min(16rem,calc(100vw-1rem))] rounded-2xl border border-slate-200/80 bg-white p-1.5 text-xs shadow-xl dark:border-white/[0.12] dark:bg-[#0B132B]"
                  onMouseLeave={() => setIsTenantMenuOpen(false)}
                >
                  <div className="px-2.5 py-1.5 text-[10px] uppercase font-bold text-slate-400 dark:text-slate-500 tracking-wider">
                    {t.shell.switchTenant}
                  </div>
                  {organizations.map((org) => {
                    const isSelected = org.name === activeTenant;
                    return (
                      <button
                        key={org.id}
                        onClick={() => handleSwitchTenant(org)}
                        className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-left transition-colors ${
                          isSelected
                            ? "bg-blue-50 text-[#0076FF] dark:bg-[#172652] dark:text-[#00D4FF] font-semibold"
                            : "text-slate-700 dark:text-[#94A3B8] hover:bg-slate-50 dark:hover:bg-white/[0.04]"
                        }`}
                      >
                        <div className="truncate">
                          <div className="truncate font-medium">{org.name}</div>
                          {org.role && (
                            <div className="text-[10px] text-slate-400 dark:text-slate-500">
                              {org.role}
                            </div>
                          )}
                        </div>
                        {isSelected && <Check className="w-3.5 h-3.5 shrink-0 ml-2" />}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          ) : (
            <div className="flex h-9 min-w-0 items-center gap-1 rounded-xl border border-slate-200/60 bg-slate-100 px-1.5 text-xs font-semibold text-slate-700 sm:px-2 dark:border-white/[0.08] dark:bg-[#111D3D] dark:text-[#F4F7FB]">
              <Building2 className="h-3.5 w-3.5 shrink-0 text-[#0076FF]" />
              <span className="max-w-[5.5rem] truncate sm:max-w-[8rem] lg:max-w-[11rem] xl:max-w-[14rem]" title={activeTenant}>{activeTenant || catalog.company.connectionsLoading}</span>
            </div>
          )}

          <div data-testid="header-dataset-desktop" className="hidden min-w-0 md:block md:max-w-[9rem] lg:max-w-[12rem] xl:max-w-[16rem]">
            <GlobalSourceSelector />
          </div>
        </div>

        <div data-testid="header-search-desktop" className="hidden min-w-0 lg:block">
          {searchField("header-search-field")}
        </div>

        <div className="flex shrink-0 items-center justify-end gap-1">
          <button
            type="button"
            data-testid="header-search-mobile"
            onClick={openSearch}
            aria-label={t.shell.quickSearch}
            className="rounded-xl p-2 text-slate-600 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0076FF] md:hidden dark:text-[#C5D0E0] dark:hover:bg-white/[0.06]"
          >
            <Search size={18} />
          </button>

          <RegionLanguageSelector appearance="app" />

          {/* Theme Toggle (Dark / Light) */}
          <ThemeToggle />

          {/* Notification Center */}
          <div className="relative">
            <button
              onClick={() => setIsNotifMenuOpen((prev) => !prev)}
              aria-label={t.shell.notifications}
              className="relative p-2 rounded-xl text-slate-500 hover:text-slate-800 dark:text-[#94A3B8] dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/[0.06] transition-colors"
            >
              <Bell size={18} />
              {unreadNotifsCount > 0 && (
                <span className="absolute top-1.5 right-1.5 flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#0076FF] opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-[#0076FF]" />
                </span>
              )}
            </button>

            {isNotifMenuOpen && (
              <div
                className="absolute end-0 z-20 mt-2 w-[min(20rem,calc(100vw-1rem))] rounded-2xl border border-slate-200/80 bg-white p-3 text-xs shadow-xl dark:border-white/[0.12] dark:bg-[#0B132B]"
                onMouseLeave={() => setIsNotifMenuOpen(false)}
              >
                <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-100 dark:border-white/[0.06]">
                  <span className="font-bold text-slate-900 dark:text-[#F4F7FB]">
                    {t.shell.notifications}
                  </span>
                  <button
                    onClick={() => setUnreadNotifsCount(0)}
                    className="text-[10px] text-[#0076FF] hover:underline"
                  >
                    {t.shell.markAllRead}
                  </button>
                </div>
                <div className="p-3 text-center text-slate-500 dark:text-slate-400">
                  {t.shell.noNotifications}
                </div>
              </div>
            )}
          </div>

          {showCopilot && (
          <button
            type="button"
            aria-label={t.shell.copilotButton}
            aria-expanded={isCopilotOpen}
            aria-controls="avenqo-central-dialog"
            onClick={() => setIsCopilotOpen(true)}
            className="flex h-9 max-w-[9rem] items-center gap-1.5 rounded-xl bg-[#0076FF] px-2 text-xs font-semibold text-white hover:bg-[#158bff] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#00D4FF] xl:max-w-[12rem] xl:px-3"
          >
            <Sparkles className="h-3.5 w-3.5 shrink-0 text-[#00D4FF]" />
            <span className="hidden min-w-0 truncate xl:inline">{t.shell.copilotButton}</span>
          </button>
          )}
        </div>
        </div>
        {allows(["data:read", "data:manage", "retail:read"]) && (
          <div data-testid="header-dataset-mobile" className="min-w-0 px-2 pb-2 md:hidden sm:px-4">
            <GlobalSourceSelector wide />
          </div>
        )}
        <div data-testid="header-search-tablet" className="hidden min-w-0 px-2 pb-2 md:block lg:hidden sm:px-4">
          {searchField("header-search-tablet-field")}
        </div>
      </header>

      {/* Main Container */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar */}
        <aside
          className={`fixed inset-y-0 start-0 z-30 flex w-[min(100vw,18rem)] flex-col justify-between border-e border-slate-200/80 bg-white transition-transform duration-200 dark:border-white/[0.08] dark:bg-[#0B132B] lg:sticky lg:top-16 lg:z-20 lg:h-[calc(100vh-4rem)] lg:translate-x-0 ${
            isSidebarOpen ? "translate-x-0" : "-translate-x-full rtl:translate-x-full"
          }`}
        >
          {/* Top of Sidebar: Brand + Tagline (Mobile drawer only) */}
          <div className={`p-5 border-b border-slate-200/80 dark:border-white/[0.08] ${showSidebarLogo ? "" : "lg:hidden"}`}>
            <Link
              href="/dashboard"
              onClick={() => setIsSidebarOpen(false)}
              className="flex items-center gap-3 group"
            >
              {showSidebarLogo ? (
                <img
                  src={brandMark}
                  alt={activeTenant || t.brand.name}
                  className="w-9 h-9 rounded-xl object-contain border border-slate-200/80 dark:border-white/10 group-hover:scale-105 transition-transform"
                />
              ) : (
                <Image
                  src="/brand/avenqo-icon.png"
                  alt="Avenqo"
                  width={38}
                  height={38}
                  className="rounded-xl object-contain shadow-sm shadow-blue-500/25 group-hover:scale-105 transition-transform"
                />
              )}
              <div>
                <div className="font-extrabold tracking-tight text-slate-900 dark:text-[#F4F7FB] text-base leading-none truncate max-w-[150px]">
                  {showSidebarLogo ? activeTenant : t.brand.name}
                </div>
                <div className="text-[9px] font-bold text-slate-400 dark:text-[#94A3B8] tracking-widest uppercase mt-1">
                  {showSidebarLogo ? chrome.whiteLabel : t.brand.tagline}
                </div>
              </div>
            </Link>
          </div>

          {/* Navigation Links Scroll Area */}
          <div className="flex-1 overflow-y-auto p-3 space-y-6">
            {/* Core Modules */}
            <div>
              <div className="px-3 mb-2 text-[10px] uppercase font-bold tracking-wider text-slate-400 dark:text-slate-500">
                {t.shell.mainOperations}
              </div>
              {entitlementsStatus === "error" && (
                <div className="px-3 py-1.5 mb-2 mx-1 rounded-xl bg-amber-500/10 border border-amber-500/20 text-[11px] text-amber-700 dark:text-amber-400 flex items-center justify-between">
                  <span>{chrome.modulesOutOfSync}</span>
                  <button
                    onClick={() => void loadModuleEntitlements()}
                    className="text-[10px] underline font-bold hover:text-amber-800 dark:hover:text-amber-300"
                  >
                    {chrome.retry}
                  </button>
                </div>
              )}
              <nav className="space-y-1">
                {mainModules.map((item) => {
                  const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => {
                        setIsSidebarOpen(false);
                        if (item.href === "/voice") setIsCopilotOpen(false);
                      }}
                      className={`flex items-center justify-between px-3 py-2 rounded-xl text-xs font-semibold transition-colors ${
                        isActive
                          ? "bg-blue-50 text-blue-600 dark:bg-[#172652] dark:text-white shadow-2xs"
                          : "text-slate-600 hover:text-slate-900 hover:bg-slate-100 dark:text-[#94A3B8] dark:hover:text-[#F4F7FB] dark:hover:bg-[#111D3D]"
                      }`}
                    >
                      <div className="flex items-center gap-2.5">
                        <Icon className={`w-4 h-4 ${isActive ? "text-blue-600 dark:text-white" : "text-slate-400 dark:text-slate-500"}`} />
                        <span>{item.label}</span>
                      </div>
                    </Link>
                  );
                })}
              </nav>
            </div>

            {aiModules.length > 0 && (
            <div>
              <div className="px-3 mb-2 text-[10px] uppercase font-bold tracking-wider text-slate-400 dark:text-slate-500">
                {t.shell.artificialIntelligence}
              </div>
              <nav className="space-y-1">
                {aiModules.map((item) => {
                  const isActive = pathname === item.href;
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => setIsSidebarOpen(false)}
                      className={`flex items-center justify-between px-3 py-2 rounded-xl text-xs font-semibold transition-colors ${
                        isActive
                          ? "bg-blue-50 text-blue-600 dark:bg-[#172652] dark:text-white"
                          : "text-slate-600 hover:text-slate-900 hover:bg-slate-100 dark:text-[#94A3B8] dark:hover:text-[#F4F7FB] dark:hover:bg-[#111D3D]"
                      }`}
                    >
                      <div className="flex items-center gap-2.5">
                        <Icon className="w-4 h-4 text-slate-400 dark:text-slate-500" />
                        <span>{item.label}</span>
                      </div>
                      {item.badge && (
                        <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-md bg-blue-100 text-blue-700 dark:bg-[#0076FF]/20 dark:text-[#00D4FF]">
                          {item.badge}
                        </span>
                      )}
                    </Link>
                  );
                })}
              </nav>
            </div>
            )}

            {/* Platform & Integrations */}
            <div>
              <div className="px-3 mb-2 text-[10px] uppercase font-bold tracking-wider text-slate-400 dark:text-slate-500">
                {t.shell.platformData}
              </div>
              <nav className="space-y-1">
                {platformModules.map((item) => {
                  const isActive = pathname === item.href;
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => setIsSidebarOpen(false)}
                      className={`flex items-center justify-between px-3 py-2 rounded-xl text-xs font-semibold transition-colors ${
                        isActive
                          ? "bg-blue-50 text-blue-600 dark:bg-[#172652] dark:text-white"
                          : "text-slate-600 hover:text-slate-900 hover:bg-slate-100 dark:text-[#94A3B8] dark:hover:text-[#F4F7FB] dark:hover:bg-[#111D3D]"
                      }`}
                    >
                      <div className="flex items-center gap-2.5">
                        <Icon className="w-4 h-4 text-slate-400 dark:text-slate-500" />
                        <span>{item.label}</span>
                      </div>
                    </Link>
                  );
                })}
              </nav>
            </div>
          </div>

          {/* Bottom of Sidebar: AI Credits Gauge + User Profile */}
          <div className="p-3 border-t border-slate-200/80 dark:border-white/[0.08] space-y-3 bg-slate-50/50 dark:bg-[#060B13]/40">
            <CreditMeter
              remaining={aiCreditsRemaining}
              limit={aiCreditsLimit}
              monthlyAllocation={session.credits.monthlyAllocation}
              monthlyRemaining={session.credits.monthlyRemaining}
              purchasedRemaining={session.credits.purchasedRemaining}
              label={t.shell.aiCredits}
              upgradeLabel={t.shell.upgradePlan}
              error={session.creditError ? session.creditError.publicMessage ?? catalog.auth.genericError : undefined}
              loadingLabel={catalog.company.connectionsLoading}
              onRetry={() => { void session.reload(); }}
              retryLabel={t.common.retry}
            />

            {/* User Profile */}
            <div className="flex items-center justify-between px-2 py-1.5">
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-slate-200 dark:bg-white/[0.1] text-slate-800 dark:text-white font-bold text-xs">
                  {currentUser
                    ? `${(currentUser.first_name || "")[0] || ""}${(currentUser.last_name || "")[0] || ""}`.toUpperCase() || "U"
                    : "U"}
                </div>
                <div className="leading-tight min-w-0">
                  <div className="text-xs font-bold text-slate-900 dark:text-[#F4F7FB] truncate">
                    {currentUser ? `${currentUser.first_name} ${currentUser.last_name}` : chrome.userFallback}
                  </div>
                  <div className="text-[10px] text-slate-400 dark:text-[#94A3B8] truncate flex items-center gap-1">
                    <span>{currentUser?.job_title || currentUser?.role || chrome.memberFallback}</span>
                    {currentUser?.is_platform_admin && (
                      <span className="px-1 py-0.2 rounded bg-amber-500/20 text-amber-500 font-bold text-[8px]">
                        {t.shell.role}
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <button
                onClick={handleSignOut}
                aria-label={t.shell.signOut}
                className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/20 transition-colors cursor-pointer"
                title={t.shell.signOut}
              >
                <LogOut size={16} />
              </button>
            </div>
          </div>
        </aside>

        {/* Backdrop for mobile sidebar */}
        {isSidebarOpen && (
          <div
            className="fixed inset-0 z-20 bg-black/50 backdrop-blur-xs lg:hidden"
            onClick={() => setIsSidebarOpen(false)}
          />
        )}

        {/* Page Main Content Area */}
        <main className="min-w-0 flex-1 overflow-y-auto focus:outline-none p-4 pb-20 sm:p-6 sm:pb-20 md:pb-6 lg:p-8">
          {session.error ? <RequestFailure error={session.error} retry={() => { void session.reload(); }} />
            : session.identity ? <>
              {session.sourceError && <RequestFailure error={session.sourceError} retry={() => { void session.reload(); }} />}
              <WorkspaceReadinessGate>{children}</WorkspaceReadinessGate>
            </> : <div role="status">{catalog.company.connectionsLoading}</div>}
        </main>
      </div>

      {/* Mobile Bottom Navigation Bar (< 768px) */}
      <nav className="md:hidden fixed bottom-0 inset-x-0 z-30 h-14 bg-white/95 dark:bg-[#0B132B]/95 backdrop-blur-md border-t border-slate-200 dark:border-white/[0.08] flex items-center justify-around px-2">
        {allows(["data:read"]) && (
        <Link
          href="/dashboard"
          className={`flex min-w-0 flex-col items-center gap-0.5 text-[10px] font-semibold ${
            pathname === "/dashboard" ? "text-[#0076FF] dark:text-[#00D4FF]" : "text-slate-500 dark:text-[#94A3B8]"
          }`}
        >
          <LayoutDashboard size={18} />
          <span className="max-w-16 truncate">{t.navigation.dashboard}</span>
        </Link>
        )}
        {allows(["retail:read"]) && entitlementsStatus === "success" && activeModuleKeys?.includes("retail") ? (
        <Link
          href="/retail"
          className={`flex min-w-0 flex-col items-center gap-0.5 text-[10px] font-semibold ${
            pathname.startsWith("/retail") ? "text-[#0076FF] dark:text-[#00D4FF]" : "text-slate-500 dark:text-[#94A3B8]"
          }`}
        >
          <ShoppingBag size={18} />
          <span className="max-w-16 truncate">{t.navigation.retailAi}</span>
        </Link>
        ) : allows(["data:read"]) ? (
        <Link
          href="/data"
          className={`flex min-w-0 flex-col items-center gap-0.5 text-[10px] font-semibold ${
            pathname.startsWith("/data") ? "text-[#0076FF] dark:text-[#00D4FF]" : "text-slate-500 dark:text-[#94A3B8]"
          }`}
        >
          <Database size={18} />
          <span className="max-w-16 truncate">{t.navigation.dataHub}</span>
        </Link>
        ) : null}
        {showCopilot && (
        <button
          onClick={() => setIsCopilotOpen(true)}
          className="flex min-w-0 flex-col items-center gap-0.5 text-[10px] font-semibold text-[#0076FF] dark:text-[#00D4FF]"
        >
          <div className="p-1.5 rounded-full bg-blue-50 dark:bg-[#172652] shadow-2xs">
            <Sparkles size={16} />
          </div>
          <span className="max-w-16 truncate">{t.shell.copilotButton}</span>
        </button>
        )}
        {allows(["data:manage"]) && (
        <Link
          href="/connections"
          className={`flex min-w-0 flex-col items-center gap-0.5 text-[10px] font-semibold ${
            pathname.startsWith("/connections") ? "text-[#0076FF] dark:text-[#00D4FF]" : "text-slate-500 dark:text-[#94A3B8]"
          }`}
        >
          <Plug size={18} />
          <span className="max-w-16 truncate">{t.navigation.connections}</span>
        </Link>
        )}
        <button
          onClick={() => setIsSidebarOpen(true)}
          className="flex flex-col items-center gap-0.5 text-[10px] font-semibold text-slate-500 dark:text-[#94A3B8]"
        >
          <Menu size={18} />
          <span>{t.shell.workspace}</span>
        </button>
      </nav>

      {/* Global Command Palette */}
      <CommandPalette
        isOpen={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
        authorizedModuleKeys={entitlementsStatus === "success" ? activeModuleKeys : null}
        grantedPermissions={granted ?? null}
        t={t}
        onTriggerAction={(actionId) => {
          if (actionId === "open-copilot" && showCopilot) setIsCopilotOpen(true);
        }}
      />

      {/* Avenqo Copilot Assistant Drawer */}
      <AvenqoCopilot
        isOpen={isCopilotOpen}
        onClose={() => setIsCopilotOpen(false)}
        activeRoute={pathname}
        tenantName={activeTenant}
        t={t}
      />
    </div>
  );
}
