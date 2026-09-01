import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/i18n/translations.dart';

typedef RecommendationsLoader = Future<Map<String, dynamic>> Function();

class RecommendationsPage extends StatefulWidget {
  const RecommendationsPage({super.key, required this.api, this.loader, this.onNavigate});

  final ApiClient api;
  final RecommendationsLoader? loader;
  final ValueChanged<String>? onNavigate;

  @override
  State<RecommendationsPage> createState() => _RecommendationsPageState();
}

class _RecommendationsPageState extends State<RecommendationsPage> {
  late Future<Map<String, dynamic>> _future = _load();

  Future<Map<String, dynamic>> _load() {
    if (widget.loader case final loader?) return loader();
    return widget.api
        .get('/recommendations')
        .then((value) => value as Map<String, dynamic>);
  }

  void _reload() {
    final next = _load();
    setState(() {
      _future = next;
    });
  }

  @override
  Widget build(BuildContext context) {
    final company = AvenqoLocaleScope.translationsOf(context).company;
    final colors = AvenqoColors.of(context);
    return FutureBuilder<Map<String, dynamic>>(
      future: _future,
      builder: (context, snapshot) => ListView(
        padding: const EdgeInsets.all(24),
        children: [
          Text(company.navRecommendationsLabel, style: Theme.of(context).textTheme.headlineMedium),
          const SizedBox(height: 6),
          Text(company.navRecommendationsDescription, style: TextStyle(color: colors.muted)),
          const SizedBox(height: 20),
          if (snapshot.connectionState != ConnectionState.done)
            const Center(child: CircularProgressIndicator())
          else if (snapshot.hasError)
            _RecommendationState(
              message: company.connectionsGenericError,
              action: company.connectionsRetry,
              onPressed: _reload,
            )
          else
            _RecommendationsContent(data: snapshot.data!, onNavigate: widget.onNavigate),
        ],
      ),
    );
  }
}

class _RecommendationsContent extends StatelessWidget {
  const _RecommendationsContent({required this.data, required this.onNavigate});
  final Map<String, dynamic> data;
  final ValueChanged<String>? onNavigate;

  @override
  Widget build(BuildContext context) {
    final company = AvenqoLocaleScope.translationsOf(context).company;
    final strings = AvenqoLocaleScope.translationsOf(context).phase4d;
    if (data['status'] == 'processing') {
      return _RecommendationState(message: company.connectionsAnalyzing);
    }
    final items = (data['recommendations'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (data['status'] == 'partial_ready') ...[
          _RecommendationState(message: strings.partialReady, icon: Icons.info_outline),
          const SizedBox(height: 16),
        ],
        if (items.isEmpty)
          _RecommendationState(message: strings.recommendationsEmpty)
        else
          LayoutBuilder(
            builder: (context, constraints) {
              final width = constraints.maxWidth >= 920
                  ? (constraints.maxWidth - 16) / 2
                  : constraints.maxWidth;
              return Wrap(
                spacing: 16,
                runSpacing: 16,
                children: [
                  for (final item in items)
                    SizedBox(width: width, child: _RecommendationCard(item: item, onNavigate: onNavigate)),
                ],
              );
            },
          ),
      ],
    );
  }
}

