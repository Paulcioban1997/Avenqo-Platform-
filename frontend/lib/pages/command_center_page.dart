import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/core/money_formatter.dart';
import 'package:avenqo/i18n/locale_scope.dart';

class _Brand {
  const _Brand._();
  static const blue = Color(0xFF087CF0);
  static const emerald = Color(0xFF10B981);
  static const amber = Color(0xFFF59E0B);
  static const rose = Color(0xFFEF4444);
  static const purple = Color(0xFF8B5CF6);
}

class CommandCenterData {
  const CommandCenterData({
    required this.crossAgent,
    required this.crmSummary,
    required this.accountingOverview,
    required this.retailDashboard,
    required this.connections,
    required this.highRiskContacts,
    required this.unpaidInvoices,
  });

  final Map<String, dynamic> crossAgent;
  final Map<String, dynamic> crmSummary;
  final Map<String, dynamic> accountingOverview;
  final Map<String, dynamic> retailDashboard;
  final List<Map<String, dynamic>> connections;
  final List<Map<String, dynamic>> highRiskContacts;
  final List<Map<String, dynamic>> unpaidInvoices;

  factory CommandCenterData.empty() => const CommandCenterData(
        crossAgent: {},
        crmSummary: {},
        accountingOverview: {},
        retailDashboard: {},
        connections: [],
        highRiskContacts: [],
        unpaidInvoices: [],
      );
}

class CommandCenterPage extends StatefulWidget {
  const CommandCenterPage({super.key, required this.auth});

  final AuthController auth;

  @override
  State<CommandCenterPage> createState() => _CommandCenterPageState();
}

class _CommandCenterPageState extends State<CommandCenterPage> {
  late Future<CommandCenterData> _future;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  void _reload() {
    setState(() {
      _future = _fetchData();
    });
  }

  Future<CommandCenterData> _fetchData() async {
    final api = widget.auth.api;
    final results = await Future.wait([
      api.get('/cross-agent/synthesis').catchError((_) => <String, dynamic>{}),
      api.get('/crm/summary').catchError((_) => <String, dynamic>{}),
      api.get('/accounting/overview').catchError((_) => <String, dynamic>{}),
      api.get('/dashboard').catchError((_) => <String, dynamic>{}),
      api.get('/connectors').catchError((_) => <dynamic>[]),
      api.get('/crm/contacts/high-risk?limit=5').catchError((_) => <dynamic>[]),
      api.get('/accounting/invoices/unpaid').catchError((_) => <String, dynamic>{}),
    ]);

    final crossAgent = (results[0] is Map) ? results[0] as Map<String, dynamic> : <String, dynamic>{};
    final crmSummary = (results[1] is Map) ? results[1] as Map<String, dynamic> : <String, dynamic>{};
    final accountingOverview = (results[2] is Map) ? results[2] as Map<String, dynamic> : <String, dynamic>{};
    final retailDashboard = (results[3] is Map) ? results[3] as Map<String, dynamic> : <String, dynamic>{};
    final connections = (results[4] is List) ? (results[4] as List).cast<Map<String, dynamic>>() : <Map<String, dynamic>>[];
    final highRiskContacts = (results[5] is List) ? (results[5] as List).cast<Map<String, dynamic>>() : <Map<String, dynamic>>[];
    final unpaidInvMap = (results[6] is Map) ? results[6] as Map<String, dynamic> : <String, dynamic>{};
    final unpaidInvoices = (unpaidInvMap['invoices'] is List) ? (unpaidInvMap['invoices'] as List).cast<Map<String, dynamic>>() : <Map<String, dynamic>>[];

    return CommandCenterData(
      crossAgent: crossAgent,
      crmSummary: crmSummary,
      accountingOverview: accountingOverview,
      retailDashboard: retailDashboard,
      connections: connections,
      highRiskContacts: highRiskContacts,
      unpaidInvoices: unpaidInvoices,
    );
  }

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final companyName = widget.auth.company?['name'] as String? ?? 'Avenqo';

