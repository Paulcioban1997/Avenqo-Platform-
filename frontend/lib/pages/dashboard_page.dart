import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/core/money_formatter.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/i18n/translations.dart';

/// Palette de marque Avenqo (alignée sur home_page.dart / auth_page.dart).
/// `blue`/`blueDark` sont l'accent de marque fixe (identique clair/sombre) ;
/// le texte/fond de contenu passe par [AvenqoColors.of] pour le mode sombre.
class _Brand {
  const _Brand._();

  static const blue = Color(0xFF087CF0);
  static const blueDark = Color(0xFF0757C9);
  static const ink = Color(0xFF080B12);
}

class DashboardData {
  const DashboardData({
    required this.status,
    required this.planCode,
    required this.currency,
    required this.kpis,
    required this.priorities,
    required this.connections,
    required this.recentActivity,
  });

  factory DashboardData.fromJson(Map<String, dynamic> json) {
    final company = json['company'] as Map<String, dynamic>? ?? const {};
    return DashboardData(
      status: json['status']?.toString() ?? 'error',
      planCode: company['plan_code']?.toString(),
      currency: company['currency']?.toString() ?? 'USD',
      kpis: (json['kpis'] as List<dynamic>? ?? const [])
          .cast<Map<String, dynamic>>(),
      priorities: (json['priorities'] as List<dynamic>? ?? const [])
          .cast<Map<String, dynamic>>(),
      connections:
          json['connections'] as Map<String, dynamic>? ?? const {},
      recentActivity: (json['recent_activity'] as List<dynamic>? ?? const [])
          .cast<Map<String, dynamic>>(),
    );
  }

  final String status;
  final String? planCode;
  final String currency;
  final List<Map<String, dynamic>> kpis;
  final List<Map<String, dynamic>> priorities;
  final Map<String, dynamic> connections;
  final List<Map<String, dynamic>> recentActivity;

  bool get hasReadyData => status == 'ready' || status == 'partial_ready';

  Map<String, dynamic>? kpi(String key) {
    for (final item in kpis) {
      if (item['key'] == key) return item;
    }
    return null;
  }
}

/// Point d'injection pour les tests : évite tout appel réseau réel dans les
/// widget tests, sans changer le comportement par défaut en production.
typedef DashboardDataLoader = Future<DashboardData> Function(AuthController auth);

Future<DashboardData> _defaultDashboardLoader(AuthController auth) async {
  final payload = await auth.api
      .get('/dashboard')
      .timeout(const Duration(seconds: 10)) as Map<String, dynamic>;
  return DashboardData.fromJson(payload);
}

class DashboardPage extends StatefulWidget {
  const DashboardPage({super.key, required this.auth, DashboardDataLoader? loader})
      : loader = loader ?? _defaultDashboardLoader;

  final AuthController auth;
  final DashboardDataLoader loader;

  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  late Future<DashboardData> _future = widget.loader(widget.auth);

  void _retry() {
    final next = widget.loader(widget.auth);
    setState(() {
      _future = next;
    });
  }