class _RecommendationCard extends StatelessWidget {
  const _RecommendationCard({required this.item, required this.onNavigate});
  final Map<String, dynamic> item;
  final ValueChanged<String>? onNavigate;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final strings = AvenqoLocaleScope.translationsOf(context).phase4d;
    final type = item['type']?.toString() ?? '';
    final priority = item['priority']?.toString() ?? 'informational';
    final route = item['action_route']?.toString();
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border.all(color: colors.line),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(_icon(type), color: _priorityColor(priority)),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  _title(context, type),
                  style: TextStyle(color: colors.ink, fontSize: 17, fontWeight: FontWeight.w800),
                ),
              ),
              const SizedBox(width: 8),
              _PriorityBadge(label: '${strings.priorityLabel}: $priority', priority: priority),
            ],
          ),
          const SizedBox(height: 12),
          Text(_explanation(context, type), style: TextStyle(color: colors.muted)),
          const SizedBox(height: 16),
          Text(strings.evidenceLabel, style: TextStyle(color: colors.ink, fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          Text(_evidence(strings, type, item['evidence'] as Map<String, dynamic>? ?? const {}), style: TextStyle(color: colors.muted)),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: Text(
                  '${strings.suggestedActionLabel}: ${_action(context, item['suggested_action']?.toString() ?? '')}',
                  style: TextStyle(color: colors.ink, fontWeight: FontWeight.w600),
                ),
              ),
              if (route != null)
                IconButton(
                  tooltip: _action(context, item['suggested_action']?.toString() ?? ''),
                  onPressed: () {
                    if (onNavigate case final navigate?) {
                      navigate(route);
                    } else {
                      context.go(route);
                    }
                  },
                  icon: const Icon(Icons.arrow_forward),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

String _title(BuildContext context, String type) {
  final all = AvenqoLocaleScope.translationsOf(context);
  return switch (type) {
    'revenue_decline' => all.dashboardHome.revenueDeclineTitle,
    'revenue_growth' => all.dashboardHome.revenueGrowthTitle,
    'product_decline' => all.phase4d.productDeclineTitle,
    'product_growth' => all.phase4d.productGrowthTitle,
    'product_concentration' => all.phase4d.productConcentrationTitle,
    'cross_sell_opportunity' => all.phase4d.crossSellOpportunityTitle,
    _ => all.company.navRecommendationsLabel,
  };
}

String _explanation(BuildContext context, String type) {
  final all = AvenqoLocaleScope.translationsOf(context);
  return switch (type) {
    'revenue_decline' || 'revenue_growth' => all.dashboardHome.revenueChangedExplanation,
    'product_decline' || 'product_growth' => all.phase4d.productRevenueChangedExplanation,
    'product_concentration' => all.phase4d.productConcentrationExplanation,
    'cross_sell_opportunity' => all.phase4d.crossSellOpportunityExplanation,
    _ => all.company.navRecommendationsDescription,
  };
}

String _action(BuildContext context, String action) {
  final all = AvenqoLocaleScope.translationsOf(context);
  return switch (action) {
    'review_product_performance' => all.phase4d.reviewProductPerformance,
    'review_product_concentration' => all.phase4d.reviewProductConcentration,
    'review_cross_sell_opportunities' => all.phase4d.reviewCrossSellOpportunities,
    'review_sales_performance' => all.company.navSalesLabel,
    _ => all.company.navRecommendationsLabel,
  };
}

String _evidence(Phase4dStrings strings, String type, Map<String, dynamic> evidence) {
  String apply(String template, Map<String, dynamic> values) {
    var result = template;
    for (final entry in values.entries) {
      result = result.replaceAll('{${entry.key}}', '${entry.value}');
    }
    return result;
  }
  if (type == 'product_concentration') {
    return apply(strings.concentrationEvidence, {
      'entity': evidence['product_name'] ?? evidence['product_id'] ?? '—',
      'current': evidence['revenue_share'] ?? '—',
    });
  }
  if (type == 'cross_sell_opportunity') {
    return apply(strings.customerEvidence, {'current': evidence['customer_count'] ?? 0});
  }
  return apply(strings.changeEvidence, {
    'entity': evidence['product_name'] ?? evidence['product_id'] ?? '',
    'current': evidence['current'] ?? '—',
    'comparison': evidence['comparison'] ?? '—',
    'change': evidence['change_percent'] ?? '—',
  });
}

IconData _icon(String type) => switch (type) {
      'revenue_decline' || 'product_decline' => Icons.trending_down,
      'revenue_growth' || 'product_growth' => Icons.trending_up,
      'product_concentration' => Icons.donut_large,
      'cross_sell_opportunity' => Icons.join_inner,
      _ => Icons.lightbulb_outline,
    };

Color _priorityColor(String priority) => switch (priority) {
      'critical' => const Color(0xFFB42318),
      'high' => const Color(0xFFD1414B),
      'medium' => const Color(0xFFC97912),
      _ => const Color(0xFF087CF0),
    };

class _PriorityBadge extends StatelessWidget {
  const _PriorityBadge({required this.label, required this.priority});
  final String label;
  final String priority;
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
        decoration: BoxDecoration(
          color: _priorityColor(priority).withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(6),
        ),
        child: Text(label, style: TextStyle(color: _priorityColor(priority), fontSize: 12, fontWeight: FontWeight.w700)),
      );
}

class _RecommendationState extends StatelessWidget {
  const _RecommendationState({required this.message, this.icon = Icons.lightbulb_outline, this.action, this.onPressed});
  final String message;
  final IconData icon;
  final String? action;
  final VoidCallback? onPressed;
  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(color: colors.surface, border: Border.all(color: colors.line), borderRadius: BorderRadius.circular(8)),
      child: Wrap(spacing: 12, runSpacing: 10, crossAxisAlignment: WrapCrossAlignment.center, children: [
        Icon(icon, color: const Color(0xFF087CF0)),
        Text(message, style: TextStyle(color: colors.ink)),
        if (action != null && onPressed != null) FilledButton(onPressed: onPressed, child: Text(action!)),
      ]),
    );
  }
}