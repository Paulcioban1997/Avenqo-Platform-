import 'package:flutter/material.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/features/admin/admin_theme.dart';
import 'package:avenqo/i18n/locale_scope.dart';

/// Détail administratif d'une entreprise (profil, plan, usage, comptages) —
/// n'affiche pas par défaut le contenu commercial privé du tenant (ventes,
/// clients, datasets bruts).
class AdminCompanyDetailPage extends StatelessWidget {
  const AdminCompanyDetailPage({super.key, required this.api, required this.companyId});
  final ApiClient api;
  final String companyId;

  @override
  Widget build(BuildContext context) {
    final s = AvenqoLocaleScope.translationsOf(context).admin;
    final colors = AvenqoColors.of(context);
    return FutureBuilder<dynamic>(
      future: api.get('/admin/companies/$companyId'),
      builder: (context, snapshot) {
        final detail = snapshot.data as Map<String, dynamic>?;
        final wide = MediaQuery.sizeOf(context).width >= 1080;
        return ListView(
          padding: EdgeInsets.all(wide ? 32 : 20),
          children: [
            if (snapshot.connectionState != ConnectionState.done)
              const AdminLoadingState()
            else if (snapshot.hasError)
              AdminErrorState(message: s.companyDetailError)
            else ...[
              AdminCard(
                child: Row(
                  children: [
                    Container(
                      width: 52,
                      height: 52,
                      decoration: BoxDecoration(
                        color: AdminBrand.blue.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: const Icon(Icons.apartment_outlined, color: AdminBrand.blue, size: 24),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            detail?['name']?.toString() ?? s.companyFallbackName,
                            style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: colors.ink),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            '${detail?['country'] ?? '—'} · ${s.joinedLabel} ${detail?['joined_at'] ?? '—'}',
                            style: TextStyle(color: colors.muted, fontSize: 13),
                          ),
                        ],
                      ),
                    ),
                    AdminStatusBadge(
                      label: '${detail?['plan_code'] ?? '—'}'.toUpperCase(),
                      tone: AdminStatusTone.neutral,
                    ),
                    const SizedBox(width: 10),
                    AdminStatusBadge(
                      label: '${detail?['subscription_status'] ?? '—'}'.toUpperCase(),
                      tone: toneForProviderStatus('${detail?['subscription_status'] ?? ''}'),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),
              AdminSectionHeader(title: s.usage),
              const SizedBox(height: 12),
              GridView.count(
                crossAxisCount: wide ? 4 : 2,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                crossAxisSpacing: 16,
                mainAxisSpacing: 16,
                childAspectRatio: wide ? 1.5 : 1.8,
                children: [
                  AdminMetricCard(
                    label: s.users,
                    value: '${detail?['users_count'] ?? '—'}',
                    icon: Icons.people_outline,
                  ),
                  AdminMetricCard(
                    label: s.datasets,
                    value: '${detail?['datasets_count'] ?? '—'}',
                    icon: Icons.dataset_outlined,
                  ),
                  AdminMetricCard(
                    label: s.trainedModels,
                    value: '${detail?['trained_model_count'] ?? '—'}',
                    icon: Icons.model_training_outlined,
                  ),
                  AdminMetricCard(
                    label: s.aiRequestsPeriod,
                    value: '${detail?['ai_requests_current_period'] ?? '—'}',
                    icon: Icons.auto_awesome_outlined,
                  ),
                ],
              ),
              const SizedBox(height: 24),
              AdminSectionHeader(title: s.subscription),
              const SizedBox(height: 12),
              AdminCard(
                child: Column(
                  children: [
                    _DetailRow(label: s.currentPeriodEnd, value: '${detail?['current_period_end'] ?? '—'}'),
                    Divider(height: 24, color: colors.line),
                    _DetailRow(
                      label: s.cancelsAtPeriodEnd,
                      value: (detail?['cancel_at_period_end'] == true) ? s.yes : s.no,
                    ),
                    if (detail?['enterprise_override'] != null) ...[
                      Divider(height: 24, color: colors.line),
                      _DetailRow(label: s.enterpriseOverride, value: s.active),
                    ],
                  ],
                ),
              ),
            ],
          ],
        );
      },
    );
  }
}

class _DetailRow extends StatelessWidget {
  const _DetailRow({required this.label, required this.value});
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label, style: TextStyle(color: colors.muted)),
        Text(value, style: TextStyle(fontWeight: FontWeight.w700, color: colors.ink)),
      ],
    );
  }
}