  @override
  Widget build(BuildContext context) {
    final t = AvenqoLocaleScope.translationsOf(context).dashboardHome;
    final companyT = AvenqoLocaleScope.translationsOf(context).company;
    final colors = AvenqoColors.of(context);
    final company = widget.auth.company ?? const <String, dynamic>{};
    final user = widget.auth.user ?? const <String, dynamic>{};
    final wide = MediaQuery.sizeOf(context).width >= 1080;
    final companyName = company['name']?.toString() ?? '';
    final firstName = user['first_name']?.toString();

    return Container(
      color: colors.canvas,
      child: FutureBuilder<DashboardData>(
        future: _future,
        builder: (context, snapshot) {
          final loading = snapshot.connectionState != ConnectionState.done;
          final data = snapshot.data ?? const DashboardData(
            status: 'no_data',
            planCode: null,
            currency: 'USD',
            kpis: [],
            priorities: [],
            connections: {},
            recentActivity: [],
          );
          return ListView(
            padding: EdgeInsets.all(wide ? 32 : 20),
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          firstName == null ? t.hello : '${t.hello}, $firstName',
                          style: TextStyle(
                            fontSize: 26,
                            fontWeight: FontWeight.w800,
                            color: colors.ink,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          t.subtitleForCompany.replaceFirst(
                            '{company}',
                            companyName.isEmpty ? '—' : companyName,
                          ),
                          style: TextStyle(color: colors.muted, fontSize: 15),
                        ),
                      ],
                    ),
                  ),
                  if (!loading && data.planCode?.isNotEmpty == true)
                    _PlanBadge(label: t.planLabel, plan: data.planCode!),
                ],
              ),
              if (company['onboarding_status'] == 'skipped') ...[
                const SizedBox(height: 16),
                _ResumeOnboardingBanner(),
              ],
              const SizedBox(height: 24),
              LayoutBuilder(
                builder: (context, constraints) {
                  final stacked = constraints.maxWidth < 760;
                  final askCard = _HeroCard(
                    icon: Icons.auto_awesome,
                    title: t.askAvenqo,
                    subtitle: t.askAvenqoSubtitle,
                    cta: t.askAvenqoCta,
                    dark: true,
                    onTap: () => context.go('/assistant'),
                  );
                  final importCard = _HeroCard(
                    icon: Icons.upload_file_outlined,
                    title: t.importDataTitle,
                    subtitle: t.importDataSubtitle,
                    cta: t.importDataCta,
                    dark: false,
                    onTap: () => context.go('/connections'),
                  );
                  if (stacked) {
                    return Column(children: [askCard, const SizedBox(height: 16), importCard]);
                  }
                  return IntrinsicHeight(
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Expanded(child: askCard),
                        const SizedBox(width: 16),
                        Expanded(child: importCard),
                      ],
                    ),
                  );
                },
              ),
              const SizedBox(height: 20),
              if (loading)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 40),
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (snapshot.hasError)
                _DashboardMessage(
                  icon: Icons.error_outline,
                  message: companyT.connectionsGenericError,
                  actionLabel: companyT.connectionsRetry,
                  onAction: _retry,
                )
              else if (data.status == 'no_data')
                _EmptyDataBanner(title: t.connectDataTitle, cta: t.connectDataCta)
              else if (data.status == 'processing')
                _DashboardMessage(
                  icon: Icons.sync,
                  message: companyT.connectionsAnalyzing,
                )
              else ...[
                Text(t.thisMonth, style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18, color: colors.ink)),
                const SizedBox(height: 12),
                GridView.count(
                  crossAxisCount: wide
                      ? 4
                      : MediaQuery.sizeOf(context).width >= 620
                          ? 2
                          : 1,
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  crossAxisSpacing: 16,
                  mainAxisSpacing: 16,
                    childAspectRatio: wide
                      ? 1.65
                      : MediaQuery.sizeOf(context).width >= 620
                        ? 1.7
                        : 2.2,
                  children: [
                    _Metric.fromKpi(label: t.salesLabel, data: data, key: 'revenue', context: context),
                    _Metric.fromKpi(label: t.ordersLabel, data: data, key: 'orders', context: context),
                    _Metric.fromKpi(label: t.customersLabel, data: data, key: 'customers', context: context),
                    _Metric.fromKpi(label: t.avgOrderLabel, data: data, key: 'average_order_value', context: context),
                  ],
                ),
              ],
              const SizedBox(height: 28),
              Text(t.prioritiesTitle, style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18, color: colors.ink)),
              const SizedBox(height: 12),
              Container(
                decoration: BoxDecoration(
                  color: colors.surface,
                  border: Border.all(color: colors.line),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(22),
                  child: data.priorities.isEmpty
                      ? Row(
                          children: [
                            const Icon(Icons.lightbulb_outline, color: _Brand.blue),
                            const SizedBox(width: 14),
                            Expanded(child: Text(t.prioritiesEmpty, style: TextStyle(color: colors.muted))),
                          ],
                        )
                      : Column(
                          children: [
                            for (final priority in data.priorities)
                              _PriorityRow(priority: priority, strings: t),
                          ],
                        ),
                ),
              ),
              const SizedBox(height: 28),
              Text(t.connectionsTitle, style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18, color: colors.ink)),
              const SizedBox(height: 12),
              if (!loading && data.connections.isNotEmpty)
                _ConnectionsSummary(data: data.connections, strings: companyT)
              else if (!loading)
                _EmptyDataBanner(title: t.connectionsEmpty, cta: t.connectionsEmptyCta),
              const SizedBox(height: 28),
              Text(t.activityTitle, style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18, color: colors.ink)),
              const SizedBox(height: 12),
              Container(
                decoration: BoxDecoration(
                  color: colors.surface,
                  border: Border.all(color: colors.line),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(22),
                  child: !loading && data.recentActivity.isNotEmpty
                      ? Column(
                          children: [
                            for (final activity in data.recentActivity)
                              _ActivityRow(activity: activity),
                          ],
                        )
                      : Row(
                          children: [
                            const Icon(Icons.history, color: _Brand.blue),
                            const SizedBox(width: 14),
                            Expanded(child: Text(t.activityEmpty, style: TextStyle(color: colors.muted))),
                          ],
                        ),
                ),
              ),
              const SizedBox(height: 28),
              Text(t.stepsTitle, style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18, color: colors.ink)),
              const SizedBox(height: 12),
              _RecommendedSteps(
                orgDone: company['onboarding_status'] != null && company['onboarding_status'] != 'pending',
                dataDone: !loading && data.hasReadyData,
                orgLabel: t.stepOrgLabel,
                dataLabel: t.stepDataLabel,
                insightsLabel: t.stepInsightsLabel,
                askLabel: t.stepAskLabel,
              ),
            ],
          );
        },
      ),
    );
  }
}

