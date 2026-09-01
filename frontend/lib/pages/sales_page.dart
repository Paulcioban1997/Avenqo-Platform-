import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/money_formatter.dart';
import 'package:avenqo/i18n/locale_scope.dart';

typedef SalesLoader = Future<Map<String, dynamic>> Function(String period);

class SalesPage extends StatefulWidget {
  const SalesPage({
    super.key,
    required this.api,
    this.loader,
    this.readOnly = false,
  });

  final ApiClient api;
  final SalesLoader? loader;
  final bool readOnly;

  @override
  State<SalesPage> createState() => _SalesPageState();
}

class _SalesPageState extends State<SalesPage> {
  String _period = 'last_30_days';
  late Future<Map<String, dynamic>> _future = _load();

  Future<Map<String, dynamic>> _load() {
    if (widget.loader case final loader?) return loader(_period);
    return widget.api
        .get('/sales/summary?period=$_period')
        .then((value) => value as Map<String, dynamic>);
  }

  void _reload() {
    final next = _load();
    setState(() {
      _future = next;
    });
  }

  void _changePeriod(String? value) {
    if (value == null || value == _period) return;
    _period = value;
    _reload();
  }

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final t = AvenqoLocaleScope.translationsOf(context).company;
    final dashboardT = AvenqoLocaleScope.translationsOf(context).dashboardHome;
    final periods = {
      'current_month': t.periodCurrentMonth,
      'last_30_days': t.periodLast30Days,
      'last_90_days': t.periodLast90Days,
      'year_to_date': t.periodYearToDate,
    };
    return FutureBuilder<Map<String, dynamic>>(
      future: _future,
      builder: (context, snapshot) => ListView(
        padding: const EdgeInsets.all(24),
        children: [
          Wrap(
            alignment: WrapAlignment.spaceBetween,
            crossAxisAlignment: WrapCrossAlignment.center,
            spacing: 16,
            runSpacing: 12,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    t.navSalesLabel,
                    style: Theme.of(context).textTheme.headlineMedium,
                  ),
                  const SizedBox(height: 6),
                  Text(
                    t.navSalesDescription,
                    style: TextStyle(color: colors.muted),
                  ),
                ],
              ),
              DropdownButton<String>(
                value: _period,
                items: [
                  for (final entry in periods.entries)
                    DropdownMenuItem(
                      value: entry.key,
                      child: Text(entry.value),
                    ),
                ],
                onChanged: snapshot.connectionState == ConnectionState.waiting
                    ? null
                    : _changePeriod,
              ),
            ],
          ),
          const SizedBox(height: 24),
          if (snapshot.connectionState != ConnectionState.done)
            const Center(child: CircularProgressIndicator())
          else if (snapshot.hasError)
            _StatePanel(
              icon: Icons.error_outline,
              message: t.connectionsGenericError,
              action: t.connectionsRetry,
              onPressed: _reload,
            )
          else
            _SalesContent(
              data: snapshot.data!,
              readOnly: widget.readOnly,
              revenueLabel: dashboardT.salesLabel,
              ordersLabel: dashboardT.ordersLabel,
              averageLabel: dashboardT.avgOrderLabel,
            ),
        ],
      ),
    );
  }
}

class _SalesContent extends StatelessWidget {
  const _SalesContent({
    required this.data,
    required this.readOnly,
    required this.revenueLabel,
    required this.ordersLabel,
    required this.averageLabel,
  });

  final Map<String, dynamic> data;
  final bool readOnly;
  final String revenueLabel;
  final String ordersLabel;
  final String averageLabel;

