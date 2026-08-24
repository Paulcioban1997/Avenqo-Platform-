import 'package:flutter/material.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/features/admin/admin_theme.dart';
import 'package:avenqo/i18n/locale_scope.dart';

/// Vue billing plateforme : agrégats déjà exposés par /admin/dashboard.
/// Pas d'agrégation cross-tenant des factures/paiements côté backend
/// aujourd'hui — affiché honnêtement en état vide plutôt qu'inventé.
class AdminBillingPage extends StatelessWidget {
  const AdminBillingPage({super.key, required this.api});
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
          padding: const EdgeInsets.all(24),
          children: [
            AdminSectionHeader(
              title: s.billingTitle,
              subtitle: s.billingSubtitle,
            ),
            const SizedBox(height: 20),
            if (snapshot.connectionState != ConnectionState.done)
              const AdminLoadingState()
            else if (snapshot.hasError)
              AdminErrorState(message: s.billingError)
            else ...[
              GridView.count(
                crossAxisCount: wide ? 2 : 1,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                crossAxisSpacing: 16,
                mainAxisSpacing: 16,
                childAspectRatio: wide ? 2.6 : 2,
                children: [
                  AdminMetricCard(
                    label: s.activeSubscriptions,
                    value: '${data?['active_subscriptions'] ?? '—'}',
                    icon: Icons.workspace_premium_outlined,
                  ),
                  AdminMetricCard(
                    label: s.pastDue,
                    value: '${data?['past_due_subscriptions'] ?? '—'}',
                    icon: Icons.warning_amber_outlined,
                    accent: AdminBrand.warning,
                  ),
                ],
              ),
              const SizedBox(height: 24),
              AdminEmptyState(
                message: s.noInvoicesMessage,
                icon: Icons.receipt_long_outlined,
              ),
            ],
          ],
        );
      },
    );
  }
}
