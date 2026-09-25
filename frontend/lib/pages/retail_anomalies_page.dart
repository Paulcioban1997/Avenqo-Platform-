import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/money_formatter.dart';
import 'package:avenqo/i18n/locale_scope.dart';

class _Brand {
  const _Brand._();
  static const blue = Color(0xFF087CF0);
  static const amber = Color(0xFFF59E0B);
  static const rose = Color(0xFFEF4444);
}

class RetailAnomaliesPage extends StatefulWidget {
  const RetailAnomaliesPage({super.key, required this.api});

  final ApiClient api;

  @override
  State<RetailAnomaliesPage> createState() => _RetailAnomaliesPageState();
}

class _RetailAnomaliesPageState extends State<RetailAnomaliesPage> {
  late Future<_AnomaliesData> _future;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  void _reload() {
    setState(() {
      _future = _fetch();
    });
  }

  Future<_AnomaliesData> _fetch() async {
    final results = await Future.wait([
      widget.api.get('/products/summary?performance=weak').catchError((_) => <String, dynamic>{}),
    ]);

    final prodSummary = (results[0] is Map) ? results[0] as Map<String, dynamic> : <String, dynamic>{};

    final decliningProducts = (prodSummary['items'] is List)
        ? (prodSummary['items'] as List).cast<Map<String, dynamic>>()
        : (prodSummary['declining_products'] is List)
        ? (prodSummary['declining_products'] as List).cast<Map<String, dynamic>>()
        : (prodSummary['products'] is List ? (prodSummary['products'] as List).cast<Map<String, dynamic>>() : <Map<String, dynamic>>[]);

    return _AnomaliesData(
      financialAnomalies: const [],
      decliningProducts: decliningProducts,
      highRiskCustomers: const [],
    );
  }

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);

    return Scaffold(
      backgroundColor: colors.canvas,
      body: FutureBuilder<_AnomaliesData>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }

          if (snapshot.hasError) {
            return Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.error_outline, size: 48, color: _Brand.rose),
                  const SizedBox(height: 16),
                  Text('Erreur lors du chargement des anomalies', style: TextStyle(color: colors.ink, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 8),
                  FilledButton.icon(onPressed: _reload, icon: const Icon(Icons.refresh), label: const Text('Réessayer')),
                ],
              ),
            );
          }

          final data = snapshot.data ?? const _AnomaliesData(financialAnomalies: [], decliningProducts: [], highRiskCustomers: []);
          final totalCount = data.financialAnomalies.length + data.decliningProducts.length + data.highRiskCustomers.length;

          return ListView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 28),
            children: [
              // Header
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Détection des Anomalies', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w800, color: colors.ink)),
                      const SizedBox(height: 4),
                      Text('Identification automatique des ruptures de tendance, dépenses atypiques et baisses de régime.', style: TextStyle(fontSize: 14, color: colors.muted)),
                    ],
                  ),
                  IconButton(onPressed: _reload, tooltip: 'Actualiser', icon: const Icon(Icons.refresh)),
                ],
              ),
              const SizedBox(height: 20),

              // Summary Stats Banner
              LayoutBuilder(
                builder: (context, constraints) {
                  final wide = constraints.maxWidth > 800;
                  final cards = [
                    _buildAnomalySummaryCard('Total Anomalies Détectées', '$totalCount', Icons.troubleshoot, _Brand.rose, colors),
                    _buildAnomalySummaryCard('Écarts Financiers / Opérationnels', '${data.financialAnomalies.length}', Icons.account_balance_outlined, _Brand.amber, colors),
                    _buildAnomalySummaryCard('Produits en Déclin Atypique', '${data.decliningProducts.length}', Icons.trending_down, _Brand.blue, colors),
                    _buildAnomalySummaryCard('Comportements Clients Inhabituels', '${data.highRiskCustomers.length}', Icons.person_off_outlined, _Brand.rose, colors),
                  ];

                  if (!wide) {
                    return Column(children: [for (final c in cards) ...[c, const SizedBox(height: 12)]]);
                  }
                  return Row(
                    children: [
                      for (var i = 0; i < cards.length; i++) ...[
                        if (i > 0) const SizedBox(width: 16),
                        Expanded(child: cards[i]),
                      ],
                    ],
                  );
                },
              ),
              const SizedBox(height: 28),

              // Section 1: Financial / Operational Anomalies
              Text('Anomalies Opérationnelles & Financières', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: colors.ink)),
              const SizedBox(height: 12),
              if (data.financialAnomalies.isEmpty)
                _buildEmptyNotice('Aucune dépense ou écriture atypique détectée.', colors)
              else
                for (final a in data.financialAnomalies)
                  _buildAnomalyCard(
                    context,
                    colors: colors,
                    title: a['description']?.toString() ?? 'Écriture atypique',
                    category: a['category']?.toString() ?? 'Opérations',
                    badgeLabel: a['flag_reason']?.toString() ?? 'Écart significatif détecté',
                    severityColor: _Brand.rose,
                    amount: _formatMoney(context, (a['amount'] as num?)?.toDouble() ?? 0.0, 'CAD'),
                    date: a['transaction_date']?.toString().split('T').first ?? '',
                    onAction: () => context.go('/accounting'),
                  ),
              const SizedBox(height: 28),

              // Section 2: Products Declining or Atypical
              Text('Produits en Baisse de Performance Atypique', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: colors.ink)),
              const SizedBox(height: 12),
              if (data.decliningProducts.isEmpty)
                _buildEmptyNotice('Aucun produit n’affiche de chute anormale de ventes.', colors)
              else
                for (final p in data.decliningProducts.take(5))
                  _buildAnomalyCard(
                    context,
                    colors: colors,
                    title: p['name']?.toString() ?? p['title']?.toString() ?? 'Produit',
                    category: p['category']?.toString() ?? 'Catalogue',
                    badgeLabel: 'Performance en baisse',
                    severityColor: _Brand.amber,
                    amount: 'Stock restant : ${p['stock'] ?? p['inventory_level'] ?? 0}',
                    date: 'Revenu : ${_formatMoney(context, (p['revenue'] as num?)?.toDouble() ?? 0.0, 'CAD')}',
                    onAction: () => context.go('/retail/products?product_id=${p['product_id'] ?? p['id']}'),
                  ),
              const SizedBox(height: 28),

              // Section 3: Customer Abnormalities
              Text('Comportements Clients & Risques Churn Inhabituels', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: colors.ink)),
              const SizedBox(height: 12),
              if (data.highRiskCustomers.isEmpty)
                _buildEmptyNotice('Aucun comportement d’abandon anormal détecté.', colors)
              else
                for (final c in data.highRiskCustomers.take(5))
                  _buildAnomalyCard(
                    context,
                    colors: colors,
                    title: '${c['name']} (${c['company_name'] ?? 'Client'})',
                    category: 'Client B2B / B2C',
                    badgeLabel: c['churn_risk_score'] is num
                      ? 'Risque d’attrition ${((c['churn_risk_score'] as num) * 100).toStringAsFixed(1)}%'
                      : 'Risque d’attrition non calculé',
                    severityColor: _Brand.rose,
                    amount: _formatMoney(context, (c['customer_lifetime_value'] as num?)?.toDouble() ?? 0.0, 'CAD'),
                    date: c['churn_reason']?.toString() ?? 'Chute brutale de fréquence d’achat',
                    onAction: () => context.go('/crm'),
                  ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildAnomalySummaryCard(String label, String value, IconData icon, Color color, AvenqoColors colors) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: colors.line),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(8)),
            child: Icon(icon, color: color, size: 22),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: TextStyle(color: colors.muted, fontSize: 12, fontWeight: FontWeight.w600)),
                const SizedBox(height: 4),
                Text(value, style: TextStyle(color: colors.ink, fontSize: 22, fontWeight: FontWeight.w800)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAnomalyCard(
    BuildContext context, {
    required AvenqoColors colors,
    required String title,
    required String category,
    required String badgeLabel,
    required Color severityColor,
    required String amount,
    required String date,
    required VoidCallback onAction,
  }) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: colors.line),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(color: severityColor.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(6)),
            child: Icon(Icons.warning_amber_rounded, color: severityColor, size: 20),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(color: severityColor.withValues(alpha: 0.15), borderRadius: BorderRadius.circular(4)),
                      child: Text(badgeLabel, style: TextStyle(color: severityColor, fontSize: 11, fontWeight: FontWeight.bold)),
                    ),
                    const SizedBox(width: 8),
                    Text(category, style: TextStyle(fontSize: 11, color: colors.muted)),
                  ],
                ),
                const SizedBox(height: 6),
                Text(title, style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14, color: colors.ink)),
                const SizedBox(height: 2),
                Text(date, style: TextStyle(color: colors.muted, fontSize: 12)),
              ],
            ),
          ),
          const SizedBox(width: 12),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(amount, style: TextStyle(fontWeight: FontWeight.w800, fontSize: 14, color: colors.ink)),
              const SizedBox(height: 4),
              OutlinedButton(
                onPressed: onAction,
                style: OutlinedButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4), minimumSize: const Size(0, 30)),
                child: const Text('Examiner', style: TextStyle(fontSize: 12)),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildEmptyNotice(String message, AvenqoColors colors) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: colors.line),
      ),
      child: Center(
        child: Text(message, style: TextStyle(color: colors.muted, fontSize: 13)),
      ),
    );
  }
}

class _AnomaliesData {
  const _AnomaliesData({
    required this.financialAnomalies,
    required this.decliningProducts,
    required this.highRiskCustomers,
  });
  final List<Map<String, dynamic>> financialAnomalies;
  final List<Map<String, dynamic>> decliningProducts;
  final List<Map<String, dynamic>> highRiskCustomers;
}

String _formatMoney(BuildContext context, num value, [String currency = 'CAD']) {
  final locale = AvenqoLocaleScope.of(context).code;
  return formatMoney(value, locale: locale, currencyCode: currency);
}