  @override
  Widget build(BuildContext context) {
    final t = AvenqoLocaleScope.translationsOf(context).company;
    final status = data['status']?.toString();
    if (status == 'processing') {
      return _StatePanel(icon: Icons.sync, message: t.connectionsAnalyzing);
    }
    if (data['available'] != true) {
      return _StatePanel(
        icon: Icons.query_stats,
        message: t.analyticsUnavailable,
        action: readOnly ? null : t.businessConnectButton,
        onPressed: readOnly ? null : () => context.go('/connections'),
      );
    }
    final summary = data['summary'] as Map<String, dynamic>;
    final trend = data['trend'] as Map<String, dynamic>;
    final points = (trend['points'] as List<dynamic>)
        .cast<Map<String, dynamic>>();
    final currency = data['currency']?.toString() ?? 'USD';
    final locale = Localizations.localeOf(context).toLanguageTag();
    String money(dynamic value) =>
        formatMoney(value as num, locale: locale, currencyCode: currency);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        GridView.count(
          crossAxisCount: MediaQuery.sizeOf(context).width >= 980 ? 3 : 1,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          childAspectRatio: MediaQuery.sizeOf(context).width >= 980 ? 2.0 : 3.2,
          crossAxisSpacing: 16,
          mainAxisSpacing: 16,
          children: [
            _Metric(
              label: revenueLabel,
              value: money(summary['revenue']),
              change: summary['revenue_change_percent'],
            ),
            _Metric(
              label: ordersLabel,
              value: '${summary['orders']}',
              change: summary['orders_change_percent'],
            ),
            _Metric(
              label: averageLabel,
              value: money(summary['average_order_value']),
            ),
          ],
        ),
        const SizedBox(height: 28),
        Text(t.salesTrendTitle, style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 12),
        _TrendPanel(points: points, currency: currency),
        const SizedBox(height: 20),
        Wrap(
          spacing: 16,
          runSpacing: 16,
          children: [
            if (data['strongest_period']
                case final Map<String, dynamic> strongest)
              _PeriodFact(
                label: t.salesStrongestPeriod,
                point: strongest,
                currency: currency,
              ),
            if (data['weakest_period'] case final Map<String, dynamic> weakest)
              _PeriodFact(
                label: t.salesWeakestPeriod,
                point: weakest,
                currency: currency,
              ),
          ],
        ),
        if (data['forecast'] case final Map<String, dynamic> forecast) ...[
          const SizedBox(height: 28),
          Text(
            t.salesForecastTitle,
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 12),
          _StatePanel(
            icon: Icons.auto_graph,
            message: money(forecast['forecasted_total']),
          ),
        ],
      ],
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({required this.label, required this.value, this.change});
  final String label;
  final String value;
  final dynamic change;

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
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(color: colors.muted)),
          const SizedBox(height: 7),
          Text(
            value,
            style: TextStyle(
              color: colors.ink,
              fontSize: 22,
              fontWeight: FontWeight.w800,
            ),
          ),
          if (change is num)
            Text(
              '${change >= 0 ? '+' : ''}${(change as num).toStringAsFixed(1)}%',
              style: TextStyle(color: colors.muted),
            ),
        ],
      ),
    );
  }
}

class _TrendPanel extends StatelessWidget {
  const _TrendPanel({required this.points, required this.currency});
  final List<Map<String, dynamic>> points;
  final String currency;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final locale = Localizations.localeOf(context).toLanguageTag();
    String money(dynamic value) =>
        formatMoney(value as num, locale: locale, currencyCode: currency);
    final maxValue = points.fold<double>(
      0,
      (value, point) => (point['revenue'] as num).toDouble() > value
          ? (point['revenue'] as num).toDouble()
          : value,
    );
    return Container(
      height: 250,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border.all(color: colors.line),
        borderRadius: BorderRadius.circular(8),
      ),
      child: points.isEmpty
          ? Center(
              child: Text('—', style: TextStyle(color: colors.muted)),
            )
          : Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                for (final point in points)
                  Expanded(
                    child: Tooltip(
                      message: '${point['period']}: ${money(point['revenue'])}',
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 3),
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.end,
                          children: [
                            Expanded(
                              child: Align(
                                alignment: Alignment.bottomCenter,
                                child: FractionallySizedBox(
                                  heightFactor: maxValue == 0
                                      ? 0.02
                                      : (point['revenue'] as num) / maxValue,
                                  child: Container(
                                    decoration: BoxDecoration(
                                      color: const Color(0xFF087CF0),
                                      borderRadius: BorderRadius.circular(3),
                                    ),
                                  ),
                                ),
                              ),
                            ),
                            const SizedBox(height: 8),
                            Text(
                              '${point['period']}',
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: 10,
                                color: colors.muted,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
              ],
            ),
    );
  }
}

class _PeriodFact extends StatelessWidget {
  const _PeriodFact({
    required this.label,
    required this.point,
    required this.currency,
  });
  final String label;
  final Map<String, dynamic> point;
  final String currency;

  @override
  Widget build(BuildContext context) {
    final locale = Localizations.localeOf(context).toLanguageTag();
    return Chip(
      label: Text(
        '$label · ${point['period']} · ${formatMoney(point['revenue'] as num, locale: locale, currencyCode: currency)}',
      ),
    );
  }
}

class _StatePanel extends StatelessWidget {
  const _StatePanel({
    required this.icon,
    required this.message,
    this.action,
    this.onPressed,
  });
  final IconData icon;
  final String message;
  final String? action;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border.all(color: colors.line),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Wrap(
        spacing: 14,
        runSpacing: 12,
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
