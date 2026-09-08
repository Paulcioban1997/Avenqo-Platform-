import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/agents/retail_source_controller.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/money_formatter.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/widgets/avenqo_data_table.dart';

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
  String _period = 'year_to_date';
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
        message: activeShopifyEmptyMessage(context, RetailEmptyKind.sales) ?? t.analyticsUnavailable,
        action: readOnly ? null : t.businessConnectButton,
        onPressed: readOnly ? null : () => context.go('/connections'),
      );
    }
    final summary = data['summary'] as Map<String, dynamic>?;
    final trend = data['trend'] as Map<String, dynamic>? ?? const {};
    if (summary == null) {
      return _StatePanel(
        icon: Icons.query_stats,
        message: t.analyticsUnavailable,
        action: readOnly ? null : t.businessConnectButton,
        onPressed: readOnly ? null : () => context.go('/connections'),
      );
    }
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
        if (points.isNotEmpty)
          ExpansionTile(
            title: Text(t.salesTrendTitle),
            leading: const Icon(Icons.table_chart_outlined),
            children: [
              AvenqoDataTable(
                semanticLabel: t.salesTrendTitle,
                minWidth: 760,
                maxHeight: 360,
                  columns: [
                    DataColumn(label: Text(t.salesTrendTitle)),
                    DataColumn(label: Text(revenueLabel), numeric: true),
                    DataColumn(label: Text(ordersLabel), numeric: true),
                    const DataColumn(label: Text('%'), numeric: true),
                  ],
                  rows: [
                    for (final point in points)
                      DataRow(cells: [
                        DataCell(Text('${point['period']}')),
                        DataCell(Text(money(point['revenue']))),
                        DataCell(Text('${point['orders'] ?? '—'}')),
                        DataCell(Text(
                          point['change_percent'] is num
                              ? '${(point['change_percent'] as num) > 0 ? '+' : ''}${(point['change_percent'] as num).toStringAsFixed(1)}%'
                              : '—',
                          style: TextStyle(color: point['change_percent'] is num
                              ? (point['change_percent'] as num) < 0
                                  ? Theme.of(context).colorScheme.error
                                  : (point['change_percent'] as num) > 0
                                      ? const Color(0xFF1B9E5A)
                                      : AvenqoColors.of(context).muted
                              : AvenqoColors.of(context).muted),
                        )),
                      ]),
                  ],
              ),
            ],
          ),
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
              style: TextStyle(color: change < 0
                  ? Theme.of(context).colorScheme.error
                  : change > 0 ? const Color(0xFF1B9E5A) : colors.muted),
            ),
        ],
      ),
    );
  }
}

class _TrendPanel extends StatefulWidget {
  const _TrendPanel({required this.points, required this.currency});
  final List<Map<String, dynamic>> points;
  final String currency;

  @override
  State<_TrendPanel> createState() => _TrendPanelState();
}

class _TrendPanelState extends State<_TrendPanel> {
  int? _selectedIndex;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final t = AvenqoLocaleScope.translationsOf(context).company;
    final locale = Localizations.localeOf(context).toLanguageTag();
    String money(dynamic value) =>
      formatMoney(value as num, locale: locale, currencyCode: widget.currency);
    final maxValue = widget.points.fold<double>(
      0,
      (value, point) => (point['revenue'] as num).abs().toDouble() > value
          ? (point['revenue'] as num).abs().toDouble()
          : value,
    );
    final selected = _selectedIndex != null &&
            _selectedIndex! < widget.points.length
        ? widget.points[_selectedIndex!]
        : null;
    return Container(
      height: 300,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border.all(color: colors.line),
        borderRadius: BorderRadius.circular(8),
      ),
      child: widget.points.isEmpty
          ? Center(
              child: Text(
                t.connectionsCleaning['previewEmpty'] ??
                  'No preview is available yet.',
                style: TextStyle(color: colors.muted),
              ),
            )
          : Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(
                  height: 38,
                  child: selected == null
                      ? Text(
                              t.connectionsCleaning['summary'] ?? 'Select a period',
                          style: TextStyle(color: colors.muted),
                        )
                      : Text(
                          '${selected['period']} · ${money(selected['revenue'])}',
                          style: TextStyle(
                            color: colors.ink,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                ),
                Expanded(
                  child: SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: SizedBox(
                      width: (widget.points.length * 64.0).clamp(320.0, 5200.0),
                      child: GestureDetector(
                        onTapUp: (details) {
                          final index = (details.localPosition.dx / 64.0)
                              .floor()
                              .clamp(0, widget.points.length - 1);
                          setState(() => _selectedIndex = index);
                        },
                        child: CustomPaint(
                          painter: _TrendPainter(
                            points: widget.points,
                            maxValue: maxValue,
                            selectedIndex: _selectedIndex,
                            lineColor: const Color(0xFF087CF0),
                            gridColor: colors.line,
                            labelColor: colors.muted,
                            pointFillColor: colors.surface,
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
    );
  }
}

class _TrendPainter extends CustomPainter {
  const _TrendPainter({
    required this.points,
    required this.maxValue,
    required this.selectedIndex,
    required this.lineColor,
    required this.gridColor,
    required this.labelColor,
    required this.pointFillColor,
  });

  final List<Map<String, dynamic>> points;
  final double maxValue;
  final int? selectedIndex;
  final Color lineColor;
  final Color gridColor;
  final Color labelColor;
  final Color pointFillColor;

  @override
  void paint(Canvas canvas, Size size) {
    final chartHeight = size.height - 28;
    final gridPaint = Paint()
      ..color = gridColor
      ..strokeWidth = 1;
    for (final fraction in [0.0, 0.5, 1.0]) {
      final y = chartHeight * (1 - fraction);
      canvas.drawLine(Offset(0, y), Offset(size.width, y), gridPaint);
    }
    final path = Path();
    for (var index = 0; index < points.length; index++) {
      final revenue = (points[index]['revenue'] as num).toDouble();
      final x = index * 64.0 + 32;
      final y = chartHeight -
          (maxValue == 0 ? 0 : revenue / maxValue * (chartHeight - 12));
      if (index == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
      if (index % (points.length > 12 ? 3 : 1) == 0) {
        final text = TextPainter(
          text: TextSpan(
            text: points[index]['period'].toString(),
            style: TextStyle(fontSize: 10, color: labelColor),
          ),
          textDirection: TextDirection.ltr,
        )..layout(maxWidth: 58);
        text.paint(canvas, Offset(x - text.width / 2, chartHeight + 8));
      }
    }
    canvas.drawPath(
      path,
      Paint()
        ..color = lineColor
        ..style = PaintingStyle.stroke
        ..strokeWidth = 3
        ..strokeCap = StrokeCap.round,
    );
    for (var index = 0; index < points.length; index++) {
      final revenue = (points[index]['revenue'] as num).toDouble();
      final x = index * 64.0 + 32;
      final y = chartHeight -
          (maxValue == 0 ? 0 : revenue / maxValue * (chartHeight - 12));
      canvas.drawCircle(
        Offset(x, y),
        selectedIndex == index ? 7 : 4,
        Paint()..color = selectedIndex == index ? lineColor : pointFillColor,
      );
      canvas.drawCircle(
        Offset(x, y),
        selectedIndex == index ? 7 : 4,
        Paint()
          ..color = lineColor
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _TrendPainter oldDelegate) =>
      oldDelegate.points != points || oldDelegate.selectedIndex != selectedIndex;
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