String _formatDate(DateTime date) {
  final local = date.toLocal();
  final day = local.day.toString().padLeft(2, '0');
  final month = local.month.toString().padLeft(2, '0');
  return '$day/$month/${local.year}';
}

class _HeroCard extends StatelessWidget {
  const _HeroCard({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.cta,
    required this.dark,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final String cta;
  final bool dark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final background = dark ? _Brand.ink : colors.surface;
    final textColor = dark ? Colors.white : colors.ink;
    final subtitleColor = dark ? Colors.white.withValues(alpha: 0.75) : colors.muted;
    return Material(
      color: background,
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: Container(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            border: dark ? null : Border.all(color: colors.line),
          ),
          padding: const EdgeInsets.all(22),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(color: _Brand.blue, borderRadius: BorderRadius.circular(10)),
                child: Icon(icon, color: Colors.white, size: 20),
              ),
              const SizedBox(height: 16),
              Text(title, style: TextStyle(color: textColor, fontSize: 17, fontWeight: FontWeight.w700)),
              const SizedBox(height: 6),
              Text(subtitle, style: TextStyle(color: subtitleColor, fontSize: 13.5)),
              const SizedBox(height: 16),
              Row(
                children: [
                  Text(cta, style: const TextStyle(color: _Brand.blue, fontWeight: FontWeight.w700)),
                  const SizedBox(width: 6),
                  const Icon(Icons.arrow_forward, size: 16, color: _Brand.blue),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _DashboardMessage extends StatelessWidget {
  const _DashboardMessage({
    required this.icon,
    required this.message,
    this.actionLabel,
    this.onAction,
  });

  final IconData icon;
  final String message;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border.all(color: colors.line),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Icon(icon, color: _Brand.blue),
          const SizedBox(width: 14),
          Expanded(child: Text(message, style: TextStyle(color: colors.ink))),
          if (actionLabel != null && onAction != null)
            TextButton(onPressed: onAction, child: Text(actionLabel!)),
        ],
      ),
    );
  }
}

class _PriorityRow extends StatelessWidget {
  const _PriorityRow({required this.priority, required this.strings});

