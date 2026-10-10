"use client";

import React, { useState, useEffect } from "react";
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
  Bot,
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
import { RequestFailure } from "@/components/ui/request-failure";
import { getApplicationCatalog } from "@/lib/i18n/generated-app-catalogs";

export interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const { locale } = useLocale();
  const t = getAppTranslations(locale);

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

  // Navigation modules
  const mainModules = [
    { href: "/dashboard", label: t.navigation.dashboard, icon: LayoutDashboard },
    { href: "/retail", label: t.navigation.retailAi, icon: ShoppingBag },
    { href: "/crm", label: t.navigation.crmAi, icon: Network },
    { href: "/accounting", label: t.navigation.accountingAi, icon: ReceiptText },
  ];

  const aiModules = [
    { href: "/marketing", label: t.navigation.marketingAi, icon: Megaphone },
    { href: "/voice", label: t.navigation.voiceAi, icon: Mic2 },
    { href: "/ocr", label: t.navigation.ocrAi, icon: FileScan },
    { href: "/legal", label: locale.startsWith("fr") ? "Legal AI" : "Legal AI", icon: FileScan },
    { href: "/chatbots", label: t.navigation.chatbotsAi, icon: MessagesSquare },
    { href: "/automations", label: t.navigation.automations, icon: Zap },
    { href: "/agents", label: t.navigation.agentsAi, icon: Bot, badge: undefined },
  ];

  const platformModules = [
    { href: "/employees", label: locale.startsWith("fr") ? "Équipe" : "Team", icon: Users },
    { href: "/marketplace", label: "Marketplace", icon: Layers },
    { href: "/connections", label: t.navigation.connections, icon: Plug },
    { href: "/integrations", label: t.navigation.integrations, icon: Globe },
    { href: "/data", label: t.navigation.dataHub, icon: Database },
    { href: "/billing", label: t.navigation.billing, icon: CreditCard },
    { href: "/workspace/modules", label: locale.startsWith("fr") ? "Mes modules" : "My modules", icon: Layers },
    { href: "/security", label: locale.startsWith("fr") ? "Centre de sécurité" : "Security center", icon: ShieldAlert },
    { href: "/trust", label: locale.startsWith("fr") ? "Centre de confiance" : "Trust center", icon: ShieldAlert },
    { href: "/onboarding", label: locale.startsWith("fr") ? "Démarrage accompagné" : "Guided setup", icon: Check },
    { href: "/settings", label: t.navigation.settings, icon: Settings },
  ];

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

  return (
    <div className="min-h-screen bg-[#F8FAFC] dark:bg-[#060B13] text-slate-900 dark:text-[#F4F7FB] flex flex-col font-sans transition-colors duration-200">
      {/* Universal Topbar */}
      <header className="sticky top-0 z-30 h-16 bg-white/80 dark:bg-[#0B132B]/80 backdrop-blur-md border-b border-slate-200/80 dark:border-white/[0.08] px-2 sm:px-4 lg:px-6 flex items-center justify-between gap-1 sm:gap-4">
        <div className="min-w-0 flex items-center gap-1 sm:gap-3 lg:gap-4">
          {/* Mobile menu toggle */}
          <button
            onClick={() => setIsSidebarOpen((prev) => !prev)}
            aria-label={isSidebarOpen ? t.shell.collapseSidebar : t.shell.expandSidebar}
            className="lg:hidden shrink-0 p-1.5 sm:p-2 rounded-xl text-slate-500 hover:text-slate-800 dark:text-[#94A3B8] dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/[0.06] transition-colors"
          >
            {isSidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>

          {/* Official Avenqo brand logo for mobile/topbar */}
          <Link href="/dashboard" className="flex items-center gap-2.5 group">
            <Image
              src="/brand/avenqo-icon.png"
              alt="Avenqo"
              width={32}
              height={32}
              className="rounded-xl object-contain shadow-xs shadow-blue-500/20 group-hover:scale-105 transition-transform"
            />
            <span className="font-extrabold tracking-tight text-slate-900 dark:text-[#F4F7FB] text-base hidden sm:inline-block">
              {t.brand.name}
            </span>
          </Link>

          {/* Tenant Indicator / Switcher Pill */}
          {organizations.length > 1 ? (
            <div className="relative">
              <button
                onClick={() => setIsTenantMenuOpen((prev) => !prev)}
                className="flex items-center gap-1 sm:gap-2 px-1.5 sm:px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-[#111D3D] hover:bg-slate-200/80 dark:hover:bg-[#172652] text-xs font-semibold text-slate-700 dark:text-[#F4F7FB] border border-slate-200/60 dark:border-white/[0.08] transition-colors cursor-pointer"
              >
                <Building2 className="w-3.5 h-3.5 text-[#0076FF]" />
                <span className="max-w-[30px] sm:max-w-[120px] truncate" title={activeTenant}>{activeTenant}</span>
                <ChevronDown className="w-3 h-3 text-slate-400" />
              </button>

              {isTenantMenuOpen && (
                <div
                  className="absolute left-0 mt-2 w-56 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.12] shadow-xl p-1.5 z-50 text-xs animate-in fade-in zoom-in-95"
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
            <div className="min-w-0 flex items-center gap-1 sm:gap-2 px-1.5 sm:px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-[#111D3D] text-xs font-semibold text-slate-700 dark:text-[#F4F7FB] border border-slate-200/60 dark:border-white/[0.08]">
              <Building2 className="w-3.5 h-3.5 text-[#0076FF]" />
              <span className="max-w-[30px] sm:max-w-[140px] truncate" title={activeTenant}>{activeTenant || catalog.company.connectionsLoading}</span>
            </div>
          )}

          {/* Dynamic Active Data Sources Pill (Only shown if live connection exists) */}
          <GlobalSourceSelector />
        </div>

        {/* Center: Command Palette Input Trigger */}
        <div className="flex-1 max-w-md hidden md:block">
          <button
            onClick={() => setIsCommandPaletteOpen(true)}
            className="w-full flex items-center justify-between px-3.5 py-2 rounded-xl bg-slate-100 dark:bg-[#111D3D] hover:bg-slate-200/60 dark:hover:bg-[#172652] border border-slate-200/60 dark:border-white/[0.08] text-xs text-slate-400 dark:text-[#94A3B8] transition-colors"
          >
            <div className="flex items-center gap-2">
              <Search className="w-3.5 h-3.5" />
              <span>{t.shell.searchPlaceholder}</span>
            </div>
            <kbd className="px-1.5 py-0.5 rounded bg-white dark:bg-white/[0.08] border border-slate-200 dark:border-white/[0.1] text-[10px] font-mono text-slate-500 dark:text-slate-400 shadow-2xs">
              {t.shell.commandPaletteShortcut}
            </kbd>
          </button>
        </div>

        {/* Right Controls */}
        <div className="shrink-0 flex items-center gap-0 sm:gap-2 lg:gap-3">
          {/* Mobile search trigger */}
          <button
            onClick={() => setIsCommandPaletteOpen(true)}
            aria-label={t.shell.quickSearch}
            className="md:hidden p-2 rounded-xl text-slate-500 hover:text-slate-800 dark:text-[#94A3B8] dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/[0.06] transition-colors"
          >
            <Search size={18} />
          </button>

          {/* 44-Language Selector */}
          <RegionLanguageSelector />

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
                className="absolute right-0 mt-2 w-80 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.12] shadow-2xl p-3 z-50 text-xs animate-in fade-in zoom-in-95"
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

          {/* Avenqo Copilot Trigger Button */}
          <button
            type="button"
            aria-label={t.shell.copilotButton}
            aria-expanded={isCopilotOpen}
            aria-controls="avenqo-central-dialog"
            onClick={() => setIsCopilotOpen(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-gradient-to-r from-[#0076FF] to-[#005bd3] hover:from-[#158bff] hover:to-[#0076FF] text-white text-xs font-semibold shadow-xs shadow-blue-500/20 transition-all duration-150"
          >
            <Sparkles className="w-3.5 h-3.5 text-[#00D4FF]" />
            <span className="hidden sm:inline">{t.shell.copilotButton}</span>
          </button>
        </div>
      </header>

      {/* Main Container */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar */}
        <aside
          className={`fixed inset-y-0 left-0 z-40 w-64 bg-white dark:bg-[#0B132B] border-r border-slate-200/80 dark:border-white/[0.08] flex flex-col justify-between transition-transform duration-200 lg:static lg:translate-x-0 ${
            isSidebarOpen ? "translate-x-0" : "-translate-x-full"
          }`}
        >
          {/* Top of Sidebar: Brand + Tagline */}
          <div className="p-5 border-b border-slate-200/80 dark:border-white/[0.08]">
            <Link
              href="/dashboard"
              onClick={() => setIsSidebarOpen(false)}
              className="flex items-center gap-3 group"
            >
              <Image
                src="/brand/avenqo-icon.png"
                alt="Avenqo"
                width={38}
                height={38}
                className="rounded-xl object-contain shadow-sm shadow-blue-500/25 group-hover:scale-105 transition-transform"
              />
              <div>
                <div className="font-extrabold tracking-tight text-slate-900 dark:text-[#F4F7FB] text-base leading-none">
                  {t.brand.name}
                </div>
                <div className="text-[9px] font-bold text-slate-400 dark:text-[#94A3B8] tracking-widest uppercase mt-1">
                  {t.brand.tagline}
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
                          ? "bg-blue-50 text-[#0076FF] dark:bg-[#172652] dark:text-[#00D4FF] shadow-2xs"
                          : "text-slate-600 hover:text-slate-900 hover:bg-slate-100 dark:text-[#94A3B8] dark:hover:text-[#F4F7FB] dark:hover:bg-[#111D3D]"
                      }`}
                    >
                      <div className="flex items-center gap-2.5">
                        <Icon className={`w-4 h-4 ${isActive ? "text-[#0076FF] dark:text-[#00D4FF]" : "text-slate-400 dark:text-slate-500"}`} />
                        <span>{item.label}</span>
                      </div>
                    </Link>
                  );
                })}
              </nav>
            </div>

            {/* AI Specialized Modules */}
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
                          ? "bg-blue-50 text-[#0076FF] dark:bg-[#172652] dark:text-[#00D4FF]"
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
                          ? "bg-blue-50 text-[#0076FF] dark:bg-[#172652] dark:text-[#00D4FF]"
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
                    {currentUser ? `${currentUser.first_name} ${currentUser.last_name}` : "Utilisateur"}
                  </div>
                  <div className="text-[10px] text-slate-400 dark:text-[#94A3B8] truncate flex items-center gap-1">
                    <span>{currentUser?.job_title || currentUser?.role || "Membre"}</span>
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
            className="fixed inset-0 z-30 bg-black/50 lg:hidden backdrop-blur-xs"
            onClick={() => setIsSidebarOpen(false)}
          />
        )}

        {/* Page Main Content Area */}
        <main className="min-w-0 flex-1 overflow-y-auto focus:outline-none p-4 sm:p-6 lg:p-8">
          {session.error ? <RequestFailure error={session.error} retry={() => { void session.reload(); }} />
            : session.identity ? <>
              {session.sourceError && <RequestFailure error={session.sourceError} retry={() => { void session.reload(); }} />}
              {children}
            </> : <div role="status">{catalog.company.connectionsLoading}</div>}
        </main>
      </div>

      {/* Mobile Bottom Navigation Bar (< 768px) */}
      <nav className="md:hidden fixed bottom-0 inset-x-0 z-30 h-14 bg-white/95 dark:bg-[#0B132B]/95 backdrop-blur-md border-t border-slate-200 dark:border-white/[0.08] flex items-center justify-around px-2">
        <Link
          href="/dashboard"
          className={`flex flex-col items-center gap-0.5 text-[10px] font-semibold ${
            pathname === "/dashboard" ? "text-[#0076FF] dark:text-[#00D4FF]" : "text-slate-500 dark:text-[#94A3B8]"
          }`}
        >
          <LayoutDashboard size={18} />
          <span>{t.navigation.dashboard}</span>
        </Link>
        <Link
          href="/retail"
          className={`flex flex-col items-center gap-0.5 text-[10px] font-semibold ${
            pathname.startsWith("/retail") ? "text-[#0076FF] dark:text-[#00D4FF]" : "text-slate-500 dark:text-[#94A3B8]"
          }`}
        >
          <ShoppingBag size={18} />
          <span>{t.navigation.retailAi}</span>
        </Link>
        <button
          onClick={() => setIsCopilotOpen(true)}
          className="flex flex-col items-center gap-0.5 text-[10px] font-semibold text-[#0076FF] dark:text-[#00D4FF]"
        >
          <div className="p-1.5 rounded-full bg-blue-50 dark:bg-[#172652] shadow-2xs">
            <Sparkles size={16} />
          </div>
          <span>{t.shell.copilotButton}</span>
        </button>
        <Link
          href="/integrations"
          className={`flex flex-col items-center gap-0.5 text-[10px] font-semibold ${
            pathname === "/integrations" ? "text-[#0076FF] dark:text-[#00D4FF]" : "text-slate-500 dark:text-[#94A3B8]"
          }`}
        >
          <Plug size={18} />
          <span>{t.navigation.connections}</span>
        </Link>
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
        t={t}
        onTriggerAction={(actionId) => {
          if (actionId === "open-copilot") setIsCopilotOpen(true);
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
