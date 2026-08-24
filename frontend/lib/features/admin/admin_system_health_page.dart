import 'package:flutter/material.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/features/admin/admin_theme.dart';
import 'package:avenqo/i18n/locale_scope.dart';

/// Santé système globale (backend, base de données, gateway IA, Stripe).
class AdminSystemHealthPage extends StatelessWidget {
  const AdminSystemHealthPage({super.key, required this.api});
  final ApiClient api;

  @override
  Widget build(BuildContext context) {
    final s = AvenqoLocaleScope.translationsOf(context).admin;
    return FutureBuilder<dynamic>(
      future: api.get('/ready'),
      builder: (context, snapshot) {
        final data = snapshot.data as Map<String, dynamic>?;
        final providers = (data?['ai_providers'] as Map<String, dynamic>?) ?? const {};
        return ListView(
          padding: const EdgeInsets.all(24),
          children: [
            AdminSectionHeader(
              title: s.systemHealthTitle,
              subtitle: s.systemHealthSubtitle,
            ),
            const SizedBox(height: 20),
            if (snapshot.connectionState != ConnectionState.done)
              const AdminLoadingState()
            else if (snapshot.hasError)
              AdminErrorState(message: s.systemHealthError)
            else
              Column(
                children: [
                  _HealthRow(
                    icon: Icons.dns_outlined,
                    label: s.backendLabel,
                    status: '${data?['status'] ?? s.unknownStatus}',
                  ),
                  const SizedBox(height: 14),
                  _HealthRow(
                    icon: Icons.storage_outlined,
                    label: s.databaseLabel,
                    status: '${data?['database'] ?? s.unknownStatus}',
                  ),
                  const SizedBox(height: 14),
                  for (final entry in providers.entries) ...[
                    _HealthRow(
                      icon: Icons.hub_outlined,
                      label: entry.key[0].toUpperCase() + entry.key.substring(1),
                      status: '${entry.value}',
                    ),
                    const SizedBox(height: 14),
                  ],
                  _HealthRow(
                    icon: Icons.payments_outlined,
                    label: s.billingStripeLabel,
                    status: (data?['stripe_configured'] == true) ? s.configured : s.notConfigured,
                  ),
                ],
              ),
          ],
        );
      },
    );
  }
}

class _HealthRow extends StatelessWidget {
  const _HealthRow({required this.icon, required this.label, required this.status});
  final IconData icon;
  final String label;
  final String status;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return AdminCard(
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: AdminBrand.blue.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(icon, color: AdminBrand.blue, size: 19),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Text(label, style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15, color: colors.ink)),
          ),
          AdminStatusBadge(label: status.toUpperCase(), tone: toneForProviderStatus(status)),
        ],
      ),
    );
  }
}