    return Scaffold(
      backgroundColor: colors.canvas,
      body: FutureBuilder<CommandCenterData>(
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
                  Text(
                    'Erreur de synchronisation avec le Command Center',
                    style: TextStyle(color: colors.ink, fontWeight: FontWeight.bold, fontSize: 16),
                  ),
                  const SizedBox(height: 8),
                  FilledButton.icon(
                    onPressed: _reload,
                    icon: const Icon(Icons.refresh, size: 18),
                    label: const Text('Réessayer'),
                  ),
                ],
              ),
            );
          }

          final data = snapshot.data ?? CommandCenterData.empty();
          return _buildDashboardContent(context, data, companyName, colors);
        },
      ),
    );
  }

  Widget _buildDashboardContent(
    BuildContext context,
    CommandCenterData data,
    String companyName,
    AvenqoColors colors,
  ) {
    final translations = AvenqoLocaleScope.translationsOf(context);
    final agentStrings = translations.agents;
    final pillars = data.crossAgent['pillars'] as Map<String, dynamic>? ?? {};
    final correlations = data.crossAgent['cross_domain_correlations'] as Map<String, dynamic>? ?? {};
    final strategicBalance = correlations['strategic_balance'] as Map<String, dynamic>? ?? {};
    final churnExposure = correlations['financial_churn_exposure'] as Map<String, dynamic>? ?? {};
    final insights = (data.crossAgent['strategic_insights'] as List<dynamic>? ?? []).cast<String>();

    final retailPillar = pillars['retail'] as Map<String, dynamic>? ?? {};
    final crmPillar = pillars['crm'] as Map<String, dynamic>? ?? {};
    final acctPillar = pillars['accounting'] as Map<String, dynamic>? ?? {};
    final acctActuals = acctPillar['confirmed_actuals'] as Map<String, dynamic>? ?? {};

    // Alert calculation
    final lowStockSamples = (retailPillar['low_stock_samples'] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();
    final lowStockCount = (retailPillar['low_stock_alerts_count'] as num?)?.toInt() ?? lowStockSamples.length;
    final overdueInvoices = data.unpaidInvoices.where((i) => ((i['days_overdue'] as num?)?.toInt() ?? 0) > 0).toList();
    final highRiskCount = data.highRiskContacts.length;

    final businessHealth = strategicBalance['overall_business_health']?.toString() ?? 'strong';
    final netConfirmed = (strategicBalance['net_confirmed_income'] as num?)?.toDouble() ?? (acctActuals['net_income'] as num?)?.toDouble() ?? 0.0;
    final pipelineValue = (strategicBalance['pipeline_potential_revenue'] as num?)?.toDouble() ?? (crmPillar['pipeline_value'] as num?)?.toDouble() ?? 0.0;
    final projectedCash = (strategicBalance['projected_cash_flow_30d'] as num?)?.toDouble() ?? 0.0;

    return RefreshIndicator(
      onRefresh: () async => _reload(),
      child: ListView(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 28),
        children: [
          // Header Bar
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                          decoration: BoxDecoration(
                            color: _Brand.blue.withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(6),
                            border: Border.all(color: _Brand.blue.withValues(alpha: 0.3)),
                          ),
                          child: const Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(Icons.hub_outlined, size: 14, color: _Brand.blue),
                              SizedBox(width: 6),
                              Text(
                                'COMMAND CENTER GLOBAL',
                                style: TextStyle(
                                  fontSize: 11,
                                  fontWeight: FontWeight.w800,
                                  color: _Brand.blue,
                                  letterSpacing: 0.8,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Tableau de bord — $companyName',
                      style: TextStyle(
                        fontSize: 28,
                        fontWeight: FontWeight.w800,
                        color: colors.ink,
                        letterSpacing: -0.5,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Synthèse stratégique unifiée en temps réel (${agentStrings.value('retailName')} ↔ ${agentStrings.value('crmName')} ↔ ${agentStrings.value('accountingName')}).',
                      style: TextStyle(fontSize: 14, color: colors.muted),
                    ),
                  ],
                ),
              ),
              Row(
                children: [
                  IconButton(
                    onPressed: _reload,
                    tooltip: 'Actualiser',
                    icon: const Icon(Icons.refresh),
                  ),
                  const SizedBox(width: 8),
                  FilledButton.icon(
                    onPressed: () => context.go('/assistant'),
                    style: FilledButton.styleFrom(
                      backgroundColor: _Brand.blue,
                      foregroundColor: Colors.white,
                    ),
                    icon: const Icon(Icons.auto_awesome, size: 16),
                    label: Text(translations.company.navAssistantLabel),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 24),

          // Business Health Banner
          _buildHealthBanner(context, colors, businessHealth, netConfirmed, pipelineValue, projectedCash),
          const SizedBox(height: 24),

          // Section 1: "Ce qui demande votre attention"
          _buildAttentionSection(context, colors, lowStockCount, lowStockSamples, data.highRiskContacts, overdueInvoices),
          const SizedBox(height: 24),

          // Section 2: "AI Central — Intelligence croisée"
          _buildCrossAgentIntelligenceSection(context, colors, churnExposure, insights),
          const SizedBox(height: 24),

          // Section 3: Pillars 360° Summary Cards
          Text(
            'Synthèse des 3 Domaines Avenqo',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: colors.ink),
          ),
          const SizedBox(height: 12),
          LayoutBuilder(
            builder: (context, constraints) {
              final wide = constraints.maxWidth > 900;
              final retailCard = _buildPillarCard(
                context,
                title: 'Retail Intelligence',
                icon: Icons.storefront_outlined,
                color: _Brand.blue,
                route: '/retail',
                stats: [
                  _StatItem('Chiffre d’affaires', _formatMoney(context, (retailPillar['orders_revenue'] as num?)?.toDouble() ?? 0.0, 'CAD')),
                  _StatItem('Commandes', '${retailPillar['orders_count'] ?? 0}'),
                  _StatItem('Produits catalogue', '${retailPillar['products_count'] ?? 0}'),
                  _StatItem('Stocks critiques', '$lowStockCount', isAlert: lowStockCount > 0),
                ],
              );
              final crmCard = _buildPillarCard(
                context,
                title: agentStrings.value('crmName'),
                icon: Icons.hub_outlined,
                color: _Brand.emerald,
                route: '/crm',
                isDemo: true,
                stats: [
                  _StatItem('Prospects actifs', '${crmPillar['confirmed_leads_count'] ?? data.crmSummary['total_leads'] ?? 0}'),
                  _StatItem('Pipeline total', _formatMoney(context, pipelineValue, 'CAD')),
                  _StatItem('Taux de conversion', '${data.crmSummary['conversion_rate_percent'] ?? 0}%'),
                  _StatItem('Clients à risque', '$highRiskCount', isAlert: highRiskCount > 0),
                ],
              );
              final acctCard = _buildPillarCard(
                context,
                title: agentStrings.value('accountingName'),
                icon: Icons.account_balance_outlined,
                color: _Brand.purple,
                route: '/accounting',
                isDemo: true,
                stats: [
                  _StatItem('Revenus confirmés', _formatMoney(context, (acctActuals['total_revenue'] as num?)?.toDouble() ?? 0.0, 'CAD')),
                  _StatItem('Dépenses totales', _formatMoney(context, (acctActuals['total_expenses'] as num?)?.toDouble() ?? 0.0, 'CAD')),
                  _StatItem('Marge brute', '${acctActuals['gross_margin_pct'] ?? 0}%'),
                  _StatItem('Créances en retard', _formatMoney(context, (acctActuals['total_overdue_receivables'] as num?)?.toDouble() ?? 0.0, 'CAD'), isAlert: (acctActuals['total_overdue_receivables'] as num? ?? 0) > 0),
                ],
              );

              if (!wide) {
                return Column(
                  children: [
                    retailCard,
                    const SizedBox(height: 16),
                    crmCard,
                    const SizedBox(height: 16),
                    acctCard,
                  ],
                );
              }

              return Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(child: retailCard),
                  const SizedBox(width: 16),
                  Expanded(child: crmCard),
                  const SizedBox(width: 16),
                  Expanded(child: acctCard),
                ],
              );
            },
          ),
          const SizedBox(height: 24),

          // Section 4: Connexions actives & Activité Récente
          LayoutBuilder(
            builder: (context, constraints) {
              final wide = constraints.maxWidth > 800;
              final connectionsWidget = _buildConnectionsCard(context, colors, data.connections);
              final activityWidget = _buildActivityCard(context, colors, data.retailDashboard['recent_activity'] as List<dynamic>? ?? []);

              if (!wide) {
                return Column(
                  children: [
                    connectionsWidget,
                    const SizedBox(height: 16),
                    activityWidget,
                  ],
                );
              }

              return Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(flex: 5, child: connectionsWidget),
                  const SizedBox(width: 16),
                  Expanded(flex: 5, child: activityWidget),
                ],
              );
            },
          ),
        ],
      ),
    );
  }

  Widget _buildHealthBanner(
    BuildContext context,
    AvenqoColors colors,
    String health,
    double netIncome,
    double pipeline,
    double cashFlow30d,
  ) {
    final isStrong = health == 'strong';
    final badgeColor = isStrong ? _Brand.emerald : _Brand.amber;
    final badgeText = isStrong ? 'SANTÉ GLOBALE SOLIDE & EN CROISSANCE' : 'SURVEILLANCE STRATÉGIQUE RECOMMANDÉE';

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: colors.line),
        boxShadow: [
          BoxShadow(color: Colors.black.withValues(alpha: 0.03), blurRadius: 10, offset: const Offset(0, 4)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Container(
                    width: 10,
                    height: 10,
                    decoration: BoxDecoration(color: badgeColor, shape: BoxShape.circle),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    badgeText,
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w800,
                      color: badgeColor,
                      letterSpacing: 0.5,
                    ),
                  ),
                ],
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: colors.canvas,
                  borderRadius: BorderRadius.circular(4),
                  border: Border.all(color: colors.line),
                ),
                child: Text(
                  'APIs réelles connectées',
                  style: TextStyle(fontSize: 11, color: colors.muted, fontWeight: FontWeight.w600),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          LayoutBuilder(
            builder: (context, constraints) {
              final wide = constraints.maxWidth > 650;
              final kpis = [
                _buildHealthMetric('Résultat Net Confirmé', _formatMoney(context, netIncome, 'CAD'), isPositive: netIncome >= 0),
                _buildHealthMetric('Pipeline Commercial', _formatMoney(context, pipeline, 'CAD')),
                _buildHealthMetric('Trésorerie Projetée (30j)', _formatMoney(context, cashFlow30d, 'CAD'), isProjection: true),
              ];
              if (!wide) {
                return Column(
                  children: [for (final k in kpis) ...[k, const SizedBox(height: 12)]],
                );
              }
              return Row(
                children: [
                  for (var i = 0; i < kpis.length; i++) ...[
                    if (i > 0) const SizedBox(width: 16),
                    Expanded(child: kpis[i]),
                  ],
                ],
              );
            },
          ),
        ],
      ),
    );
  }

  Widget _buildHealthMetric(String label, String value, {bool? isPositive, bool isProjection = false}) {
    final color = isPositive == null ? Colors.white : (isPositive ? _Brand.emerald : _Brand.rose);
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF0F172A),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  label,
                  style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 12, fontWeight: FontWeight.w600),
                ),
              ),
              if (isProjection)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
                  decoration: BoxDecoration(color: _Brand.purple.withValues(alpha: 0.3), borderRadius: BorderRadius.circular(3)),
                  child: const Text('PRÉVISION IA', style: TextStyle(color: _Brand.purple, fontSize: 9, fontWeight: FontWeight.bold)),
                ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            value,
            style: TextStyle(color: isPositive == null ? Colors.white : color, fontSize: 19, fontWeight: FontWeight.w800),
          ),
        ],
      ),
    );
  }

  Widget _buildAttentionSection(
    BuildContext context,
    AvenqoColors colors,
    int lowStockCount,
    List<Map<String, dynamic>> lowStockSamples,
    List<Map<String, dynamic>> highRiskContacts,
    List<Map<String, dynamic>> overdueInvoices,
  ) {
    final totalAlerts = (lowStockCount > 0 ? 1 : 0) + highRiskContacts.length + overdueInvoices.length;

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: totalAlerts > 0 ? _Brand.rose.withValues(alpha: 0.3) : colors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.warning_amber_rounded, size: 20, color: totalAlerts > 0 ? _Brand.rose : _Brand.emerald),
              const SizedBox(width: 8),
              Text(
                'Ce qui demande votre attention',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: colors.ink),
              ),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: totalAlerts > 0 ? _Brand.rose.withValues(alpha: 0.1) : _Brand.emerald.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  '$totalAlerts alerte${totalAlerts > 1 ? 's' : ''}',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                    color: totalAlerts > 0 ? _Brand.rose : _Brand.emerald,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          if (totalAlerts == 0)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Text(
                'Aucune alerte critique en cours. Tous les indicateurs opérationnels sont dans les seuils normaux.',
                style: TextStyle(color: colors.muted, fontSize: 14),
              ),
            )
          else ...[
            if (lowStockCount > 0)
              _buildAlertItem(
                context,
                icon: Icons.inventory_2_outlined,
                domain: 'RETAIL',
                color: _Brand.amber,
                title: '$lowStockCount produit(s) en stock critique ou rupture',
                subtitle: lowStockSamples.isNotEmpty
                    ? 'Exemple : ${lowStockSamples.first['product_name']} (${lowStockSamples.first['stock']} restant)'
                    : 'Risque de rupture prochaine de stock.',
                actionLabel: 'Gérer les stocks',
                onAction: () => context.go('/retail'),
              ),
            for (final c in highRiskContacts.take(2))
              _buildAlertItem(
                context,
                icon: Icons.person_off_outlined,
                domain: 'CRM',
                color: _Brand.rose,
                title: 'Risque d’attrition élevé : ${c['name']} (${c['company_name'] ?? 'Client'})',
                subtitle: c['churn_reason']?.toString() ?? 'Baisse marquée d\'activité commerciale.',
                actionLabel: 'Voir le prospect',
                onAction: () => context.go('/crm'),
              ),
            for (final inv in overdueInvoices.take(2))
              _buildAlertItem(
                context,
                icon: Icons.receipt_long_outlined,
                domain: 'ACCOUNTING',
                color: _Brand.rose,
                title: 'Facture en retard : ${inv['invoice_number']} — ${inv['party_name']}',
                subtitle: 'Montant dû : ${_formatMoney(context, (inv['total_amount'] as num?)?.toDouble() ?? 0.0, 'CAD')} (${inv['days_overdue'] ?? 0} jours de retard).',
                actionLabel: 'Gérer la relance',
                onAction: () => context.go('/accounting'),
              ),
          ],
        ],
      ),
    );
  }

  Widget _buildAlertItem(
    BuildContext context, {
    required IconData icon,
    required String domain,
    required Color color,
    required String title,
    required String subtitle,
    required String actionLabel,
    required VoidCallback onAction,
  }) {
    final colors = AvenqoColors.of(context);
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: colors.canvas,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(6)),
            child: Icon(icon, size: 18, color: color),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                      decoration: BoxDecoration(color: color.withValues(alpha: 0.15), borderRadius: BorderRadius.circular(3)),
                      child: Text(domain, style: TextStyle(color: color, fontSize: 10, fontWeight: FontWeight.w800)),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        title,
                        style: TextStyle(color: colors.ink, fontWeight: FontWeight.bold, fontSize: 13),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 3),
                Text(subtitle, style: TextStyle(color: colors.muted, fontSize: 12), overflow: TextOverflow.ellipsis),
              ],
            ),
          ),
          const SizedBox(width: 12),
          OutlinedButton(
            onPressed: onAction,
            style: OutlinedButton.styleFrom(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              minimumSize: const Size(0, 32),
            ),
            child: Text(actionLabel, style: const TextStyle(fontSize: 12)),
          ),
        ],
      ),
    );
  }

  Widget _buildCrossAgentIntelligenceSection(
    BuildContext context,
    AvenqoColors colors,
    Map<String, dynamic> churnExposure,
    List<String> insights,
  ) {
    final exposedInvoices = (churnExposure['exposed_invoices'] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();
    final totalExposed = (churnExposure['total_exposed_amount'] as num?)?.toDouble() ?? 0.0;

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: _Brand.purple.withValues(alpha: 0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.auto_awesome, size: 20, color: _Brand.purple),
              const SizedBox(width: 8),
              Text(
                'AI Central — Intelligence croisée',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: colors.ink),
              ),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: _Brand.purple.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: const Text(
                  'Moteur Cross-Agent Avenqo',
                  style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: _Brand.purple),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),

          // Strategic Insights
          if (insights.isNotEmpty) ...[
            Text('Recommandations & Corrélations Stratégiques :', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: colors.muted)),
            const SizedBox(height: 8),
            for (final ins in insights)
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.arrow_right, size: 18, color: _Brand.blue),
                    const SizedBox(width: 4),
                    Expanded(
                      child: Text(
                        ins,
                        style: TextStyle(fontSize: 13, color: colors.ink, height: 1.4),
                      ),
                    ),
                  ],
                ),
              ),
            const SizedBox(height: 14),
          ],

          // Financial Churn Exposure
          if (exposedInvoices.isNotEmpty)
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: _Brand.rose.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: _Brand.rose.withValues(alpha: 0.2)),
              ),
              child: Row(
                children: [
                  const Icon(Icons.shield_outlined, size: 22, color: _Brand.rose),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'Exposition Financière & Risque Churn Croisé',
                          style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: _Brand.rose),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          '${exposedInvoices.length} facture(s) en retard concernent des clients identifiés comme à haut risque de désabonnement (${_formatMoney(context, totalExposed, 'CAD')} exposés).',
                          style: TextStyle(fontSize: 12, color: colors.ink),
                        ),
                      ],
                    ),
                  ),
                  TextButton.icon(
                    onPressed: () => context.go('/assistant'),
                    icon: const Icon(Icons.psychology_outlined, size: 16),
                    label: const Text('Analyser avec l’IA'),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildPillarCard(
    BuildContext context, {
    required String title,
    required IconData icon,
    required Color color,
    required String route,
    required List<_StatItem> stats,
    bool isDemo = false,
  }) {
    final colors = AvenqoColors.of(context);
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: colors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(8)),
                child: Icon(icon, size: 20, color: color),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: colors.ink)),
                    if (isDemo)
                      const Text(
                        'DONNÉES DE DÉMONSTRATION',
                        style: TextStyle(fontSize: 9, fontWeight: FontWeight.w800, color: _Brand.amber, letterSpacing: 0.4),
                      ),
                  ],
                ),
              ),
              IconButton(
                onPressed: () => context.go(route),
                tooltip: 'Ouvrir $title',
                icon: const Icon(Icons.arrow_forward_ios, size: 14),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Divider(height: 1, color: colors.line),
          const SizedBox(height: 14),
          for (final s in stats)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(s.label, style: TextStyle(color: colors.muted, fontSize: 13)),
                  Text(
                    s.value,
                    style: TextStyle(
                      color: s.isAlert ? _Brand.rose : colors.ink,
                      fontWeight: FontWeight.bold,
                      fontSize: 13,
                    ),
                  ),
                ],
              ),
            ),
          const SizedBox(height: 8),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton(
              onPressed: () => context.go(route),
              child: Text('Accéder à $title'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildConnectionsCard(BuildContext context, AvenqoColors colors, List<Map<String, dynamic>> connections) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: colors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  const Icon(Icons.sync_alt, size: 18, color: _Brand.blue),
                  const SizedBox(width: 8),
                  Text('Connexions actives', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: colors.ink)),
                ],
              ),
              TextButton(onPressed: () => context.go('/connections'), child: const Text('Gérer')),
            ],
          ),
          const SizedBox(height: 12),
          if (connections.isEmpty)
            Text('Aucune connexion externe enregistrée.', style: TextStyle(color: colors.muted, fontSize: 13))
          else
            for (final c in connections)
              Container(
                margin: const EdgeInsets.only(bottom: 8),
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: colors.canvas,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: colors.line),
                ),
                child: Row(
                  children: [
                    Icon(
                      c['provider'] == 'shopify' ? Icons.shopping_bag_outlined : Icons.store_outlined,
                      size: 20,
                      color: _Brand.blue,
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            c['display_name'] ?? c['external_account_id'] ?? c['provider'] ?? 'Boutique',
                            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: colors.ink),
                          ),
                          Text(
                            'Fournisseur : ${c['provider']} • Statut : ${c['status']}',
                            style: TextStyle(fontSize: 11, color: colors.muted),
                          ),
                        ],
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: (c['status'] == 'READY' ? _Brand.emerald : _Brand.amber).withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(
                        c['status'] ?? 'UNKNOWN',
                        style: TextStyle(
                          color: c['status'] == 'READY' ? _Brand.emerald : _Brand.amber,
                          fontSize: 10,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
        ],
      ),
    );
  }

  Widget _buildActivityCard(BuildContext context, AvenqoColors colors, List<dynamic> activity) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: colors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.history_outlined, size: 18, color: _Brand.blue),
              const SizedBox(width: 8),
              Text('Activité récente', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: colors.ink)),
            ],
          ),
          const SizedBox(height: 12),
          if (activity.isEmpty)
            Text('Aucune activité récente enregistrée.', style: TextStyle(color: colors.muted, fontSize: 13))
          else
            for (final act in activity.take(4))
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Row(
                  children: [
                    const Icon(Icons.check_circle_outline, size: 14, color: _Brand.emerald),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        (act is Map ? (act['title'] ?? act['kind'] ?? 'Événement système') : act.toString()),
                        style: TextStyle(fontSize: 12, color: colors.ink),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
              ),
        ],
      ),
    );
  }
}

class _StatItem {
  const _StatItem(this.label, this.value, {this.isAlert = false});
  final String label;
  final String value;
  final bool isAlert;
}

String _formatMoney(BuildContext context, num value, [String currency = 'CAD']) {
  final locale = AvenqoLocaleScope.of(context).code;
  return formatMoney(value, locale: locale, currencyCode: currency);
}