  final Map<String, dynamic> priority;
  final DashboardHomeStrings strings;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final phase4d = AvenqoLocaleScope.translationsOf(context).phase4d;
    final type = priority['type']?.toString() ?? priority['title']?.toString() ?? '';
    final declining = type == 'revenue_decline' || type == 'product_decline';
    final title = switch (type) {
      'revenue_decline' => strings.revenueDeclineTitle,
      'revenue_growth' => strings.revenueGrowthTitle,
      'product_decline' => phase4d.productDeclineTitle,
      'product_growth' => phase4d.productGrowthTitle,
      'product_concentration' => phase4d.productConcentrationTitle,
      'cross_sell_opportunity' => phase4d.crossSellOpportunityTitle,
      _ => strings.prioritiesTitle,
    };
    final explanation = switch (type) {
      'revenue_decline' || 'revenue_growth' => strings.revenueChangedExplanation,
      'product_decline' || 'product_growth' => phase4d.productRevenueChangedExplanation,
      'product_concentration' => phase4d.productConcentrationExplanation,
      'cross_sell_opportunity' => phase4d.crossSellOpportunityExplanation,
      _ => strings.revenueChangedExplanation,
    };
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: Icon(
        declining ? Icons.trending_down : Icons.trending_up,
        color: declining ? const Color(0xFFD1414B) : const Color(0xFF1B9E5A),
      ),
      title: Text(
        title,
        style: TextStyle(color: colors.ink, fontWeight: FontWeight.w700),
      ),
      subtitle: Text(explanation, style: TextStyle(color: colors.muted)),
    );
  }
}

class _ConnectionsSummary extends StatelessWidget {
  const _ConnectionsSummary({required this.data, required this.strings});

  final Map<String, dynamic> data;
  final CompanyStrings strings;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final statuses = <(String, String)>[
      ('ready', strings.connectionsReadyTitle),
      ('analyzing', strings.connectionsAnalyzing),
      ('preparing_data', strings.connectionsPreparingData),
      ('training_ai', strings.connectionsTrainingAi),
      ('attention_required', strings.connectionsAttentionRequired),
      ('failed', strings.connectionsProcessingError),
    ];
    return Container(
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border.all(color: colors.line),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Wrap(
        spacing: 20,
        runSpacing: 12,
        children: [
          for (final status in statuses)
            if ((data[status.$1] as num? ?? 0) > 0)
              Text(
                '${data[status.$1]} ${status.$2}',
                style: TextStyle(color: colors.ink, fontWeight: FontWeight.w600),
              ),
        ],
      ),
    );
  }
}

class _ActivityRow extends StatelessWidget {
  const _ActivityRow({required this.activity});

  final Map<String, dynamic> activity;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final strings = AvenqoLocaleScope.translationsOf(context).dashboardHome;
    final kind = activity['kind']?.toString();
    final label = kind == 'model_activated'
        ? strings.modelActivatedActivity
        : strings.datasetImportedActivity;
    final date = DateTime.tryParse(activity['occurred_at']?.toString() ?? '');
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: const Icon(Icons.history, color: _Brand.blue),
      title: Text(label, style: TextStyle(color: colors.ink, fontWeight: FontWeight.w600)),
      subtitle: Text(
        '${activity['title'] ?? ''}${date == null ? '' : ' · ${_formatDate(date)}'}',
        style: TextStyle(color: colors.muted),
      ),
    );
  }
}

class _RecommendedSteps extends StatelessWidget {
  const _RecommendedSteps({
    required this.orgDone,
    required this.dataDone,
    required this.orgLabel,
    required this.dataLabel,
    required this.insightsLabel,
    required this.askLabel,
  });

