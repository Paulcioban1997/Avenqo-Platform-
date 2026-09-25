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
  static const cyan = Color(0xFF06B6D4);
}

class AccountingPage extends StatefulWidget {
  const AccountingPage({super.key, required this.api});

  final ApiClient api;

  @override
  State<AccountingPage> createState() => _AccountingPageState();
}

class _AccountingPageState extends State<AccountingPage> with SingleTickerProviderStateMixin {
  late final TabController _tabController;
  late Future<_AccountingAllData> _future;
  String _invoiceTypeFilter = 'receivable';

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 6, vsync: this);
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

  Future<_AccountingAllData> _fetchData() async {
    final results = await Future.wait([
      widget.api.get('/accounting/overview').catchError((_) => <String, dynamic>{}),
      widget.api.get('/accounting/margins').catchError((_) => <String, dynamic>{}),
      widget.api.get('/accounting/invoices/unpaid?invoice_type=receivable').catchError((_) => <String, dynamic>{}),
      widget.api.get('/accounting/anomalies').catchError((_) => <String, dynamic>{}),
      widget.api.get('/accounting/forecast/cashflow?horizon_days=30').catchError((_) => <String, dynamic>{}),
      widget.api.get('/accounting/transactions?limit=100').catchError((_) => <dynamic>[]),
    ]);

    return _AccountingAllData(
      overview: (results[0] is Map) ? results[0] as Map<String, dynamic> : {},
      margins: (results[1] is Map) ? results[1] as Map<String, dynamic> : {},
      unpaidInvoices: (results[2] is Map) ? results[2] as Map<String, dynamic> : {},
      anomalies: (results[3] is Map) ? results[3] as Map<String, dynamic> : {},
      cashFlowForecast: (results[4] is Map) ? results[4] as Map<String, dynamic> : {},
      transactions: (results[5] is List) ? (results[5] as List).cast<Map<String, dynamic>>() : [],
    );
  }

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final locale = AvenqoLocaleScope.of(context).code;

    return Scaffold(
      backgroundColor: colors.canvas,
      body: FutureBuilder<_AccountingAllData>(
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
                    'Erreur lors du chargement des données comptables',
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

          final data = snapshot.data ?? _AccountingAllData.empty();
          final currency = data.overview['currency']?.toString() ?? 'CAD';

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
                    Tab(icon: Icon(Icons.account_balance_wallet_outlined, size: 18), text: 'Vue financière'),
                    Tab(icon: Icon(Icons.pie_chart_outline, size: 18), text: 'Marges & Rentabilité'),
                    Tab(icon: Icon(Icons.receipt_long_outlined, size: 18), text: 'Factures & Impayés'),
                    Tab(icon: Icon(Icons.warning_amber_rounded, size: 18), text: 'Anomalies de dépenses'),
                    Tab(icon: Icon(Icons.insights, size: 18), text: 'Prévisions Cash-Flow (IA)'),
                    Tab(icon: Icon(Icons.list_alt_outlined, size: 18), text: 'Journal des transactions'),
                  ],
                ),
              ),
              Expanded(
                child: TabBarView(
                  controller: _tabController,
                  children: [
                    _buildOverviewTab(context, colors, data, locale, currency),
                    _buildMarginsTab(context, colors, data, locale, currency),
                    _buildInvoicesTab(context, colors, data, locale, currency),
                    _buildAnomaliesTab(context, colors, data, locale, currency),
                    _buildCashFlowTab(context, colors, data, locale, currency),
                    _buildTransactionsTab(context, colors, data, locale, currency),
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
    final agentStrings = AvenqoLocaleScope.translationsOf(context).agents;
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
            child: const Icon(Icons.account_balance_outlined, color: _Brand.blue, size: 24),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(
                      agentStrings.value('accountingName'),
                      style: TextStyle(
                        fontSize: 22,
                        fontWeight: FontWeight.w800,
                        color: colors.ink,
                      ),
                    ),
                    const SizedBox(width: 12),
                    _buildConfirmedTag(),
                    const SizedBox(width: 8),
                    _buildForecastTag(),
                    const SizedBox(width: 8),
                    _buildDemoTag(),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  'Comptabilité consolidée, marges réelles, détection d\'anomalies et prévisions de trésorerie.',
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

  Widget _buildConfirmedTag() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: _Brand.emerald.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: _Brand.emerald.withValues(alpha: 0.3)),
      ),
      child: const Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.verified, size: 12, color: _Brand.emerald),
          SizedBox(width: 4),
          Text(
            'DONNÉES CONFIRMÉES',
            style: TextStyle(
              color: _Brand.emerald,
              fontSize: 10,
              fontWeight: FontWeight.w800,
              letterSpacing: 0.5,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildForecastTag() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: _Brand.purple.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: _Brand.purple.withValues(alpha: 0.3)),
      ),
      child: const Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.auto_awesome, size: 12, color: _Brand.purple),
          SizedBox(width: 4),
          Text(
            'PRÉVISION IA',
            style: TextStyle(
              color: _Brand.purple,
              fontSize: 10,
              fontWeight: FontWeight.w800,
              letterSpacing: 0.5,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDemoTag() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: _Brand.amber.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: _Brand.amber.withValues(alpha: 0.35)),
      ),
      child: const Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.info_outline, size: 12, color: _Brand.amber),
          SizedBox(width: 4),
          Text(
            'DONNÉES DE DÉMONSTRATION',
            style: TextStyle(
              color: _Brand.amber,
              fontSize: 10,
              fontWeight: FontWeight.w800,
              letterSpacing: 0.5,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildOverviewTab(
    BuildContext context,
    AvenqoColors colors,
    _AccountingAllData data,
    String locale,
    String currency,
  ) {
    final o = data.overview;
    final totalRevenue = (o['total_revenue'] as num?)?.toDouble() ?? 0.0;
    final totalExpenses = (o['total_expenses'] as num?)?.toDouble() ?? 0.0;
    final netIncome = (o['net_income'] as num?)?.toDouble() ?? 0.0;
    final grossMargin = (o['gross_margin_pct'] as num?)?.toDouble() ?? 0.0;
    final operatingMargin = (o['operating_margin_pct'] as num?)?.toDouble() ?? 0.0;
    final unpaidReceivables = (o['unpaid_receivables_total'] as num?)?.toDouble() ?? 0.0;
    final unpaidPayables = (o['unpaid_payables_total'] as num?)?.toDouble() ?? 0.0;
    final txCount = o['confirmed_transactions_count'] ?? data.transactions.length;

    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        // Distinction notice
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: colors.surface,
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: colors.line),
          ),
          child: Row(
            children: [
              const Icon(Icons.info_outline, color: _Brand.blue, size: 20),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  'Distinction comptable : les montants affichés ci-dessous proviennent exclusivement de vos écritures confirmées. Les projections et estimations sont systématiquement étiquetées « Prévision IA ».',
                  style: TextStyle(color: colors.muted, fontSize: 13),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),

        // Financial Metrics Grid
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
                title: 'Chiffre d’Affaires',
                value: formatMoney(totalRevenue, locale: locale, currencyCode: currency),
                subtitle: '$txCount transactions confirmées',
                icon: Icons.trending_up,
                accentColor: _Brand.emerald,
                tag: _buildConfirmedTag(),
              ),
              _buildMetricCard(
                colors: colors,
                title: 'Dépenses Totales',
                value: formatMoney(totalExpenses, locale: locale, currencyCode: currency),
                subtitle: 'Charges et coûts directs confirmés',
                icon: Icons.trending_down,
                accentColor: _Brand.rose,
                tag: _buildConfirmedTag(),
              ),
              _buildMetricCard(
                colors: colors,
                title: 'Résultat Net',
                value: formatMoney(netIncome, locale: locale, currencyCode: currency),
                subtitle: 'Marge opérationnelle : ${operatingMargin.toStringAsFixed(1)} %',
                icon: Icons.account_balance,
                accentColor: netIncome >= 0 ? _Brand.emerald : _Brand.rose,
                tag: _buildConfirmedTag(),
              ),
              _buildMetricCard(
                colors: colors,
                title: 'Créances Clients Impayées',
                value: formatMoney(unpaidReceivables, locale: locale, currencyCode: currency),
                subtitle: 'Dettes fournisseurs : ${formatMoney(unpaidPayables, locale: locale, currencyCode: currency)}',
                icon: Icons.pending_actions,
                accentColor: _Brand.amber,
                tag: _buildConfirmedTag(),
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

        // Margins Card
        Card(
          elevation: 0,
          color: colors.surface,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
            side: BorderSide(color: colors.line),
          ),
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text('Synthèse des Marges Brute et Opérationnelle', style: TextStyle(color: colors.ink, fontWeight: FontWeight.bold, fontSize: 16)),
                    _buildConfirmedTag(),
                  ],
                ),
                const SizedBox(height: 16),
                Row(
                  children: [
                    Expanded(
                      child: _buildMarginBar(
                        colors: colors,
                        label: 'Marge Brute',
                        percentage: grossMargin,
                        color: _Brand.blue,
                      ),
                    ),
                    const SizedBox(width: 24),
                    Expanded(
                      child: _buildMarginBar(
                        colors: colors,
                        label: 'Marge Opérationnelle',
                        percentage: operatingMargin,
                        color: _Brand.emerald,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 24),

        // Recent Confirmed Transactions Preview
        Text('Dernières Écritures Comptables Confirmées', style: TextStyle(color: colors.ink, fontWeight: FontWeight.bold, fontSize: 16)),
        const SizedBox(height: 12),
        if (data.transactions.isEmpty)
          _buildEmptyCard(colors, 'Aucune écriture comptable enregistrée.')
        else
          Column(
            children: data.transactions.take(5).map((tx) {
              return _buildTransactionItemCard(colors, tx, locale, currency);
            }).toList(),
          ),
      ],
    );
  }

  Widget _buildMarginsTab(
    BuildContext context,
    AvenqoColors colors,
    _AccountingAllData data,
    String locale,
    String currency,
  ) {
    final m = data.margins;
    final grossMargin = (m['gross_margin_pct'] as num?)?.toDouble() ?? 0.0;
    final opMargin = (m['operating_margin_pct'] as num?)?.toDouble() ?? 0.0;
    final grossProfit = (m['gross_profit'] as num?)?.toDouble() ?? 0.0;
    final netProfit = (m['net_income'] as num?)?.toDouble() ?? 0.0;

    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Analyse des Marges et Rentabilité Métier', style: TextStyle(color: colors.ink, fontWeight: FontWeight.bold, fontSize: 18)),
                const SizedBox(height: 4),
                Text('Calculé sur la base des ventes réelles et du coût des marchandises (COGS).', style: TextStyle(color: colors.muted, fontSize: 13)),
              ],
            ),
            _buildConfirmedTag(),
          ],
        ),
        const SizedBox(height: 24),

        Row(
          children: [
            Expanded(
              child: _buildMetricCard(
                colors: colors,
                title: 'Bénéfice Brut Réel',
                value: formatMoney(grossProfit, locale: locale, currencyCode: currency),
                subtitle: 'Taux de marge brute : ${grossMargin.toStringAsFixed(1)} %',
                icon: Icons.bar_chart,
                accentColor: _Brand.blue,
                tag: _buildConfirmedTag(),
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: _buildMetricCard(
                colors: colors,
                title: 'Bénéfice Net Réel',
                value: formatMoney(netProfit, locale: locale, currencyCode: currency),
                subtitle: 'Taux de marge opérationnelle : ${opMargin.toStringAsFixed(1)} %',
                icon: Icons.account_balance_wallet,
                accentColor: netProfit >= 0 ? _Brand.emerald : _Brand.rose,
                tag: _buildConfirmedTag(),
              ),
            ),
          ],
        ),
        const SizedBox(height: 24),

        Card(
          elevation: 0,
          color: colors.surface,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
            side: BorderSide(color: colors.line),
          ),
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Indicateurs de Santé Financière', style: TextStyle(color: colors.ink, fontWeight: FontWeight.bold, fontSize: 15)),
                const SizedBox(height: 16),
                _buildHealthRow(
                  colors: colors,
                  title: 'Marge Brute vs Standard Industrie',
                  value: '${grossMargin.toStringAsFixed(1)} %',
                  status: grossMargin >= 40 ? 'Solide' : 'À optimiser',
                  statusColor: grossMargin >= 40 ? _Brand.emerald : _Brand.amber,
                ),
                const Divider(),
                _buildHealthRow(
                  colors: colors,
                  title: 'Rentabilité Opérationnelle',
                  value: '${opMargin.toStringAsFixed(1)} %',
                  status: opMargin > 10 ? 'Rentable' : 'Vigilance trésorerie',
                  statusColor: opMargin > 10 ? _Brand.emerald : _Brand.rose,
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildInvoicesTab(
    BuildContext context,
    AvenqoColors colors,
    _AccountingAllData data,
    String locale,
    String currency,
  ) {
    final invData = data.unpaidInvoices;
    final list = (invData['invoices'] as List<dynamic>? ?? const []).cast<Map<String, dynamic>>();

    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Suivi des Factures et Créances / Dettes Impayées', style: TextStyle(color: colors.ink, fontWeight: FontWeight.bold, fontSize: 18)),
                  const SizedBox(height: 4),
                  Text('Échéancier strict pour protéger la liquidité de votre entreprise.', style: TextStyle(color: colors.muted, fontSize: 13)),
                ],
              ),
              _buildConfirmedTag(),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              ChoiceChip(
                label: const Text('Créances Clients (À recevoir)'),
                selected: _invoiceTypeFilter == 'receivable',
                onSelected: (_) => setState(() => _invoiceTypeFilter = 'receivable'),
                selectedColor: _Brand.blue.withValues(alpha: 0.15),
              ),
              const SizedBox(width: 12),
              ChoiceChip(
                label: const Text('Dettes Fournisseurs (À payer)'),
                selected: _invoiceTypeFilter == 'payable',
                onSelected: (_) => setState(() => _invoiceTypeFilter = 'payable'),
                selectedColor: _Brand.blue.withValues(alpha: 0.15),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Expanded(
            child: list.isEmpty
                ? _buildEmptyCard(colors, 'Aucune facture impayée dans cette catégorie.')
                : ClipRRect(
                    borderRadius: BorderRadius.circular(8),
                    child: AvenqoDataTable(
                      semanticLabel: 'Tableau des factures',
                      minWidth: 850,
                      columns: const [
                        DataColumn(label: Text('N° Facture')),
                        DataColumn(label: Text('Tiers (Client / Fournisseur)')),
                        DataColumn(label: Text('Date d\'échéance')),
                        DataColumn(label: Text('Statut')),
                        DataColumn(label: Text('Montant Total')),
                        DataColumn(label: Text('Reste Dû')),
                        DataColumn(label: Text('Source')),
                      ],
                      rows: list.map((inv) {
                        final invNum = inv['invoice_number']?.toString() ?? '—';
                        final party = inv['party_name']?.toString() ?? '—';
                        final due = inv['due_date']?.toString().split('T').first ?? '—';
                        final status = inv['status']?.toString() ?? 'unpaid';
                        final total = (inv['total_amount'] as num?)?.toDouble() ?? 0.0;
                        final balance = total - ((inv['paid_amount'] as num?)?.toDouble() ?? 0.0);

                        return DataRow(
                          cells: [
                            DataCell(Text(invNum, style: const TextStyle(fontWeight: FontWeight.bold))),
                            DataCell(Text(party)),
                            DataCell(Text(due)),
                            DataCell(_buildInvoiceStatusBadge(status)),
                            DataCell(Text(formatMoney(total, locale: locale, currencyCode: currency))),
                            DataCell(Text(formatMoney(balance, locale: locale, currencyCode: currency), style: const TextStyle(fontWeight: FontWeight.bold, color: _Brand.rose))),
                            DataCell(_buildConfirmedTag()),
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

  Widget _buildAnomaliesTab(
    BuildContext context,
    AvenqoColors colors,
    _AccountingAllData data,
    String locale,
    String currency,
  ) {
    final ano = data.anomalies;
    final list = (ano['anomalies'] as List<dynamic>? ?? const []).cast<Map<String, dynamic>>();

    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Détection d\'Anomalies et Dépenses Suspectes', style: TextStyle(color: colors.ink, fontWeight: FontWeight.bold, fontSize: 18)),
                const SizedBox(height: 4),
                Text('L\'IA détecte automatiquement les écarts statistiques, doublons et montants anormaux.', style: TextStyle(color: colors.muted, fontSize: 13)),
              ],
            ),
            _buildForecastTag(),
          ],
        ),
        const SizedBox(height: 20),
        if (list.isEmpty)
          _buildEmptyCard(colors, 'Aucune anomalie de dépense détectée. Tous les flux sont conformes.')
        else
          ...list.map((item) {
            final desc = item['description']?.toString() ?? item['category']?.toString() ?? 'Dépense inhabituelle';
            final amount = (item['amount'] as num?)?.toDouble() ?? 0.0;
            final reason = item['reason']?.toString() ?? 'Montant supérieur à 2x la moyenne de la catégorie';

            return Card(
              margin: const EdgeInsets.only(bottom: 12),
              color: colors.surface,
              elevation: 0,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(10),
                side: BorderSide(color: _Brand.rose.withValues(alpha: 0.3)),
              ),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: _Brand.rose.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Icon(Icons.warning_amber_rounded, color: _Brand.rose, size: 22),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(desc, style: TextStyle(color: colors.ink, fontWeight: FontWeight.bold, fontSize: 14)),
                              Text(formatMoney(amount, locale: locale, currencyCode: currency), style: const TextStyle(fontWeight: FontWeight.bold, color: _Brand.rose, fontSize: 15)),
                            ],
                          ),
                          const SizedBox(height: 4),
                          Text('Motif : $reason', style: TextStyle(color: colors.muted, fontSize: 12)),
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

  Widget _buildCashFlowTab(
    BuildContext context,
    AvenqoColors colors,
    _AccountingAllData data,
    String locale,
    String currency,
  ) {
    final fc = data.cashFlowForecast;
    final horizon = fc['forecast_days'] ?? 30;
    final netCash = (fc['net_projected_cash_flow'] as num?)?.toDouble() ?? 0.0;
    final avgDailyRev = (fc['historical_daily_avg_revenue'] as num?)?.toDouble() ?? 0.0;
    final avgDailyExp = (fc['historical_daily_avg_expenses'] as num?)?.toDouble() ?? 0.0;
    final projections = (fc['daily_projections'] as List<dynamic>? ?? const []).cast<Map<String, dynamic>>();

    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        // AI Projection Warning Banner
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [
                _Brand.purple.withValues(alpha: 0.12),
                _Brand.cyan.withValues(alpha: 0.12),
              ],
            ),
            border: Border.all(color: _Brand.purple.withValues(alpha: 0.4)),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(Icons.auto_awesome, color: _Brand.purple, size: 22),
                  const SizedBox(width: 10),
                  Text(
                    'PRÉVISION IA — PROJECTION DE TRÉSORERIE ($horizon JOURS)',
                    style: const TextStyle(
                      color: _Brand.purple,
                      fontWeight: FontWeight.w800,
                      fontSize: 14,
                      letterSpacing: 0.6,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                'IMPORTANT : Les valeurs ci-dessous sont des estimations prédictives calculées par intelligence artificielle basées sur les tendances des encaissements et décaissements historiques. Elles ne constituent pas des écritures comptables confirmées.',
                style: TextStyle(color: colors.ink, fontSize: 13, height: 1.5),
              ),
            ],
          ),
        ),
        const SizedBox(height: 24),

        // Forecast summary cards
        Row(
          children: [
            Expanded(
              child: _buildMetricCard(
                colors: colors,
                title: 'Flux Net Estimé IA (30j)',
                value: formatMoney(netCash, locale: locale, currencyCode: currency),
                subtitle: 'Solde projeté en fin de période',
                icon: Icons.waterfall_chart,
                accentColor: _Brand.purple,
                tag: _buildForecastTag(),
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: _buildMetricCard(
                colors: colors,
                title: 'Revenu Quotidien Estimé',
                value: formatMoney(avgDailyRev, locale: locale, currencyCode: currency),
                subtitle: 'Dépenses quotidiennes est. : ${formatMoney(avgDailyExp, locale: locale, currencyCode: currency)}',
                icon: Icons.show_chart,
                accentColor: _Brand.cyan,
                tag: _buildForecastTag(),
              ),
            ),
          ],
        ),
        const SizedBox(height: 24),

        // Projections list
        Text('Projections Quotidiennes Estimées (30 jours)', style: TextStyle(color: colors.ink, fontWeight: FontWeight.bold, fontSize: 16)),
        const SizedBox(height: 12),
        if (projections.isEmpty)
          _buildEmptyCard(colors, 'Données historiques insuffisantes pour générer les projections prédictives.')
        else
          ...projections.take(15).map((p) {
            final date = p['date']?.toString().split('T').first ?? '—';
            final flow = (p['projected_net_flow'] as num?)?.toDouble() ?? 0.0;
            final cumulative = (p['cumulative_cash'] as num?)?.toDouble() ?? 0.0;

            return Card(
              margin: const EdgeInsets.only(bottom: 8),
              color: colors.surface,
              elevation: 0,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(8),
                side: BorderSide(color: colors.line),
              ),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Row(
                      children: [
                        const Icon(Icons.calendar_today, size: 14, color: _Brand.purple),
                        const SizedBox(width: 8),
                        Text(date, style: const TextStyle(fontWeight: FontWeight.w600)),
                        const SizedBox(width: 12),
                        _buildForecastTag(),
                      ],
                    ),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text(
                          'Flux net : ${formatMoney(flow, locale: locale, currencyCode: currency)}',
                          style: TextStyle(
                            fontWeight: FontWeight.bold,
                            color: flow >= 0 ? _Brand.emerald : _Brand.rose,
                          ),
                        ),
                        Text(
                          'Cumul projeté : ${formatMoney(cumulative, locale: locale, currencyCode: currency)}',
                          style: TextStyle(color: colors.muted, fontSize: 11),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            );
          }),
      ],
    );
  }

  Widget _buildTransactionsTab(
    BuildContext context,
    AvenqoColors colors,
    _AccountingAllData data,
    String locale,
    String currency,
  ) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Grand Livre & Journal des Écritures Confirmées', style: TextStyle(color: colors.ink, fontWeight: FontWeight.bold, fontSize: 18)),
                  const SizedBox(height: 4),
                  Text('Historique auditable de toutes les transactions financières réelles.', style: TextStyle(color: colors.muted, fontSize: 13)),
                ],
              ),
              _buildConfirmedTag(),
            ],
          ),
          const SizedBox(height: 16),
          Expanded(
            child: data.transactions.isEmpty
                ? _buildEmptyCard(colors, 'Aucune transaction confirmée dans le grand livre.')
                : ClipRRect(
                    borderRadius: BorderRadius.circular(8),
                    child: AvenqoDataTable(
                      semanticLabel: 'Tableau des écritures comptables',
                      minWidth: 900,
                      columns: const [
                        DataColumn(label: Text('Date')),
                        DataColumn(label: Text('Type')),
                        DataColumn(label: Text('Catégorie')),
                        DataColumn(label: Text('Description')),
                        DataColumn(label: Text('Montant')),
                        DataColumn(label: Text('Statut')),
                      ],
                      rows: data.transactions.map((tx) {
                        final date = tx['date']?.toString().split('T').first ?? '—';
                        final type = tx['transaction_type']?.toString() ?? 'expense';
                        final cat = tx['category']?.toString() ?? 'general';
                        final desc = tx['description']?.toString() ?? '—';
                        final amount = (tx['amount'] as num?)?.toDouble() ?? 0.0;
                        final isRev = type == 'revenue';

                        return DataRow(
                          cells: [
                            DataCell(Text(date)),
                            DataCell(Container(
                              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                              decoration: BoxDecoration(
                                color: (isRev ? _Brand.emerald : _Brand.rose).withValues(alpha: 0.12),
                                borderRadius: BorderRadius.circular(4),
                              ),
                              child: Text(
                                isRev ? 'Recette' : 'Dépense',
                                style: TextStyle(color: isRev ? _Brand.emerald : _Brand.rose, fontWeight: FontWeight.bold, fontSize: 11),
                              ),
                            )),
                            DataCell(Text(cat)),
                            DataCell(Text(desc, maxLines: 1, overflow: TextOverflow.ellipsis)),
                            DataCell(Text(
                              formatMoney(amount, locale: locale, currencyCode: currency),
                              style: TextStyle(fontWeight: FontWeight.bold, color: isRev ? _Brand.emerald : colors.ink),
                            )),
                            DataCell(_buildConfirmedTag()),
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

  Widget _buildMetricCard({
    required AvenqoColors colors,
    required String title,
    required String value,
    required String subtitle,
    required IconData icon,
    required Color accentColor,
    required Widget tag,
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
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(child: Text(subtitle, style: TextStyle(color: colors.muted, fontSize: 11), maxLines: 1, overflow: TextOverflow.ellipsis)),
              tag,
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildMarginBar({
    required AvenqoColors colors,
    required String label,
    required double percentage,
    required Color color,
  }) {
    final clamped = (percentage / 100).clamp(0.0, 1.0);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label, style: const TextStyle(fontWeight: FontWeight.w600)),
            Text('${percentage.toStringAsFixed(1)} %', style: TextStyle(fontWeight: FontWeight.bold, color: color)),
          ],
        ),
        const SizedBox(height: 8),
        ClipRRect(
          borderRadius: BorderRadius.circular(6),
          child: LinearProgressIndicator(
            value: clamped,
            minHeight: 10,
            backgroundColor: colors.canvas,
            valueColor: AlwaysStoppedAnimation<Color>(color),
          ),
        ),
      ],
    );
  }

  Widget _buildHealthRow({
    required AvenqoColors colors,
    required String title,
    required String value,
    required String status,
    required Color statusColor,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(title, style: TextStyle(color: colors.ink, fontSize: 13)),
          Row(
            children: [
              Text(value, style: const TextStyle(fontWeight: FontWeight.bold)),
              const SizedBox(width: 12),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: statusColor.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(status, style: TextStyle(color: statusColor, fontWeight: FontWeight.bold, fontSize: 11)),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildTransactionItemCard(AvenqoColors colors, Map<String, dynamic> tx, String locale, String currency) {
    final desc = tx['description']?.toString() ?? 'Écriture comptable';
    final amount = (tx['amount'] as num?)?.toDouble() ?? 0.0;
    final isRev = tx['transaction_type'] == 'revenue';
    final date = tx['date']?.toString().split('T').first ?? '—';

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
          backgroundColor: (isRev ? _Brand.emerald : _Brand.rose).withValues(alpha: 0.1),
          child: Icon(isRev ? Icons.arrow_downward : Icons.arrow_upward, color: isRev ? _Brand.emerald : _Brand.rose, size: 18),
        ),
        title: Text(desc, style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: Text(date, style: TextStyle(color: colors.muted, fontSize: 12)),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              formatMoney(amount, locale: locale, currencyCode: currency),
              style: TextStyle(fontWeight: FontWeight.bold, color: isRev ? _Brand.emerald : colors.ink),
            ),
            const SizedBox(width: 8),
            _buildConfirmedTag(),
          ],
        ),
      ),
    );
  }

  Widget _buildInvoiceStatusBadge(String status) {
    Color c = _Brand.amber;
    String label = 'En attente';
    if (status == 'overdue') {
      c = _Brand.rose;
      label = 'En retard';
    } else if (status == 'paid') {
      c = _Brand.emerald;
      label = 'Payée';
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: c.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(label, style: TextStyle(color: c, fontSize: 11, fontWeight: FontWeight.bold)),
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

class _AccountingAllData {
  const _AccountingAllData({
    required this.overview,
    required this.margins,
    required this.unpaidInvoices,
    required this.anomalies,
    required this.cashFlowForecast,
    required this.transactions,
  });

  factory _AccountingAllData.empty() => const _AccountingAllData(
        overview: {},
        margins: {},
        unpaidInvoices: {},
        anomalies: {},
        cashFlowForecast: {},
        transactions: [],
      );

  final Map<String, dynamic> overview;
  final Map<String, dynamic> margins;
  final Map<String, dynamic> unpaidInvoices;
  final Map<String, dynamic> anomalies;
  final Map<String, dynamic> cashFlowForecast;
  final List<Map<String, dynamic>> transactions;
}
