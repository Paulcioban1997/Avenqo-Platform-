import 'package:flutter/material.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/money_formatter.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/widgets/avenqo_data_table.dart';

class _Brand {
  const _Brand._();
  static const blue = Color(0xFF087CF0);
  static const emerald = Color(0xFF10B981);
  static const amber = Color(0xFFF59E0B);
  static const rose = Color(0xFFEF4444);
  static const purple = Color(0xFF8B5CF6);
}

class CrmPage extends StatefulWidget {
  const CrmPage({super.key, required this.api});

  final ApiClient api;

  @override
  State<CrmPage> createState() => _CrmPageState();
}

class _CrmPageState extends State<CrmPage> with SingleTickerProviderStateMixin {
  late final TabController _tabController;
  late Future<_CrmAllData> _future;
  String _leadStatusFilter = 'all';
  String _searchQuery = '';

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 5, vsync: this);
    _reload();
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  void _reload() {
    setState(() {
      _future = _fetchData();
    });
  }

  Future<_CrmAllData> _fetchData() async {
    final results = await Future.wait([
      widget.api.get('/crm/summary').catchError((_) => <String, dynamic>{}),
      widget.api.get('/crm/leads?limit=100').catchError((_) => <dynamic>[]),
      widget.api.get('/crm/opportunities?limit=100').catchError((_) => <dynamic>[]),
      widget.api.get('/crm/contacts/high-risk?limit=50').catchError((_) => <dynamic>[]),
      widget.api.get('/crm/recommendations').catchError((_) => <String, dynamic>{}),
    ]);

    return _CrmAllData(
      summary: (results[0] is Map) ? results[0] as Map<String, dynamic> : {},
      leads: (results[1] is List) ? (results[1] as List).cast<Map<String, dynamic>>() : [],
      opportunities: (results[2] is List) ? (results[2] as List).cast<Map<String, dynamic>>() : [],
      highRiskContacts: (results[3] is List) ? (results[3] as List).cast<Map<String, dynamic>>() : [],
      recommendations: (results[4] is Map) ? results[4] as Map<String, dynamic> : {},
    );
  }

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final locale = AvenqoLocaleScope.of(context).code;

    return Scaffold(
      backgroundColor: colors.canvas,
      body: FutureBuilder<_CrmAllData>(
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
                    'Erreur lors du chargement des données CRM',
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

          final data = snapshot.data ?? _CrmAllData.empty();
          final currency = data.summary['currency']?.toString() ?? 'CAD';

          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _buildHeader(context, colors),
              Material(
                color: colors.surface,
                elevation: 1,
                child: TabBar(
                  controller: _tabController,
                  isScrollable: true,
                  labelColor: _Brand.blue,
                  unselectedLabelColor: colors.muted,
                  indicatorColor: _Brand.blue,
                  tabs: const [
                    Tab(icon: Icon(Icons.dashboard_outlined, size: 18), text: 'Vue d’ensemble'),
                    Tab(icon: Icon(Icons.person_search_outlined, size: 18), text: 'Leads & Scoring IA'),
                    Tab(icon: Icon(Icons.people_outline, size: 18), text: 'Contacts & Risque Churn'),
                    Tab(icon: Icon(Icons.view_kanban_outlined, size: 18), text: 'Opportunités & Pipeline'),
                    Tab(icon: Icon(Icons.auto_awesome, size: 18), text: 'Recommandations IA'),
                  ],
                ),
              ),
              Expanded(
                child: TabBarView(
                  controller: _tabController,
                  children: [
                    _buildOverviewTab(context, colors, data, locale, currency),
                    _buildLeadsTab(context, colors, data, locale, currency),
                    _buildContactsTab(context, colors, data),
                    _buildOpportunitiesTab(context, colors, data, locale, currency),
                    _buildRecommendationsTab(context, colors, data),
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildHeader(BuildContext context, AvenqoColors colors) {
    return Container(
      padding: const EdgeInsets.fromLTRB(24, 20, 24, 16),
      color: colors.surface,
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: _Brand.blue.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(10),
            ),
            child: const Icon(Icons.hub_outlined, color: _Brand.blue, size: 24),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(
                      'CRM AI',
                      style: TextStyle(
                        fontSize: 22,
                        fontWeight: FontWeight.w800,
                        color: colors.ink,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        color: _Brand.emerald.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(999),
                      ),
                      child: const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.check_circle, size: 12, color: _Brand.emerald),
                          SizedBox(width: 4),
                          Text(
                            'Actif & Connecté',
                            style: TextStyle(
                              color: _Brand.emerald,
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  'Scoring prédictif, priorisation commerciale, gestion du churn et opportunités de vente.',
                  style: TextStyle(color: colors.muted, fontSize: 13),
                ),
              ],
            ),
          ),
          IconButton(
            tooltip: 'Rafraîchir les données',
            onPressed: _reload,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
    );
  }

  Widget _buildOverviewTab(
    BuildContext context,
    AvenqoColors colors,
    _CrmAllData data,
    String locale,
    String currency,
  ) {
    final s = data.summary;
    final totalLeads = s['total_leads'] ?? data.leads.length;
    final qualifiedLeads = s['qualified_leads'] ?? 0;
    final conversionRate = (s['conversion_rate'] as num?)?.toDouble() ?? 0.0;
    final pipelineValue = (s['total_pipeline_value'] as num?)?.toDouble() ?? 0.0;
    final weightedValue = (s['weighted_pipeline_value'] as num?)?.toDouble() ?? 0.0;
    final highRisk = s['high_risk_customers'] ?? data.highRiskContacts.length;
    final avgScore = (s['average_lead_score'] as num?)?.toInt() ?? 0;

    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        // KPI Grid
        LayoutBuilder(
          builder: (context, constraints) {
            final count = constraints.maxWidth > 1100
                ? 4
                : constraints.maxWidth > 700
                    ? 2
                    : 1;
            final itemWidth = (constraints.maxWidth - (count - 1) * 16) / count;

            final cards = [
              _buildMetricCard(
                colors: colors,
                title: 'Total Prospects',
                value: '$totalLeads',
                subtitle: '$qualifiedLeads qualifiés',
                icon: Icons.person_add_alt_1_outlined,
                accentColor: _Brand.blue,
              ),
              _buildMetricCard(
                colors: colors,
                title: 'Taux de Conversion',
                value: '${conversionRate.toStringAsFixed(1)} %',
                subtitle: 'Objectif SaaS > 15%',
                icon: Icons.trending_up,
                accentColor: _Brand.emerald,
              ),
              _buildMetricCard(
                colors: colors,
                title: 'Valeur du Pipeline',
                value: formatMoney(pipelineValue, locale: locale, currencyCode: currency),
                subtitle: 'Pondérée : ${formatMoney(weightedValue, locale: locale, currencyCode: currency)}',
                icon: Icons.monetization_on_outlined,
                accentColor: _Brand.purple,
              ),
              _buildMetricCard(
                colors: colors,
                title: 'Score Moyen IA',
                value: '$avgScore / 100',
                subtitle: '$highRisk contacts à risque churn',
                icon: Icons.psychology_outlined,
                accentColor: _Brand.amber,
              ),
            ];

            return Wrap(
              spacing: 16,
              runSpacing: 16,
              children: cards.map((c) => SizedBox(width: itemWidth, child: c)).toList(),
            );
          },
        ),
        const SizedBox(height: 24),

        // AI Recommendations banner
        if (data.recommendations.isNotEmpty) ...[
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  _Brand.blue.withValues(alpha: 0.08),
                  _Brand.purple.withValues(alpha: 0.08),
                ],
              ),
              border: Border.all(color: _Brand.blue.withValues(alpha: 0.3)),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: _Brand.blue,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: const Icon(Icons.auto_awesome, color: Colors.white, size: 20),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Recommandation IA de Suivi Client',
                        style: TextStyle(
                          color: colors.ink,
                          fontWeight: FontWeight.w700,
                          fontSize: 15,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        data.recommendations['summary']?.toString() ??
                            data.recommendations['recommendation']?.toString() ??
                            'L\'IA analyse les signaux faibles pour optimiser votre cycle de vente.',
                        style: TextStyle(color: colors.muted, fontSize: 13, height: 1.5),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
        ],

        // High priority leads preview
        Text(
          'Top Prospects prioritaires à contacter',
          style: TextStyle(color: colors.ink, fontWeight: FontWeight.w700, fontSize: 17),
        ),
        const SizedBox(height: 12),
        if (data.leads.isEmpty)
          _buildEmptyCard(colors, 'Aucun prospect enregistré pour le moment.')
        else
          Column(
            children: data.leads.take(5).map((lead) {
              return _buildLeadItemCard(colors, lead, locale, currency);
            }).toList(),
          ),
      ],
    );
  }

  Widget _buildLeadsTab(
    BuildContext context,
    AvenqoColors colors,
    _CrmAllData data,
    String locale,
    String currency,
  ) {
    final filtered = data.leads.where((l) {
      if (_leadStatusFilter != 'all' && l['status'] != _leadStatusFilter) return false;
      if (_searchQuery.isNotEmpty) {
        final q = _searchQuery.toLowerCase();
        final name = (l['full_name'] ?? '${l['first_name']} ${l['last_name']}').toString().toLowerCase();
        final email = (l['email'] ?? '').toString().toLowerCase();
        final company = (l['company_name'] ?? '').toString().toLowerCase();
        if (!name.contains(q) && !email.contains(q) && !company.contains(q)) return false;
      }
      return true;
    }).toList();

    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Filter Bar
          Wrap(
            spacing: 12,
            runSpacing: 12,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              SizedBox(
                width: 260,
                child: TextField(
                  decoration: InputDecoration(
                    hintText: 'Rechercher nom, email, société...',
                    prefixIcon: const Icon(Icons.search, size: 18),
                    isDense: true,
                    contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8),
                      borderSide: BorderSide(color: colors.line),
                    ),
                  ),
                  onChanged: (val) => setState(() => _searchQuery = val),
                ),
              ),
              _buildFilterChip('all', 'Tous (${data.leads.length})'),
              _buildFilterChip('new', 'Nouveaux'),
              _buildFilterChip('qualified', 'Qualifiés'),
              _buildFilterChip('contacted', 'Contactés'),
              _buildFilterChip('converted', 'Convertis'),
            ],
          ),
          const SizedBox(height: 16),
          Expanded(
            child: filtered.isEmpty
                ? _buildEmptyCard(colors, 'Aucun prospect correspondant aux filtres.')
                : ClipRRect(
                    borderRadius: BorderRadius.circular(8),
                    child: AvenqoDataTable(
                      semanticLabel: 'Tableau des prospects CRM',
                      minWidth: 950,
                      columns: const [
                        DataColumn(label: Text('Prospect / Entreprise')),
                        DataColumn(label: Text('Contact')),
                        DataColumn(label: Text('Statut')),
                        DataColumn(label: Text('Score IA')),
                        DataColumn(label: Text('Probabilité')),
                        DataColumn(label: Text('Valeur estimée')),
                        DataColumn(label: Text('Prochaine étape')),
                      ],
                      rows: filtered.map((lead) {
                        final fullName = lead['full_name'] ?? '${lead['first_name'] ?? ''} ${lead['last_name'] ?? ''}'.trim();
                        final company = lead['company_name'] ?? '—';
                        final email = lead['email'] ?? '—';
                        final phone = lead['phone'] ?? '—';
                        final status = lead['status']?.toString() ?? 'new';
                        final score = (lead['score'] as num?)?.toInt() ?? 50;
                        final prob = ((lead['conversion_probability'] as num?)?.toDouble() ?? 0.2) * 100;
                        final value = (lead['estimated_value'] as num?)?.toDouble() ?? 0.0;
                        final nextStep = lead['next_step']?.toString() ?? '—';

                        return DataRow(
                          cells: [
                            DataCell(Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Text(fullName.isEmpty ? 'Sans nom' : fullName, style: const TextStyle(fontWeight: FontWeight.w600)),
                                Text(company, style: TextStyle(color: colors.muted, fontSize: 11)),
                              ],
                            )),
                            DataCell(Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Text(email, style: const TextStyle(fontSize: 12)),
                                Text(phone, style: TextStyle(color: colors.muted, fontSize: 11)),
                              ],
                            )),
                            DataCell(_buildStatusBadge(status)),
                            DataCell(_buildScoreBadge(score)),
                            DataCell(Text('${prob.toStringAsFixed(0)} %', style: const TextStyle(fontWeight: FontWeight.w600))),
                            DataCell(Text(formatMoney(value, locale: locale, currencyCode: currency), style: const TextStyle(fontWeight: FontWeight.bold))),
                            DataCell(Text(nextStep, maxLines: 1, overflow: TextOverflow.ellipsis)),
                          ],
                        );
                      }).toList(),
                    ),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildFilterChip(String key, String label) {
    final selected = _leadStatusFilter == key;
    return ChoiceChip(
      label: Text(label),
      selected: selected,
      onSelected: (_) => setState(() => _leadStatusFilter = key),
      selectedColor: _Brand.blue.withValues(alpha: 0.15),
      labelStyle: TextStyle(
        color: selected ? _Brand.blue : null,
        fontWeight: selected ? FontWeight.bold : FontWeight.normal,
        fontSize: 12,
      ),
    );
  }

  Widget _buildContactsTab(BuildContext context, AvenqoColors colors, _CrmAllData data) {
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        Row(
          children: [
            const Icon(Icons.warning_amber_rounded, color: _Brand.rose, size: 22),
            const SizedBox(width: 8),
            Text(
              'Clients & Contacts prioritaires avec Détection du Risque d’Attrition (Churn)',
              style: TextStyle(color: colors.ink, fontWeight: FontWeight.bold, fontSize: 16),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Text(
          'L\'algorithme analyse la fréquence d\'achat, les baisses d\'activité et les tickets récents.',
          style: TextStyle(color: colors.muted, fontSize: 13),
        ),
        const SizedBox(height: 20),
        if (data.highRiskContacts.isEmpty)
          _buildEmptyCard(colors, 'Aucun client à risque de churn détecté. Votre fidélisation est optimale.')
        else
          ...data.highRiskContacts.map((c) {
            final name = c['name'] ?? '${c['first_name'] ?? ''} ${c['last_name'] ?? ''}'.trim();
            final email = c['email'] ?? '—';
            final risk = (c['churn_risk']?.toString() ?? 'medium').toLowerCase();
            final factors = (c['churn_factors'] as List<dynamic>?)?.join(', ') ?? 'Diminution récente des commandes';

            Color riskColor = _Brand.amber;
            if (risk == 'high' || risk == 'critical') riskColor = _Brand.rose;
            if (risk == 'low') riskColor = _Brand.emerald;

            return Card(
              margin: const EdgeInsets.only(bottom: 12),
              color: colors.surface,
              elevation: 0,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(10),
                side: BorderSide(color: colors.line),
              ),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  children: [
                    CircleAvatar(
                      backgroundColor: riskColor.withValues(alpha: 0.15),
                      child: Icon(Icons.person, color: riskColor),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Text(name, style: TextStyle(fontWeight: FontWeight.bold, color: colors.ink, fontSize: 15)),
                              const SizedBox(width: 10),
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                decoration: BoxDecoration(
                                  color: riskColor.withValues(alpha: 0.12),
                                  borderRadius: BorderRadius.circular(6),
                                ),
                                child: Text(
                                  'Risque : ${risk.toUpperCase()}',
                                  style: TextStyle(color: riskColor, fontWeight: FontWeight.bold, fontSize: 11),
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 4),
                          Text(email, style: TextStyle(color: colors.muted, fontSize: 12)),
                          const SizedBox(height: 6),
                          Text('Signaux : $factors', style: TextStyle(color: colors.ink, fontSize: 12)),
                        ],
                      ),
                    ),
                    FilledButton.tonal(
                      onPressed: () {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(content: Text('Plan d\'action de rétention déclenché pour $name.')),
                        );
                      },
                      child: const Text('Action de rétention'),
                    ),
                  ],
                ),
              ),
            );
          }),
      ],
    );
  }

  Widget _buildOpportunitiesTab(
    BuildContext context,
    AvenqoColors colors,
    _CrmAllData data,
    String locale,
    String currency,
  ) {
    final stages = ['discovery', 'proposal', 'negotiation', 'closed_won', 'closed_lost'];
    final stageLabels = {
      'discovery': 'Découverte',
      'proposal': 'Proposition',
      'negotiation': 'Négociation',
      'closed_won': 'Gagnée',
      'closed_lost': 'Perdue',
    };

    return Padding(
      padding: const EdgeInsets.all(24),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final columnWidth = (constraints.maxWidth - 4 * 12) / 5;
          final isNarrow = constraints.maxWidth < 900;

          if (isNarrow) {
            return ListView(
              children: stages.map((stage) {
                final opps = data.opportunities.where((o) => (o['stage'] ?? 'discovery') == stage).toList();
                return Card(
                  margin: const EdgeInsets.only(bottom: 16),
                  color: colors.surface,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10),
                    side: BorderSide(color: colors.line),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('${stageLabels[stage]} (${opps.length})', style: const TextStyle(fontWeight: FontWeight.bold)),
                        const SizedBox(height: 8),
                        ...opps.map((o) => _buildOpportunityCard(colors, o, locale, currency)),
                      ],
                    ),
                  ),
                );
              }).toList(),
            );
          }

          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: stages.map((stage) {
              final opps = data.opportunities.where((o) => (o['stage'] ?? 'discovery') == stage).toList();
              final total = opps.fold<double>(0.0, (sum, o) => sum + ((o['amount'] as num?)?.toDouble() ?? 0.0));

              return Container(
                width: columnWidth,
                margin: const EdgeInsets.symmetric(horizontal: 6),
                decoration: BoxDecoration(
                  color: colors.surface,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: colors.line),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        border: Border(bottom: BorderSide(color: colors.line)),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(stageLabels[stage]!, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                decoration: BoxDecoration(
                                  color: colors.canvas,
                                  borderRadius: BorderRadius.circular(999),
                                ),
                                child: Text('${opps.length}', style: TextStyle(fontSize: 11, color: colors.muted, fontWeight: FontWeight.bold)),
                              ),
                            ],
                          ),
                          const SizedBox(height: 4),
                          Text(formatMoney(total, locale: locale, currencyCode: currency), style: TextStyle(color: colors.muted, fontSize: 11, fontWeight: FontWeight.w600)),
                        ],
                      ),
                    ),
                    Expanded(
                      child: ListView(
                        padding: const EdgeInsets.all(8),
                        children: opps.map((o) => _buildOpportunityCard(colors, o, locale, currency)).toList(),
                      ),
                    ),
                  ],
                ),
              );
            }).toList(),
          );
        },
      ),
    );
  }

  Widget _buildOpportunityCard(AvenqoColors colors, Map<String, dynamic> opp, String locale, String currency) {
    final title = opp['title'] ?? 'Opportunité sans titre';
    final company = opp['company_name'] ?? '—';
    final amount = (opp['amount'] as num?)?.toDouble() ?? 0.0;
    final prob = ((opp['probability'] as num?)?.toDouble() ?? 0.2) * 100;

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      elevation: 0,
      color: colors.canvas,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: BorderSide(color: colors.line),
      ),
      child: Padding(
        padding: const EdgeInsets.all(10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: TextStyle(fontWeight: FontWeight.bold, color: colors.ink, fontSize: 12), maxLines: 2),
            const SizedBox(height: 2),
            Text(company, style: TextStyle(color: colors.muted, fontSize: 11)),
            const SizedBox(height: 6),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(formatMoney(amount, locale: locale, currencyCode: currency), style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 12)),
                Text('${prob.toStringAsFixed(0)} %', style: const TextStyle(color: _Brand.blue, fontWeight: FontWeight.bold, fontSize: 11)),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildRecommendationsTab(BuildContext context, AvenqoColors colors, _CrmAllData data) {
    final recs = data.recommendations;
    final list = (recs['actions'] as List<dynamic>? ?? recs['recommendations'] as List<dynamic>? ?? const []);

    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        Row(
          children: [
            const Icon(Icons.auto_awesome, color: _Brand.purple, size: 24),
            const SizedBox(width: 10),
            Text(
              'Recommandations et Prochaines Meilleures Actions IA (Next Best Actions)',
              style: TextStyle(color: colors.ink, fontWeight: FontWeight.w800, fontSize: 17),
            ),
          ],
        ),
        const SizedBox(height: 6),
        Text(
          'Généré par le moteur d\'intelligence croisée Avenqo à partir de l\'historique des ventes et des interactions.',
          style: TextStyle(color: colors.muted, fontSize: 13),
        ),
        const SizedBox(height: 24),
        if (list.isEmpty)
          _buildEmptyCard(colors, 'Toutes les actions prioritaires ont été exécutées. Aucun retard détecté.')
        else
          ...list.map((item) {
            final title = item is Map ? item['title'] ?? item['action'] ?? 'Action recommandée' : item.toString();
            final desc = item is Map ? item['description'] ?? item['rationale'] ?? '' : '';
            final priority = item is Map ? item['priority']?.toString() ?? 'Normale' : 'Normale';

            return Card(
              margin: const EdgeInsets.only(bottom: 12),
              color: colors.surface,
              elevation: 0,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(10),
                side: BorderSide(color: colors.line),
              ),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: _Brand.purple.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Icon(Icons.bolt, color: _Brand.purple, size: 20),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Expanded(child: Text(title, style: TextStyle(fontWeight: FontWeight.bold, color: colors.ink, fontSize: 14))),
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                decoration: BoxDecoration(
                                  color: _Brand.blue.withValues(alpha: 0.1),
                                  borderRadius: BorderRadius.circular(999),
                                ),
                                child: Text('Priorité : $priority', style: const TextStyle(fontSize: 11, color: _Brand.blue, fontWeight: FontWeight.bold)),
                              ),
                            ],
                          ),
                          if (desc.isNotEmpty) ...[
                            const SizedBox(height: 4),
                            Text(desc, style: TextStyle(color: colors.muted, fontSize: 12)),
                          ],
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            );
          }),
      ],
    );
  }

  Widget _buildMetricCard({
    required AvenqoColors colors,
    required String title,
    required String value,
    required String subtitle,
    required IconData icon,
    required Color accentColor,
  }) {
    return Container(
      padding: const EdgeInsets.all(18),
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
              Text(title, style: TextStyle(color: colors.muted, fontSize: 12, fontWeight: FontWeight.w600)),
              Icon(icon, color: accentColor, size: 20),
            ],
          ),
          const SizedBox(height: 10),
          Text(value, style: TextStyle(color: colors.ink, fontSize: 22, fontWeight: FontWeight.w800)),
          const SizedBox(height: 4),
          Text(subtitle, style: TextStyle(color: colors.muted, fontSize: 11)),
        ],
      ),
    );
  }

  Widget _buildLeadItemCard(AvenqoColors colors, Map<String, dynamic> lead, String locale, String currency) {
    final name = lead['full_name'] ?? '${lead['first_name'] ?? ''} ${lead['last_name'] ?? ''}'.trim();
    final company = lead['company_name'] ?? '—';
    final score = (lead['score'] as num?)?.toInt() ?? 50;
    final value = (lead['estimated_value'] as num?)?.toDouble() ?? 0.0;
    final status = lead['status']?.toString() ?? 'new';

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      color: colors.surface,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: BorderSide(color: colors.line),
      ),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: _Brand.blue.withValues(alpha: 0.1),
          child: Text(name.isNotEmpty ? name[0].toUpperCase() : 'L', style: const TextStyle(color: _Brand.blue, fontWeight: FontWeight.bold)),
        ),
        title: Row(
          children: [
            Text(name, style: const TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(width: 8),
            _buildStatusBadge(status),
          ],
        ),
        subtitle: Text(company, style: TextStyle(color: colors.muted, fontSize: 12)),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            _buildScoreBadge(score),
            const SizedBox(width: 14),
            Text(formatMoney(value, locale: locale, currencyCode: currency), style: const TextStyle(fontWeight: FontWeight.bold)),
          ],
        ),
      ),
    );
  }

  Widget _buildStatusBadge(String status) {
    Color c = _Brand.blue;
    String label = status;
    switch (status) {
      case 'new':
        c = _Brand.blue;
        label = 'Nouveau';
        break;
      case 'qualified':
        c = _Brand.purple;
        label = 'Qualifié';
        break;
      case 'contacted':
        c = _Brand.amber;
        label = 'Contacté';
        break;
      case 'converted':
        c = _Brand.emerald;
        label = 'Converti';
        break;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: c.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(label, style: TextStyle(color: c, fontSize: 11, fontWeight: FontWeight.bold)),
    );
  }

  Widget _buildScoreBadge(int score) {
    Color c = _Brand.amber;
    if (score >= 70) c = _Brand.emerald;
    if (score < 40) c = _Brand.rose;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: c.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text('Score : $score', style: TextStyle(color: c, fontSize: 11, fontWeight: FontWeight.bold)),
    );
  }

  Widget _buildEmptyCard(AvenqoColors colors, String message) {
    return Container(
      padding: const EdgeInsets.all(32),
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: colors.line),
      ),
      child: Text(message, style: TextStyle(color: colors.muted)),
    );
  }
}

class _CrmAllData {
  const _CrmAllData({
    required this.summary,
    required this.leads,
    required this.opportunities,
    required this.highRiskContacts,
    required this.recommendations,
  });

  factory _CrmAllData.empty() => const _CrmAllData(
        summary: {},
        leads: [],
        opportunities: [],
        highRiskContacts: [],
        recommendations: {},
      );

  final Map<String, dynamic> summary;
  final List<Map<String, dynamic>> leads;
  final List<Map<String, dynamic>> opportunities;
  final List<Map<String, dynamic>> highRiskContacts;
  final Map<String, dynamic> recommendations;
}
