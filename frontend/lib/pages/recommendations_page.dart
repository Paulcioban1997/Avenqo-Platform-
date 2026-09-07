import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/money_formatter.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/i18n/translations.dart';

typedef RecommendationsLoader = Future<Map<String, dynamic>> Function();
typedef RecommendationProductLoader =
    Future<Map<String, dynamic>> Function(String productId);

class RecommendationsPage extends StatefulWidget {
  const RecommendationsPage({
    super.key,
    required this.api,
    this.loader,
    this.productLoader,
    this.onNavigate,
  });

  final ApiClient api;
  final RecommendationsLoader? loader;
  final RecommendationProductLoader? productLoader;
  final ValueChanged<String>? onNavigate;

  @override
  State<RecommendationsPage> createState() => _RecommendationsPageState();
}

class _RecommendationsPageState extends State<RecommendationsPage> {
  late Future<Map<String, dynamic>> _future = _load();

  Future<Map<String, dynamic>> _load() async {
    final loader = widget.loader;
    final data = loader != null
        ? await loader()
        : await widget.api.get('/recommendations') as Map<String, dynamic>;
    final normalized = _applyProductDetails(data, const {});
    unawaited(_enrichProductIdentities(normalized));
    return normalized;
  }

  Future<void> _enrichProductIdentities(Map<String, dynamic> data) async {
    final items = (data['recommendations'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>();
    final productIds = <String>{};
    for (final item in items) {
      if (!_isProductRecommendation(item)) continue;
      final product = _productIdentity(item);
      final productId = _textValue(product?['id']);
      if (productId != null && _textValue(product?['name']) == null) {
        productIds.add(productId);
      }
    }

    final details = <String, Map<String, dynamic>>{};
    await Future.wait(
      productIds.map((productId) async {
        try {
          final loader = widget.productLoader;
          final detail = loader != null
              ? await loader(productId)
              : await widget.api.get(
                      '/products/${Uri.encodeComponent(productId)}',
                    )
                    as Map<String, dynamic>;
          details[productId] = detail;
        } on Object {
          // The recommendation remains useful with its real SKU when detail lookup fails.
        }
      }),
    );
    if (details.isEmpty || !mounted) return;
    final enriched = _applyProductDetails(data, details);
    setState(() {
      _future = Future.value(enriched);
    });
  }

  Map<String, dynamic> _applyProductDetails(
    Map<String, dynamic> data,
    Map<String, Map<String, dynamic>> details,
  ) {
    final items = (data['recommendations'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>();
    final enriched = items
        .map((item) {
          if (!_isProductRecommendation(item)) return item;
          final product = _productIdentity(item);
          final productId = _textValue(product?['id']);
          final detail = productId == null ? null : details[productId];
          final identity = _mergeProductIdentity(product, detail);
          return <String, dynamic>{
            ...item,
            'affected_product': ?identity,
            if (productId != null)
              'action_route':
                  '/retail/products?product_id=${Uri.encodeQueryComponent(productId)}',
          };
        })
        .toList(growable: false);
    return {...data, 'recommendations': enriched};
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
          Text(
            company.navRecommendationsLabel,
            style: Theme.of(context).textTheme.headlineMedium,
          ),
          const SizedBox(height: 6),
          Text(
            company.navRecommendationsDescription,
            style: TextStyle(color: colors.muted),
          ),
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
            _RecommendationsContent(
              data: snapshot.data!,
              onNavigate: widget.onNavigate,
            ),
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
          _RecommendationState(
            message: strings.partialReady,
            icon: Icons.info_outline,
          ),
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
                    SizedBox(
                      width: width,
                      child: _RecommendationCard(
                        item: item,
                        currency: data['currency']?.toString() ?? 'USD',
                        onNavigate: onNavigate,
                      ),
                    ),
                ],
              );
            },
          ),
      ],
    );
  }
}

