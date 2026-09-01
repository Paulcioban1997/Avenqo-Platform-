import 'package:flutter/material.dart';
import 'package:avenqo/i18n/translations.dart';

class AdminDestination {
  const AdminDestination({
    required this.path,
    required this.label,
    required this.icon,
  });

  final String path;
  final String label;
  final IconData icon;
}

const adminDestinations = <AdminDestination>[
  AdminDestination(path: '/admin', label: 'Overview', icon: Icons.dashboard_outlined),
  AdminDestination(path: '/admin/agents', label: 'Agents', icon: Icons.apps_outlined),
  AdminDestination(path: '/admin/companies', label: 'Companies', icon: Icons.apartment_outlined),
  AdminDestination(path: '/admin/subscriptions', label: 'Subscriptions', icon: Icons.workspace_premium_outlined),
  AdminDestination(path: '/admin/billing', label: 'Billing', icon: Icons.receipt_long_outlined),
  AdminDestination(path: '/admin/ai-usage', label: 'AI Usage', icon: Icons.auto_awesome_outlined),
  AdminDestination(path: '/admin/providers', label: 'Providers', icon: Icons.hub_outlined),
  AdminDestination(path: '/admin/system-health', label: 'System Health', icon: Icons.monitor_heart_outlined),
  AdminDestination(path: '/admin/audit-log', label: 'Audit Logs', icon: Icons.fact_check_outlined),
  AdminDestination(path: '/admin/support', label: 'Support', icon: Icons.support_agent_outlined),
  AdminDestination(path: '/admin/settings', label: 'Settings', icon: Icons.settings_outlined),
];

/// Localized labels for [adminDestinations], in the same order — used by
/// [AdminShell] instead of the hardcoded English [AdminDestination.label].
List<String> adminNavLabels(Translations translations) {
  final s = translations.admin;
  return [
      s.navOverview,
  translations.agents.navLabel,
      s.navCompanies,
      s.navSubscriptions,
      s.navBilling,
      s.navAiUsage,
      s.navProviders,
      s.navSystemHealth,
      s.navAuditLogs,
      s.navSupport,
      s.navSettings,
    ];
}

