"use client";

import React, { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import {
  Search,
  LayoutDashboard,
  ShoppingBag,
  Network,
  ReceiptText,
  FileScan,
  Mic2,
  Cpu,
  Bot,
  Plug,
  Database,
  Settings,
  Sparkles,
  RefreshCw,
  FileText,
  HelpCircle,
  ArrowRight,
  Command,
  X,
  Users,
  Calendar,
  Wrench,
  TrendingUp,
  UserCheck,
} from "lucide-react";
import type { AppTranslations } from "@/lib/i18n/app-dictionary";
import { getAuthHeaders } from "@/lib/api-headers";

export interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  t: AppTranslations;
  onTriggerAction?: (actionId: string) => void;
}

export function CommandPalette({
  isOpen,
  onClose,
  t,
  onTriggerAction,
}: CommandPaletteProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [crmResults, setCrmResults] = useState<any[]>([]);

  useEffect(() => {
    if (!query.trim() || query.length < 2) {
      setCrmResults([]);
      return;
    }

    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/v1/crm/search?q=${encodeURIComponent(query)}&limit=6`, {
          headers: getAuthHeaders(),
        });
        if (res.ok) {
          const data = await res.json();
          const results = data.results || data;
          const items: any[] = [];

          // Clients
          if (results.clients && Array.isArray(results.clients)) {
            results.clients.forEach((c: any) => {
              items.push({
                id: `crm-client-${c.id}`,
                title: c.title || `${c.first_name || ""} ${c.last_name || ""}`,
                subtitle: c.subtitle || c.email || c.phone,
                group: "CRM — Clients",
                icon: <Users className="w-4 h-4 text-[#0076FF]" />,
                onSelect: () => {
                  if (typeof window !== "undefined") {
                    window.dispatchEvent(
                      new CustomEvent("crm:select-entity", { detail: { type: "client", id: c.id } })
                    );
                  }
                  router.push("/crm");
                  onClose();
                },
              });
            });
          }

          // Appointments
          if (results.appointments && Array.isArray(results.appointments)) {
            results.appointments.forEach((a: any) => {
              items.push({
                id: `crm-app-${a.id}`,
                title: a.title || "Rendez-vous",
                subtitle: a.subtitle || a.client_name,
                group: "CRM — Rendez-vous",
                icon: <Calendar className="w-4 h-4 text-[#00D4FF]" />,
                onSelect: () => {
                  if (typeof window !== "undefined") {
                    window.dispatchEvent(
                      new CustomEvent("crm:select-entity", { detail: { type: "appointment", id: a.id } })
                    );
                  }
                  router.push("/crm");
                  onClose();
                },
              });
            });
          }

          // Services
          if (results.services && Array.isArray(results.services)) {
            results.services.forEach((s: any) => {
              items.push({
                id: `crm-srv-${s.id}`,
                title: s.title || s.name,
                subtitle: s.subtitle || `${s.duration_minutes || 30} min`,
                group: "CRM — Prestations & Services",
                icon: <Wrench className="w-4 h-4 text-emerald-400" />,
                onSelect: () => {
                  router.push("/crm");
                  onClose();
                },
              });
            });
          }

          // Employees
          if (results.employees && Array.isArray(results.employees)) {
            results.employees.forEach((e: any) => {
              items.push({
                id: `crm-emp-${e.id}`,
                title: e.title || `${e.first_name || ""} ${e.last_name || ""}`,
                subtitle: e.subtitle || e.email || e.phone,
                group: "CRM — Collaborateurs",
                icon: <UserCheck className="w-4 h-4 text-indigo-400" />,
                onSelect: () => {
                  router.push("/crm");
                  onClose();
                },
              });
            });
          }

          // Notes
          if (results.notes && Array.isArray(results.notes)) {
            results.notes.forEach((n: any) => {
              items.push({
                id: `crm-note-${n.id}`,
                title: n.title || "Note client",
                subtitle: n.subtitle || n.content,
                group: "CRM — Notes",
                icon: <FileText className="w-4 h-4 text-amber-400" />,
                onSelect: () => {
                  router.push("/crm");
                  onClose();
                },
              });
            });
          }

          // Opportunities / Deals
          if (results.opportunities && Array.isArray(results.opportunities)) {
            results.opportunities.forEach((o: any) => {
              items.push({
                id: `crm-opp-${o.id}`,
                title: o.title,
                subtitle: o.subtitle || `${o.amount || 0} $`,
                group: "CRM — Pipelines & Opportunités",
                icon: <TrendingUp className="w-4 h-4 text-violet-400" />,
                onSelect: () => {
                  if (typeof window !== "undefined") {
                    window.dispatchEvent(
                      new CustomEvent("crm:select-entity", { detail: { type: "opportunity", id: o.id } })
                    );
                  }
                  router.push("/crm");
                  onClose();
                },
              });
            });
          }

          setCrmResults(items);
        }
      } catch {
        // Silently fail
      }
    }, 180);

    return () => clearTimeout(timer);
  }, [query, router, onClose]);

  const items = useMemo(() => {
    const pages = [
      {
        id: "page-dashboard",
        title: t.navigation.dashboard,
        group: t.commandPalette.pagesGroup,
        icon: <LayoutDashboard className="w-4 h-4 text-[#0076FF]" />,
        onSelect: () => {
          router.push("/dashboard");
          onClose();
        },
      },
      {
        id: "page-retail",
        title: t.navigation.retailAi,
        group: t.commandPalette.pagesGroup,
        icon: <ShoppingBag className="w-4 h-4 text-[#00D4FF]" />,
        onSelect: () => {
          router.push("/retail");
          onClose();
        },
      },
      {
        id: "page-crm",
        title: t.navigation.crmAi,
        group: t.commandPalette.pagesGroup,
        icon: <Network className="w-4 h-4 text-violet-400" />,
        onSelect: () => {
          router.push("/crm");
          onClose();
        },
      },
      {
        id: "page-accounting",
        title: t.navigation.accountingAi,
        group: t.commandPalette.pagesGroup,
        icon: <ReceiptText className="w-4 h-4 text-emerald-400" />,
        onSelect: () => {
          router.push("/accounting");
          onClose();
        },
      },
      {
        id: "page-integrations",
        title: t.navigation.integrations,
        group: t.commandPalette.pagesGroup,
        icon: <Plug className="w-4 h-4 text-amber-400" />,
        onSelect: () => {
          router.push("/integrations");
          onClose();
        },
      },
      {
        id: "page-data",
        title: t.navigation.dataHub,
        group: t.commandPalette.pagesGroup,
        icon: <Database className="w-4 h-4 text-cyan-400" />,
        onSelect: () => {
          router.push("/data");
          onClose();
        },
      },
      {
        id: "page-settings",
        title: t.navigation.settings,
        group: t.commandPalette.pagesGroup,
        icon: <Settings className="w-4 h-4 text-slate-400" />,
        onSelect: () => {
          router.push("/settings");
          onClose();
        },
      },
    ];

    const actions = [
      {
        id: "action-sync",
        title: t.commandPalette.actionSync,
        group: t.commandPalette.actionsGroup,
        icon: <RefreshCw className="w-4 h-4 text-[#0076FF]" />,
        onSelect: () => {
          onClose();
          onTriggerAction?.("sync");
        },
      },
      {
        id: "action-clean-data",
        title: t.commandPalette.actionCleanData,
        group: t.commandPalette.actionsGroup,
        icon: <Database className="w-4 h-4 text-emerald-400" />,
        onSelect: () => {
          router.push("/retail");
          onClose();
          onTriggerAction?.("clean-data");
        },
      },
      {
        id: "action-generate-report",
        title: t.commandPalette.actionGenerateReport,
        group: t.commandPalette.actionsGroup,
        icon: <FileText className="w-4 h-4 text-amber-400" />,
        onSelect: () => {
          onClose();
          onTriggerAction?.("report");
        },
      },
      {
        id: "action-ask-copilot",
        title: t.commandPalette.actionAskCopilot,
        group: t.commandPalette.actionsGroup,
        icon: <Sparkles className="w-4 h-4 text-[#00D4FF]" />,
        onSelect: () => {
          onClose();
          onTriggerAction?.("open-copilot");
        },
      },
    ];

    const integrations = [
      {
        id: "int-shopify",
        title: "Shopify (Commerce Sync)",
        group: t.commandPalette.integrationsGroup,
        icon: <Plug className="w-4 h-4 text-emerald-400" />,
        onSelect: () => {
          router.push("/integrations");
          onClose();
        },
      },
      {
        id: "int-woocommerce",
        title: "WooCommerce (Public Store API)",
        group: t.commandPalette.integrationsGroup,
        icon: <Plug className="w-4 h-4 text-purple-400" />,
        onSelect: () => {
          router.push("/integrations");
          onClose();
        },
      },
      {
        id: "int-stripe",
        title: "Stripe (Subscriptions & Payouts)",
        group: t.commandPalette.integrationsGroup,
        icon: <Plug className="w-4 h-4 text-blue-400" />,
        onSelect: () => {
          router.push("/billing");
          onClose();
        },
      },
    ];

    const all = [...pages, ...actions, ...integrations];

    if (!query.trim()) return all;
    const lower = query.toLowerCase();
    const filtered = all.filter(
      (item) =>
        item.title.toLowerCase().includes(lower) ||
        item.group.toLowerCase().includes(lower)
    );
    return [...crmResults, ...filtered];
  }, [query, router, onClose, onTriggerAction, t, crmResults]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (isOpen) {
          onClose();
        } else {
          // Open trigger can be handled from caller, but let's toggle if already attached
        }
      }

      if (!isOpen) return;

      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((prev) => (prev + 1) % (items.length || 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((prev) => (prev - 1 + items.length) % (items.length || 1));
      } else if (e.key === "Enter" && items[selectedIndex]) {
        e.preventDefault();
        items[selectedIndex].onSelect();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose, items, selectedIndex]);

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t.commandPalette.title}
      className="fixed inset-0 z-50 flex items-start justify-center pt-20 p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-150"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.12] shadow-2xl overflow-hidden text-slate-900 dark:text-[#F4F7FB] animate-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search header */}
        <div className="flex items-center px-4 py-3.5 border-b border-slate-200/80 dark:border-white/[0.08] gap-3">
          <Search className="w-5 h-5 text-slate-400 dark:text-[#94A3B8]" />
          <input
            autoFocus
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t.commandPalette.placeholder}
            className="flex-1 bg-transparent border-none outline-none text-sm text-slate-900 dark:text-[#F4F7FB] placeholder-slate-400 dark:placeholder-slate-500 font-medium"
          />
          <button
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-white/[0.08] text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Results list */}
        <div className="max-h-80 overflow-y-auto p-2 divide-y divide-slate-100 dark:divide-white/[0.04]">
          {items.length === 0 ? (
            <div className="p-8 text-center text-sm text-slate-500 dark:text-[#94A3B8]">
              {t.commandPalette.noResults}
            </div>
          ) : (
            items.map((item, index) => {
              const isSelected = index === selectedIndex;
              return (
                <div
                  key={item.id}
                  onClick={item.onSelect}
                  onMouseEnter={() => setSelectedIndex(index)}
                  className={`flex items-center justify-between px-3.5 py-2.5 rounded-xl cursor-pointer transition-colors ${
                    isSelected
                      ? "bg-blue-50 dark:bg-[#172652] text-slate-900 dark:text-[#F4F7FB]"
                      : "hover:bg-slate-50 dark:hover:bg-white/[0.04] text-slate-700 dark:text-[#94A3B8]"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-100 dark:bg-[#111D3D]">
                      {item.icon}
                    </div>
                    <div>
                      <div className="text-sm font-medium">{item.title}</div>
                      <div className="text-[11px] text-slate-400 dark:text-slate-500">
                        {item.group}
                      </div>
                    </div>
                  </div>
                  <ArrowRight
                    className={`w-4 h-4 text-slate-400 transition-transform ${
                      isSelected ? "translate-x-0.5 text-[#0076FF]" : "opacity-0"
                    }`}
                  />
                </div>
              );
            })
          )}
        </div>

        {/* Footer shortcuts */}
        <div className="px-4 py-2.5 bg-slate-50/80 dark:bg-[#060B13]/60 border-t border-slate-200/60 dark:border-white/[0.06] flex items-center justify-between text-[11px] text-slate-500 dark:text-[#94A3B8]">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1">
              <kbd className="px-1.5 py-0.5 rounded bg-white dark:bg-white/[0.08] border border-slate-200 dark:border-white/[0.1] font-mono">
                ↑↓
              </kbd>{" "}
              {t.commandPalette.navigateHint}
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1.5 py-0.5 rounded bg-white dark:bg-white/[0.08] border border-slate-200 dark:border-white/[0.1] font-mono">
                ↵
              </kbd>{" "}
              {t.commandPalette.selectHint}
            </span>
          </div>
          <span className="flex items-center gap-1">
            <kbd className="px-1.5 py-0.5 rounded bg-white dark:bg-white/[0.08] border border-slate-200 dark:border-white/[0.1] font-mono">
              ESC
            </kbd>{" "}
            {t.commandPalette.closeHint}
          </span>
        </div>
      </div>
    </div>
  );
}