  final bool orgDone;
  final bool dataDone;
  final String orgLabel;
  final String dataLabel;
  final String insightsLabel;
  final String askLabel;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final steps = [
      (orgLabel, orgDone),
      (dataLabel, dataDone),
      (insightsLabel, dataDone),
      (askLabel, false),
    ];
    return Container(
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border.all(color: colors.line),
        borderRadius: BorderRadius.circular(12),
      ),
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Material(
        type: MaterialType.transparency,
        child: Column(
          children: [
            for (var i = 0; i < steps.length; i++)
              ListTile(
                leading: Icon(
                  steps[i].$2 ? Icons.check_circle : Icons.radio_button_unchecked,
                  color: steps[i].$2 ? const Color(0xFF1B9E5A) : colors.muted,
                ),
                title: Text(
                  steps[i].$1,
                  style: TextStyle(
                    color: colors.ink,
                    fontWeight: FontWeight.w600,
                    decoration: steps[i].$2 ? TextDecoration.lineThrough : null,
                    decorationColor: colors.muted,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _ResumeOnboardingBanner extends StatelessWidget {
  const _ResumeOnboardingBanner();

  @override
  Widget build(BuildContext context) {
    final t = AvenqoLocaleScope.translationsOf(context).onboarding;
    final colors = AvenqoColors.of(context);
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: _Brand.blue.withValues(alpha: 0.06),
        border: Border.all(color: _Brand.blue.withValues(alpha: 0.25)),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Wrap(
        spacing: 16,
        runSpacing: 10,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          const Icon(Icons.rocket_launch_outlined, color: _Brand.blue),
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Text(t.title, style: TextStyle(color: colors.ink, fontWeight: FontWeight.w600)),
          ),
          OutlinedButton(
            onPressed: () => context.go('/onboarding'),
            child: Text(t.continueCta),
          ),
        ],
      ),
    );
  }
}

class _PlanBadge extends StatelessWidget {
  const _PlanBadge({required this.label, required this.plan});

  final String label;
  final String plan;
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: _Brand.blue.withValues(alpha: 0.08),
        border: Border.all(color: _Brand.blue.withValues(alpha: 0.3)),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        '$label \u00b7 ${plan[0].toUpperCase()}${plan.substring(1)}',
        style: const TextStyle(color: _Brand.blueDark, fontWeight: FontWeight.w700, fontSize: 12),
      ),
    );
  }
}

class _EmptyDataBanner extends StatelessWidget {
  const _EmptyDataBanner({required this.title, required this.cta});

  final String title;
  final String cta;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border.all(color: colors.line),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Wrap(
        spacing: 16,
        runSpacing: 14,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: _Brand.blue.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(10),
            ),
            child: const Icon(Icons.sync_alt, color: _Brand.blue),
          ),
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 460),
            child: Text(title, style: TextStyle(color: colors.ink, fontWeight: FontWeight.w600)),
          ),
          FilledButton.icon(
            onPressed: () => context.go('/connections'),
            style: FilledButton.styleFrom(backgroundColor: _Brand.blue),
            icon: const Icon(Icons.add_link, size: 18),
            label: Text(cta),
          ),
        ],
      ),
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({required this.label, required this.value, this.change});

  factory _Metric.fromKpi({
    required String label,
    required DashboardData data,
    required String key,
    required BuildContext context,
  }) {
    final kpi = data.kpi(key);
    final available = kpi?['available'] == true && kpi?['value'] is num;
    if (!available) return _Metric(label: label, value: '—');
    final value = kpi!['value'] as num;
    final currency = kpi['currency']?.toString();
    final rendered = currency == null
        ? value.toString()
        : formatMoney(
            value,
            locale: Localizations.localeOf(context).toLanguageTag(),
            currencyCode: data.currency,
          );
    final changePercent = kpi['change_percent'] as num?;
    return _Metric(
      label: label,
      value: rendered,
      change: changePercent == null
          ? null
          : '${changePercent >= 0 ? '+' : ''}${changePercent.toStringAsFixed(1)}%',
    );
  }

  final String label;
  final String value;
  final String? change;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border.all(color: colors.line),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(label, style: TextStyle(color: colors.muted)),
            const SizedBox(height: 4),
            Text(value, style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: colors.ink)),
            if (change != null) ...[
              const SizedBox(height: 4),
              Text(change!, style: const TextStyle(color: Color(0xFF1B9E5A), fontSize: 12)),
            ],
          ],
        ),
      ),
    );
  }
}
