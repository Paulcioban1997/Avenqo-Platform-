import 'package:flutter/material.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/features/admin/admin_theme.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/i18n/translations.dart';

/// Vue d'ensemble globale de la plateforme (jamais de données métier privées
/// d'un tenant spécifique — uniquement des agrégats sûrs pour un platform_admin).
class AdminDashboardPage extends StatelessWidget {
  const AdminDashboardPage({super.key, required this.api});
  final ApiClient api;

  @override
  Widget build(BuildContext context) {
    final s = AvenqoLocaleScope.translationsOf(context).admin;
    return FutureBuilder<dynamic>(
      future: api.get('/admin/dashboard'),
      builder: (context, snapshot) {
        final data = snapshot.data as Map<String, dynamic>?;
        final wide = MediaQuery.sizeOf(context).width >= 1080;
        return ListView(
          padding: EdgeInsets.all(wide ? 32 : 20),
          children: [
            AdminSectionHeader(
              title: s.overviewTitle,
              subtitle: s.overviewSubtitle,
            ),
            const SizedBox(height: 24),
            if (snapshot.connectionState != ConnectionState.done)
              const AdminLoadingState()
            else if (snapshot.hasError)
              AdminErrorState(message: s.overviewError)
            else ...[
              GridView.count(
                crossAxisCount: wide ? 4 : (MediaQuery.sizeOf(context).width >= 640 ? 2 : 1),
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                crossAxisSpacing: 16,
                mainAxisSpacing: 16,
                childAspectRatio: wide ? 1.5 : 2,
                children: [
                  AdminMetricCard(
                    label: s.totalCompanies,
                    value: '${data?['total_companies'] ?? '—'}',
                    icon: Icons.apartment_outlined,
                  ),
                  AdminMetricCard(
                    label: s.newCompanies30d,
                    value: '${data?['new_companies_last_30_days'] ?? '—'}',
                    icon: Icons.trending_up,
                    accent: AdminBrand.success,
                  ),
                  AdminMetricCard(
                    label: s.activeSubscriptions,
                    value: '${data?['active_subscriptions'] ?? '—'}',
                    icon: Icons.workspace_premium_outlined,
                  ),
                  AdminMetricCard(
                    label: s.pastDue,
                    value: '${data?['past_due_subscriptions'] ?? '—'}',
                    icon: Icons.warning_amber_outlined,
                    accent: (data?['past_due_subscriptions'] ?? 0) is num && (data?['past_due_subscriptions'] as num? ?? 0) > 0
                        ? AdminBrand.warning
                        : AdminBrand.blue,
                  ),
                  AdminMetricCard(
                    label: s.aiRequestsPeriod,
                    value: '${data?['ai_requests_current_period'] ?? '—'}',
                    icon: Icons.auto_awesome_outlined,
                  ),
                ],
              ),
              const SizedBox(height: 28),
              AdminSectionHeader(title: s.planDistribution),
              const SizedBox(height: 12),
              AdminCard(
                child: _PlanDistribution(
                  byPlan: (data?['companies_by_plan'] as Map<String, dynamic>?) ?? const {},
                  strings: s,
                ),
              ),
              const SizedBox(height: 28),
              AdminSectionHeader(title: s.providerHealth),
              const SizedBox(height: 12),
              AdminCard(
                child: _ProviderStatusRow(
                  status: (data?['provider_status'] as Map<String, dynamic>?) ?? const {},
                  strings: s,
                ),
              ),
            ],
          ],
        );
      },
    );
  }
}

class _PlanDistribution extends StatelessWidget {
  const _PlanDistribution({required this.byPlan, required this.strings});
  final Map<String, dynamic> byPlan;
  final AdminStrings strings;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    if (byPlan.isEmpty) {
      return Text(strings.noCompaniesYet, style: TextStyle(color: colors.muted));
    }
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: [
        for (final entry in byPlan.entries)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: colors.canvas,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: colors.line),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(entry.key.toString(), style: TextStyle(fontWeight: FontWeight.w700, color: colors.ink)),
                const SizedBox(width: 8),
                Text('${entry.value}', style: TextStyle(color: colors.muted)),
              ],
            ),
          ),
      ],
    );
  }
}

class _ProviderStatusRow extends StatelessWidget {
  const _ProviderStatusRow({required this.status, required this.strings});
  final Map<String, dynamic> status;
  final AdminStrings strings;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    if (status.isEmpty) {
      return Text(strings.noProviderStatus, style: TextStyle(color: colors.muted));
    }
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: [
        for (final entry in status.entries)
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(entry.key, style: TextStyle(fontWeight: FontWeight.w700, color: colors.ink)),
              const SizedBox(width: 8),
              AdminStatusBadge(label: '${entry.value}'.toUpperCase(), tone: toneForProviderStatus('${entry.value}')),
            ],
          ),
      ],
    );
  }
}

