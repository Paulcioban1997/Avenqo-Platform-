import 'package:flutter/material.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/features/admin/admin_theme.dart';
import 'package:avenqo/i18n/locale_scope.dart';

/// Usage IA plateforme : agrégats réels de /admin/dashboard. Pas de coût par
/// fournisseur/tokens détaillé exposé aujourd'hui côté backend — état vide
/// honnête plutôt qu'une estimation inventée.
class AdminAiUsagePage extends StatelessWidget {
  const AdminAiUsagePage({super.key, required this.api});
  final ApiClient api;

  @override
  Widget build(BuildContext context) {
    final s = AvenqoLocaleScope.translationsOf(context).admin;
    return FutureBuilder<dynamic>(
      future: api.get('/admin/dashboard'),
      builder: (context, snapshot) {
        final data = snapshot.data as Map<String, dynamic>?;
        final providerStatus = (data?['provider_status'] as Map<String, dynamic>?) ?? const {};
        return ListView(
          padding: const EdgeInsets.all(24),
          children: [
            AdminSectionHeader(
              title: s.aiUsageTitle,
              subtitle: s.aiUsageSubtitle,
            ),
            const SizedBox(height: 20),
            if (snapshot.connectionState != ConnectionState.done)
              const AdminLoadingState()
            else if (snapshot.hasError)
              AdminErrorState(message: s.aiUsageError)
            else ...[
              AdminMetricCard(
                label: s.aiRequestsCurrentPeriod,
                value: '${data?['ai_requests_current_period'] ?? '—'}',
                icon: Icons.auto_awesome_outlined,
              ),
              const SizedBox(height: 24),
              AdminSectionHeader(title: s.providersLabel),
              const SizedBox(height: 12),
              if (providerStatus.isEmpty)
                AdminEmptyState(message: s.noProviderStatus, icon: Icons.hub_outlined)
              else
                AdminCard(
                  child: Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    children: [
                      for (final entry in providerStatus.entries)
                        Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(entry.key, style: TextStyle(fontWeight: FontWeight.w700, color: AvenqoColors.of(context).ink)),
                            const SizedBox(width: 8),
                            AdminStatusBadge(label: '${entry.value}'.toUpperCase(), tone: toneForProviderStatus('${entry.value}')),
                          ],
                        ),
                    ],
                  ),
                ),
              const SizedBox(height: 24),
              AdminEmptyState(
                message: s.noCostBreakdownMessage,
                icon: Icons.bar_chart_outlined,
              ),
            ],
          ],
        );
      },
    );
  }
}
