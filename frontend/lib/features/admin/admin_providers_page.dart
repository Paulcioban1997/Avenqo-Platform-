import 'package:flutter/material.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/features/admin/admin_theme.dart';
import 'package:avenqo/i18n/locale_scope.dart';

/// Statut des fournisseurs IA (READY/DEGRADED/...) — jamais de clé API,
/// erreur brute ou stack trace exposée dans cette vue.
class AdminProvidersPage extends StatelessWidget {
  const AdminProvidersPage({super.key, required this.api});
  final ApiClient api;

  @override
  Widget build(BuildContext context) {
    final s = AvenqoLocaleScope.translationsOf(context).admin;
    final colors = AvenqoColors.of(context);
    return FutureBuilder<dynamic>(
      future: api.get('/ready'),
      builder: (context, snapshot) {
        final data = snapshot.data as Map<String, dynamic>?;
        final providers = (data?['ai_providers'] as Map<String, dynamic>?) ?? const {};
        return ListView(
          padding: const EdgeInsets.all(24),
          children: [
            AdminSectionHeader(
              title: s.providersTitle,
              subtitle: s.providersSubtitle,
            ),
            const SizedBox(height: 20),
            if (snapshot.connectionState != ConnectionState.done)
              const AdminLoadingState()
            else if (snapshot.hasError)
              AdminErrorState(message: s.providersError)
            else if (providers.isEmpty)
              AdminEmptyState(message: s.noProviderStatus, icon: Icons.hub_outlined)
            else
              Column(
                children: [
                  for (final entry in providers.entries) ...[
                    AdminCard(
                      child: Row(
                        children: [
                          Container(
                            width: 40,
                            height: 40,
                            decoration: BoxDecoration(
                              color: AdminBrand.blue.withValues(alpha: 0.1),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: const Icon(Icons.hub_outlined, color: AdminBrand.blue, size: 19),
                          ),
                          const SizedBox(width: 16),
                          Expanded(
                            child: Text(
                              entry.key[0].toUpperCase() + entry.key.substring(1),
                              style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15, color: colors.ink),
                            ),
                          ),
                          AdminStatusBadge(label: '${entry.value}'.toUpperCase(), tone: toneForProviderStatus('${entry.value}')),
                        ],
                      ),
                    ),
                    const SizedBox(height: 14),
                  ],
                ],
              ),
          ],
        );
      },
    );
  }
}