class _RecommendationCard extends StatelessWidget {
  const _RecommendationCard({
    required this.item,
    required this.currency,
    required this.onNavigate,
  });
  final Map<String, dynamic> item;
  final String currency;
  final ValueChanged<String>? onNavigate;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final strings = AvenqoLocaleScope.translationsOf(context).phase4d;
    final type = item['type']?.toString() ?? '';
    final priority = item['priority']?.toString() ?? 'informational';
    final route = item['action_route']?.toString();
    final evidence = item['evidence'] as Map<String, dynamic>? ?? const {};
    final product = item['affected_product'] as Map<String, dynamic>?;
    final locale = Localizations.localeOf(context).toLanguageTag();
    String money(dynamic value) => value is num
        ? formatMoney(value, locale: locale, currencyCode: currency)
        : '—';
    String percent(dynamic value) =>
        value is num ? NumberFormat.decimalPattern(locale).format(value) : '—';
    final isProduct = type.startsWith('product_') && product != null;
    final productId = _textValue(product?['id']);
    final productName = _textValue(product?['name']);
    final productLabel = productName ?? productId;
    final title = _title(context, type);
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
                  isProduct && productLabel != null
                      ? '$title · $productLabel'
                      : title,
                  style: TextStyle(
                    color: colors.ink,
                    fontSize: 17,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              _PriorityBadge(
                label:
                    '${strings.priorityLabel}: ${strings.severityName(priority)}',
                priority: priority,
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            _explanation(context, type),
            style: TextStyle(color: colors.muted),
          ),
          if (isProduct) ...[
            const SizedBox(height: 16),
            if (productName != null)
              _EvidenceLine(
                label: strings.productLabel,
                value: productName,
                emphasized: true,
              ),
            if (productId != null)
              _EvidenceLine(
                label: strings.skuLabel,
                value: productId,
                emphasized: productName == null,
              ),
            if (product['category'] != null)
              _EvidenceLine(
                label: strings.categoryLabel,
                value: product['category'].toString(),
              ),
          ],
          const SizedBox(height: 16),
          Text(
            strings.evidenceLabel,
            style: TextStyle(color: colors.ink, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 4),
          if (isProduct) ...[
            _EvidenceLine(
              label: strings.currentPeriodLabel,
              value: money(evidence['current']),
            ),
            _EvidenceLine(
              label: strings.previousPeriodLabel,
              value: money(evidence['comparison']),
            ),
            _EvidenceLine(
              label: strings.changeLabel,
              value: '${percent(evidence['change_percent'])}%',
            ),
            _EvidenceLine(
              label: strings.businessImpactLabel,
              value: money(item['estimated_impact']),
            ),
            _EvidenceLine(
              label: strings.periodLabel,
              value: _period(locale, evidence['period']),
            ),
          ] else
            Text(
              _evidence(strings, type, evidence),
              style: TextStyle(color: colors.muted),
            ),
          const SizedBox(height: 12),
          _EvidenceLine(
            label: strings.severityReasonLabel,
            value: strings.severityReason(
              item['severity_reason']?.toString() ?? '',
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: Text(
                  '${strings.suggestedActionLabel}: ${_action(context, item['suggested_action']?.toString() ?? '')}',
                  style: TextStyle(
                    color: colors.ink,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              if (route != null)
                IconButton(
                  tooltip: _action(
                    context,
                    item['suggested_action']?.toString() ?? '',
                  ),
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

bool _isProductRecommendation(Map<String, dynamic> item) =>
    item['type']?.toString().startsWith('product_') ?? false;

String? _textValue(dynamic value) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty ? null : text;
}

Map<String, dynamic>? _productIdentity(Map<String, dynamic> item) {
  final rawProduct = item['affected_product'];
  final product = rawProduct is Map<String, dynamic>
      ? rawProduct
      : const <String, dynamic>{};
  final rawEvidence = item['evidence'];
  final evidence = rawEvidence is Map<String, dynamic>
      ? rawEvidence
      : const <String, dynamic>{};
  final id =
      _textValue(product['id']) ??
      _textValue(evidence['product_id']) ??
      _textValue(item['affected_entity']);
  final name =
      _textValue(product['name']) ?? _textValue(evidence['product_name']);
  final category =
      _textValue(product['category']) ?? _textValue(evidence['category']);
  if (id == null && name == null && category == null) return null;
  return {
    'id': ?id,
    'name': ?name,
    'category': ?category,
  };
}

Map<String, dynamic>? _mergeProductIdentity(
  Map<String, dynamic>? product,
  Map<String, dynamic>? detail,
) {
  final id = _textValue(product?['id']) ?? _textValue(detail?['product_id']);
  final name = _textValue(product?['name']) ?? _textValue(detail?['name']);
  final category =
      _textValue(product?['category']) ?? _textValue(detail?['category']);
  if (id == null && name == null && category == null) return null;
  return {
    'id': ?id,
    'name': ?name,
    'category': ?category,
  };
}

String _explanation(BuildContext context, String type) {
  final all = AvenqoLocaleScope.translationsOf(context);
  return switch (type) {
    'revenue_decline' ||
    'revenue_growth' => all.dashboardHome.revenueChangedExplanation,
    'product_decline' ||
    'product_growth' => all.phase4d.productRevenueChangedExplanation,
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
    'review_cross_sell_opportunities' =>
      all.phase4d.reviewCrossSellOpportunities,
    'review_sales_performance' => all.company.navSalesLabel,
    _ => all.company.navRecommendationsLabel,
  };
}

String _evidence(
  Phase4dStrings strings,
  String type,
  Map<String, dynamic> evidence,
) {
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
    return apply(strings.customerEvidence, {
      'current': evidence['customer_count'] ?? 0,
    });
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
    child: Text(
      label,
      style: TextStyle(
        color: _priorityColor(priority),
        fontSize: 12,
        fontWeight: FontWeight.w700,
      ),
    ),
  );
}

class _RecommendationState extends StatelessWidget {
  const _RecommendationState({
    required this.message,
    this.icon = Icons.lightbulb_outline,
    this.action,
    this.onPressed,
  });
  final String message;
  final IconData icon;
  final String? action;
  final VoidCallback? onPressed;
  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border.all(color: colors.line),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Wrap(
        spacing: 12,
        runSpacing: 10,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Icon(icon, color: const Color(0xFF087CF0)),
          Text(message, style: TextStyle(color: colors.ink)),
          if (action != null && onPressed != null)
            FilledButton(onPressed: onPressed, child: Text(action!)),
        ],
      ),
    );
  }
}

String _period(String locale, dynamic value) {
  if (value is! Map<String, dynamic>) return value?.toString() ?? '—';
  String date(dynamic raw) => raw == null
      ? '—'
      : DateFormat.yMd(locale).format(DateTime.parse(raw.toString()));
  return '${date(value['comparison_start'])} - ${date(value['comparison_end'])} / '
      '${date(value['start'])} - ${date(value['end'])}';
}

class _EvidenceLine extends StatelessWidget {
  const _EvidenceLine({
    required this.label,
    required this.value,
    this.emphasized = false,
  });

  final String label;
  final String value;
  final bool emphasized;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 5),
      child: Text.rich(
        TextSpan(
          style: TextStyle(color: colors.muted),
          children: [
            TextSpan(
              text: '$label: ',
              style: TextStyle(color: colors.ink, fontWeight: FontWeight.w600),
            ),
            TextSpan(
              text: value,
              style: emphasized
                  ? TextStyle(color: colors.ink, fontWeight: FontWeight.w700)
                  : null,
            ),
          ],
        ),
      ),
    );
  }
}
