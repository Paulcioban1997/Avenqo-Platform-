import 'package:flutter/material.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/features/admin/admin_theme.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/i18n/translations.dart';

/// Vue d'ensemble des abonnements cross-tenant (dérivée du répertoire des
/// entreprises — aucune nouvelle donnée commerciale inventée).
class AdminSubscriptionsPage extends StatelessWidget {
  const AdminSubscriptionsPage({super.key, required this.api});
  final ApiClient api;

  @override
  Widget build(BuildContext context) {
    final s = AvenqoLocaleScope.translationsOf(context).admin;
    final colors = AvenqoColors.of(context);
    return FutureBuilder<dynamic>(
      future: api.get('/admin/companies'),
      builder: (context, snapshot) {
        final companies = (snapshot.data as List<dynamic>? ?? const []).cast<Map<String, dynamic>>();
        return ListView(
          padding: const EdgeInsets.all(24),
          children: [
            AdminSectionHeader(
              title: s.subscriptionsTitle,
              subtitle: '${companies.length} ${s.subscriptionsSubtitle}',
            ),
            const SizedBox(height: 20),
            if (snapshot.connectionState != ConnectionState.done)
              const AdminLoadingState()
            else if (snapshot.hasError)
              AdminErrorState(message: s.subscriptionsError)
            else if (companies.isEmpty)
              AdminEmptyState(message: s.noSubscriptionsYet, icon: Icons.workspace_premium_outlined)
            else
              AdminCard(
                padding: EdgeInsets.zero,
                child: Column(
                  children: [
                    for (var i = 0; i < companies.length; i++) ...[
                      if (i > 0) Divider(height: 1, color: colors.line),
                      _SubscriptionRow(company: companies[i], strings: s),
                    ],
                  ],
                ),
              ),
          ],
        );
      },
    );
  }
}

class _SubscriptionRow extends StatelessWidget {
  const _SubscriptionRow({required this.company, required this.strings});
  final Map<String, dynamic> company;
  final AdminStrings strings;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
      child: Row(
        children: [
          Expanded(
            child: Text(
              company['name']?.toString() ?? strings.companyFallbackName,
              style: TextStyle(fontWeight: FontWeight.w700, color: colors.ink),
            ),
          ),
          AdminStatusBadge(label: '${company['plan_code'] ?? '—'}'.toUpperCase(), tone: AdminStatusTone.neutral),
          const SizedBox(width: 10),
          AdminStatusBadge(
            label: '${company['subscription_status'] ?? '—'}'.toUpperCase(),
            tone: toneForProviderStatus('${company['subscription_status'] ?? ''}'),
          ),
        ],
      ),
    );
  }
}
