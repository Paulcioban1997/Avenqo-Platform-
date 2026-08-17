"use client";

import Image from "next/image";
import { motion } from "framer-motion";
import {
  ArrowRight, BarChart3, FileScan, MessagesSquare, Mic2, Network,
  Play, ReceiptText, Scale, ShoppingBag, Sparkles,
} from "lucide-react";
import { useTranslations } from "@/lib/i18n/locale-context";

const quickModuleIcons: Record<string, typeof ShoppingBag> = {
  retail: ShoppingBag,
  crm: Network,
  ocr: FileScan,
  voice: Mic2,
  media: Play,
  accounting: ReceiptText,
  legal: Scale,
};

export function DashboardPreview() {
  const t = useTranslations();
  return (
    <div className="dashboard-window" aria-label="Aperçu du tableau de bord Avenqo">
      <div className="window-topbar">
        <div className="window-dots"><i /><i /><i /></div>
        <span>Vue d’ensemble</span>
        <div className="avatar">PC</div>
      </div>
      <div className="dashboard-body">
        <aside className="dashboard-nav">
          <div className="mini-mark"><Image src="/brand/avenqo-icon.png" alt="" fill sizes="28px" /></div>
          {[BarChart3, Sparkles, ShoppingBag, MessagesSquare].map((Icon, index) => (
            <span className={index === 0 ? "active" : ""} key={index}><Icon size={16} /></span>
          ))}
        </aside>
        <div className="dashboard-content">
          <div className="dashboard-heading">
            <div><small>{t.dashboard.greeting}</small><strong>{t.dashboard.subtitle}</strong></div>
            <button><Sparkles size={14} /> {t.dashboard.askAvenqo}</button>
          </div>
          <div className="metric-grid">
            <div><small>{t.dashboard.salesLabel}</small><strong>284 650 $</strong><em>+12,4 %</em></div>
            <div><small>{t.dashboard.activeClientsLabel}</small><strong>2 847</strong><em>+8,1 %</em></div>
            <div><small>{t.dashboard.opportunitiesLabel}</small><strong>36</strong><em>{t.dashboard.opportunitiesHint}</em></div>
          </div>
          <div className="dashboard-lower">
            <div className="chart-panel">
              <div className="panel-title"><strong>{t.dashboard.performanceLabel}</strong><span>{t.dashboard.performancePeriod}</span></div>
              <div className="chart-bars">
                {[44, 62, 55, 74, 68, 90, 82, 98].map((height, index) => <i key={index} style={{ height: `${height}%` }} />)}
              </div>
            </div>
            <div className="insight-panel">
              <span><Sparkles size={16} /> {t.dashboard.recommendationLabel}</span>
              <strong>{t.dashboard.recommendationTitle}</strong>
              <p>{t.dashboard.recommendationText}</p>
              <button>{t.dashboard.recommendationAction} <ArrowRight size={13} /></button>
            </div>
          </div>
          <div className="quick-modules">
            <span className="quick-modules-label">{t.dashboard.quickModulesLabel}</span>
            <div className="quick-modules-grid">
              {t.dashboard.quickModules.map(({ key, label }, index) => {
                const Icon = quickModuleIcons[key] ?? ShoppingBag;
                return (
                  <motion.div
                    className="quick-module-card"
                    key={key}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.45, delay: 0.1 + index * 0.05, ease: "easeOut" }}
                    whileHover={{ y: -3 }}
                  >
                    <Icon size={16} /><span>{label}</span>
                  </motion.div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
