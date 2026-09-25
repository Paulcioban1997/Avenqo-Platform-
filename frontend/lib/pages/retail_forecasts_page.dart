import 'package:flutter/material.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/money_formatter.dart';
import 'package:avenqo/i18n/locale_scope.dart';

class _Brand {
  const _Brand._();
  static const blue = Color(0xFF087CF0);
  static const emerald = Color(0xFF10B981);
  static const purple = Color(0xFF8B5CF6);
  static const amber = Color(0xFFF59E0B);
  static const rose = Color(0xFFEF4444);
}

class RetailForecastsPage extends StatefulWidget {
  const RetailForecastsPage({super.key, required this.api});

  final ApiClient api;

  @override
  State<RetailForecastsPage> createState() => _RetailForecastsPageState();
}

class _RetailForecastsPageState extends State<RetailForecastsPage> {
  late Future<_ForecastData> _future;

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

  Future<_ForecastData> _fetch() async {
    final results = await Future.wait([
      widget.api.get('/sales/summary?period=last_30_days').catchError((_) => <String, dynamic>{}),
      widget.api.get('/recommendations').catchError((_) => <String, dynamic>{}),
    ]);

    final sales = (results[0] is Map) ? results[0] as Map<String, dynamic> : <String, dynamic>{};
    final recMap = (results[1] is Map) ? results[1] as Map<String, dynamic> : <String, dynamic>{};
    final recs = (recMap['recommendations'] is List)
        ? (recMap['recommendations'] as List).cast<Map<String, dynamic>>()
        : <Map<String, dynamic>>[];

    return _ForecastData(sales: sales, recommendations: recs);
  }

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);

    return Scaffold(
      backgroundColor: colors.canvas,
      body: FutureBuilder<_ForecastData>(
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
                  Text('Erreur lors du calcul des prévisions', style: TextStyle(color: colors.ink, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 8),
                  FilledButton.icon(onPressed: _reload, icon: const Icon(Icons.refresh), label: const Text('Réessayer')),
                ],
              ),
            );
          }

          final data = snapshot.data ?? const _ForecastData(sales: {}, recommendations: []);
          final sales = data.sales;
          final summary = sales['summary'] as Map<String, dynamic>? ?? {};
          final forecastData = sales['forecast'] as Map<String, dynamic>?;
          final projectedSales =
              (forecastData?['forecasted_total'] as num?)?.toDouble();
          final confidence = forecastData?['confidence']?.toString();
          final forecastMethod = forecastData?['method']?.toString();
          final forecastDescription = confidence != null
              ? 'Confiance mesurée : $confidence'
              : forecastMethod == 'historical_weekly_mean'
                  ? 'Projection basée sur la moyenne des 4 dernières semaines observées'
                  : 'Prévision indisponible : historique insuffisant';
          final disclaimer = forecastData?['disclaimer']?.toString() ??
              'Aucune prévision Retail n’est disponible sans un modèle actif pour ce tenant.';

          final currentRevenue = (summary['revenue'] as num?)?.toDouble() ?? 0.0;
          final ordersCount = summary['orders'] ?? 0;

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
                      Row(
                        children: [
                          Text('Prévisions & Projections IA', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w800, color: colors.ink)),
                          const SizedBox(width: 12),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                            decoration: BoxDecoration(
                              color: _Brand.purple.withValues(alpha: 0.15),
                              borderRadius: BorderRadius.circular(6),
                              border: Border.all(color: _Brand.purple.withValues(alpha: 0.3)),
                            ),
                            child: const Text('PRÉVISION IA', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: _Brand.purple)),
                          ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text('Projections calculées par les modèles de prévision Avenqo à partir des données historiques.', style: TextStyle(fontSize: 14, color: colors.muted)),
                    ],
                  ),
                  IconButton(onPressed: _reload, tooltip: 'Recalculer', icon: const Icon(Icons.refresh)),
                ],
              ),
              const SizedBox(height: 20),

              // Prominent Transparency Notice
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: _Brand.amber.withValues(alpha: 0.08),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: _Brand.amber.withValues(alpha: 0.3)),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.info_outline, color: _Brand.amber, size: 22),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'ENGAGEMENT DE TRANSPARENCE — AUCUNE ESTIMATION DÉGUISÉE',
                            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12, color: _Brand.amber, letterSpacing: 0.5),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            disclaimer,
                            style: TextStyle(fontSize: 13, color: colors.ink, height: 1.35),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),

              // Forecast Metric Cards
              LayoutBuilder(
                builder: (context, constraints) {
                  final wide = constraints.maxWidth > 800;
                  final cards = [
                    _buildForecastMetric('Chiffre d’affaires actuel (30j)', _formatMoney(context, currentRevenue, 'CAD'), 'Donnée confirmée', colors, isActual: true),
                    _buildForecastMetric(
                      'Ventes projetées',
                      projectedSales == null
                          ? '—'
                          : _formatMoney(context, projectedSales, 'CAD'),
                      forecastDescription,
                      colors,
                      isActual: false,
                    ),
                    _buildForecastMetric('Commandes observées', '$ordersCount', 'Base de calcul validée', colors, isActual: true),
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
              const SizedBox(height: 24),

              // Predictive Recommendations Impact
              Text('Impacts Prévisionnels Recommandés par l’IA', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: colors.ink)),
              const SizedBox(height: 12),
              if (data.recommendations.isEmpty)
                Container(
                  padding: const EdgeInsets.all(24),
                  decoration: BoxDecoration(color: colors.surface, borderRadius: BorderRadius.circular(10), border: Border.all(color: colors.line)),
                  child: Center(child: Text('Aucune projection de recommandation active pour le moment.', style: TextStyle(color: colors.muted))),
                )
              else
                for (final rec in data.recommendations.take(4))
                  Container(
                    margin: const EdgeInsets.only(bottom: 12),
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: colors.surface,
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: colors.line),
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Container(
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(color: _Brand.purple.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(8)),
                          child: const Icon(Icons.trending_up, color: _Brand.purple, size: 22),
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
                                    decoration: BoxDecoration(color: _Brand.purple.withValues(alpha: 0.15), borderRadius: BorderRadius.circular(4)),
                                    child: const Text('PRÉVISION IA', style: TextStyle(color: _Brand.purple, fontSize: 10, fontWeight: FontWeight.bold)),
                                  ),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: Text(
                                      rec['title']?.toString() ?? 'Action recommandée',
                                      style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14, color: colors.ink),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 6),
                              Text(rec['explanation']?.toString() ?? '', style: TextStyle(color: colors.muted, fontSize: 13, height: 1.35)),
                              if (rec['suggested_action'] != null) ...[
                                const SizedBox(height: 8),
                                Text(
                                  'Action suggérée : ${rec['suggested_action']}',
                                  style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 12, color: _Brand.blue),
                                ),
                              ],
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildForecastMetric(String label, String value, String subtext, AvenqoColors colors, {required bool isActual}) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: isActual ? colors.line : _Brand.purple.withValues(alpha: 0.4)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(label, style: TextStyle(color: colors.muted, fontSize: 12, fontWeight: FontWeight.w600)),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: (isActual ? _Brand.emerald : _Brand.purple).withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(
                  isActual ? 'RÉEL' : 'PRÉVISION IA',
                  style: TextStyle(
                    fontSize: 9,
                    fontWeight: FontWeight.w800,
                    color: isActual ? _Brand.emerald : _Brand.purple,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(value, style: TextStyle(color: colors.ink, fontSize: 22, fontWeight: FontWeight.w800)),
          const SizedBox(height: 4),
          Text(subtext, style: TextStyle(color: isActual ? colors.muted : _Brand.purple, fontSize: 11, fontWeight: FontWeight.w500)),
        ],
      ),
    );
  }
}

class _ForecastData {
  const _ForecastData({required this.sales, required this.recommendations});
  final Map<String, dynamic> sales;
  final List<Map<String, dynamic>> recommendations;
}

String _formatMoney(BuildContext context, num value, [String currency = 'CAD']) {
  final locale = AvenqoLocaleScope.of(context).code;
  return formatMoney(value, locale: locale, currencyCode: currency);
}

