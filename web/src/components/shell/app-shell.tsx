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
} from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";
import { RegionLanguageSelector } from "@/components/region-language-selector";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
import { CommandPalette } from "./command-palette";
import { AvenqoCopilot } from "./avenqo-copilot";

export interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const { locale } = useLocale();
  const t = getAppTranslations(locale);

  interface UserProfile {
    id: string;
    first_name: string;
    last_name: string;
    job_title?: string;
    role: string;
    is_platform_admin: boolean;
  }

  interface OrganizationItem {
    id: string;
    name: string;
    slug: string;
    subscription_plan: string;
    role: string;
    is_current: boolean;
  }

  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [isCopilotOpen, setIsCopilotOpen] = useState(false);
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null);
  const [activeTenant, setActiveTenant] = useState<string>("");
  const [organizations, setOrganizations] = useState<OrganizationItem[]>([]);
  const [isTenantMenuOpen, setIsTenantMenuOpen] = useState(false);
  const [isNotifMenuOpen, setIsNotifMenuOpen] = useState(false);
  const [unreadNotifsCount, setUnreadNotifsCount] = useState(2);

  // Dynamic AI credit meter state
  const [aiCreditsUsed, setAiCreditsUsed] = useState<number>(0);
  const [aiCreditsLimit, setAiCreditsLimit] = useState<number>(6500);
  const creditPercent = Math.min(100, Math.round((aiCreditsUsed / (aiCreditsLimit || 1)) * 100));

  useEffect(() => {
    async function loadIdentity() {
      try {
        const token = typeof window !== "undefined" ? localStorage.getItem("avenqo_token") || localStorage.getItem("avenqo_access_token") : null;
        if (!token) return;
        const res = await fetch("/api/v1/auth/me", {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const data = await res.json();
          setCurrentUser(data.user);
          setActiveTenant(data.company?.name || "");
          if (Array.isArray(data.organizations)) {
            setOrganizations(data.organizations);
          }
        }
        const credRes = await fetch("/api/v1/billing/ai-credits", {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (credRes.ok) {
          const credData = await credRes.json();
          setAiCreditsUsed(credData.monthly_used || 0);
          setAiCreditsLimit(credData.monthly_allocation || credData.total_available || 6500);
        }
      } catch {}
    }
    loadIdentity();
  }, []);

  const handleSwitchTenant = async (org: OrganizationItem) => {
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("avenqo_token") || localStorage.getItem("avenqo_access_token") : null;
      const res = await fetch("/api/v1/auth/switch-tenant", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ company_id: org.id }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.access_token) {
          localStorage.setItem("avenqo_token", data.access_token);
          localStorage.setItem("avenqo_access_token", data.access_token);
        }
        setActiveTenant(org.name);
        setIsTenantMenuOpen(false);
        window.location.reload();
      }
    } catch {}
  };

  const handleSignOut = async () => {
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("avenqo_token") || localStorage.getItem("avenqo_access_token") : null;
      if (token) {
        await fetch("/api/v1/auth/logout", {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        });
      }
    } catch {}
    localStorage.removeItem("avenqo_token");
    localStorage.removeItem("avenqo_access_token");
    localStorage.removeItem("avenqo_refresh_token");
    window.location.href = "/login";
  };

  // Navigation modules
  const mainModules = [
    { href: "/dashboard", label: t.navigation.dashboard, icon: LayoutDashboard },
    { href: "/retail", label: t.navigation.retailAi, icon: ShoppingBag },
    { href: "/crm", label: t.navigation.crmAi, icon: Network },
    { href: "/accounting", label: t.navigation.accountingAi, icon: ReceiptText },
  ];

  const aiModules = [
    { href: "/marketing", label: t.navigation.marketingAi, icon: Megaphone, badge: "AI" },
    { href: "/voice", label: t.navigation.voiceAi, icon: Mic2, badge: "AI" },
    { href: "/ocr", label: t.navigation.ocrAi, icon: FileScan, badge: "AI" },
    { href: "/chatbots", label: t.navigation.chatbotsAi, icon: MessagesSquare, badge: "AI" },
    { href: "/automations", label: t.navigation.automations, icon: Zap },
    { href: "/agents", label: t.navigation.agentsAi, icon: Bot, badge: "Pro" },
  ];

  const platformModules = [
    { href: "/integrations", label: t.navigation.integrations, icon: Plug },
    { href: "/data", label: t.navigation.dataHub, icon: Database },
    { href: "/billing", label: t.navigation.billing || "Facturation", icon: CreditCard },
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
      <header className="sticky top-0 z-30 h-16 bg-white/80 dark:bg-[#0B132B]/80 backdrop-blur-md border-b border-slate-200/80 dark:border-white/[0.08] px-4 lg:px-6 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 lg:gap-4">
          {/* Mobile menu toggle */}
          <button
            onClick={() => setIsSidebarOpen((prev) => !prev)}
            aria-label="Basculer la barre latérale"
            className="lg:hidden p-2 rounded-xl text-slate-500 hover:text-slate-800 dark:text-[#94A3B8] dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/[0.06] transition-colors"
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

          {/* Tenant Switcher Pill */}
          <div className="relative">
            <button
              onClick={() => setIsTenantMenuOpen((prev) => !prev)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-[#111D3D] hover:bg-slate-200/80 dark:hover:bg-[#172652] text-xs font-semibold text-slate-700 dark:text-[#F4F7FB] border border-slate-200/60 dark:border-white/[0.08] transition-colors"
            >
              <Building2 className="w-3.5 h-3.5 text-[#0076FF]" />
              <span className="max-w-[120px] truncate">{activeTenant}</span>
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
                {organizations.length === 0 ? (
                  <div className="px-3 py-2 text-slate-400 dark:text-slate-500 text-[11px]">
                    {activeTenant || "Aucune organisation"}
                  </div>
                ) : (
                  organizations.map((org) => {
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
                  })
                )}
              </div>
            )}
          </div>

          {/* Active Data Sources Pill */}
          <div className="hidden sm:flex items-center gap-1.5">
            <div className="flex items-center gap-1 px-2.5 py-1.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/60 text-[10px] font-bold text-emerald-700 dark:text-emerald-400">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-500 opacity-75" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
              </span>
              <span>WooCommerce</span>
            </div>
            <div className="flex items-center gap-1 px-2.5 py-1.5 rounded-xl bg-orange-50 dark:bg-orange-950/30 border border-orange-200 dark:border-orange-800/60 text-[10px] font-bold text-orange-700 dark:text-orange-400">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-orange-500 opacity-75" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-orange-500" />
              </span>
              <span>Etsy</span>
            </div>
          </div>
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
        <div className="flex items-center gap-2 lg:gap-3">
          {/* Mobile search trigger */}
          <button
            onClick={() => setIsCommandPaletteOpen(true)}
            aria-label="Recherche rapide"
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
                    Tout marquer comme lu
                  </button>
                </div>
                <div className="space-y-2">
                  <div className="p-2 rounded-xl bg-blue-50/60 dark:bg-[#111D3D] border border-blue-100 dark:border-white/[0.06]">
                    <div className="font-semibold text-slate-900 dark:text-[#F4F7FB] flex items-center justify-between">
                      <span>Synchronisation WooCommerce</span>
                      <span className="text-[10px] text-slate-400">14m</span>
                    </div>
                    <p className="mt-0.5 text-slate-600 dark:text-[#94A3B8] text-[11px]">
                      14 produits réconciliés avec succès sur le registre normalisé.
                    </p>
                  </div>
                  <div className="p-2 rounded-xl bg-amber-50/60 dark:bg-amber-950/20 border border-amber-100 dark:border-amber-900/30">
                    <div className="font-semibold text-amber-900 dark:text-amber-200 flex items-center justify-between">
                      <span>Alerte Réapprovisionnement</span>
                      <span className="text-[10px] text-slate-400">1h</span>
                    </div>
                    <p className="mt-0.5 text-amber-700/90 dark:text-amber-300/80 text-[11px]">
                      Stock bas identifié sur Avenqo Headphones X (30 unités restantes).
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Avenqo Copilot Trigger Button */}
          <button
            onClick={() => setIsCopilotOpen((prev) => !prev)}
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
                  AI FOR A SMARTER FUTURE
                </div>
              </div>
            </Link>
          </div>

          {/* Navigation Links Scroll Area */}
          <div className="flex-1 overflow-y-auto p-3 space-y-6">
            {/* Core Modules */}
            <div>
              <div className="px-3 mb-2 text-[10px] uppercase font-bold tracking-wider text-slate-400 dark:text-slate-500">
                Opérations Principales
              </div>
              <nav className="space-y-1">
                {mainModules.map((item) => {
                  const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => setIsSidebarOpen(false)}
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
                Intelligence Artificielle
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
                Plateforme & Données
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
            {/* AI Credits Consumption Meter */}
            <div className="p-3 rounded-2xl bg-white dark:bg-[#111D3D] border border-slate-200/80 dark:border-white/[0.08] shadow-2xs">
              <div className="flex items-center justify-between text-xs mb-1.5">
                <div className="flex items-center gap-1.5 font-bold text-slate-900 dark:text-[#F4F7FB]">
                  <Sparkles className="w-3.5 h-3.5 text-[#0076FF]" />
                  <span>{t.shell.aiCredits}</span>
                </div>
                <span className="text-[11px] font-semibold text-slate-500 dark:text-[#94A3B8]">
                  {creditPercent}%
                </span>
              </div>
              <div className="h-1.5 w-full rounded-full bg-slate-100 dark:bg-white/[0.08] overflow-hidden mb-1.5">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-[#0076FF] to-[#00D4FF] transition-all duration-300"
                  style={{ width: `${creditPercent}%` }}
                />
              </div>
              <div className="flex items-center justify-between text-[10px] text-slate-400 dark:text-slate-500">
                <span>{aiCreditsUsed.toLocaleString()} / {aiCreditsLimit.toLocaleString()}</span>
                <Link href="/pricing" className="text-[#0076FF] hover:underline font-medium">
                  {t.shell.upgradePlan}
                </Link>
              </div>
            </div>

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
                        ADMIN
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
        <main className="flex-1 overflow-y-auto focus:outline-none p-4 sm:p-6 lg:p-8">
          {children}
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
          <span>Dashboard</span>
        </Link>
        <Link
          href="/retail"
          className={`flex flex-col items-center gap-0.5 text-[10px] font-semibold ${
            pathname.startsWith("/retail") ? "text-[#0076FF] dark:text-[#00D4FF]" : "text-slate-500 dark:text-[#94A3B8]"
          }`}
        >
          <ShoppingBag size={18} />
          <span>Retail AI</span>
        </Link>
        <button
          onClick={() => setIsCopilotOpen(true)}
          className="flex flex-col items-center gap-0.5 text-[10px] font-semibold text-[#0076FF] dark:text-[#00D4FF]"
        >
          <div className="p-1.5 rounded-full bg-blue-50 dark:bg-[#172652] shadow-2xs">
            <Sparkles size={16} />
          </div>
          <span>Copilot</span>
        </button>
        <Link
          href="/integrations"
          className={`flex flex-col items-center gap-0.5 text-[10px] font-semibold ${
            pathname === "/integrations" ? "text-[#0076FF] dark:text-[#00D4FF]" : "text-slate-500 dark:text-[#94A3B8]"
          }`}
        >
          <Plug size={18} />
          <span>Connecteurs</span>
        </Link>
        <button
          onClick={() => setIsSidebarOpen(true)}
          className="flex flex-col items-center gap-0.5 text-[10px] font-semibold text-slate-500 dark:text-[#94A3B8]"
        >
          <Menu size={18} />
          <span>Menu</span>
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
