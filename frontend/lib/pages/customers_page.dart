import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/money_formatter.dart';
import 'package:avenqo/i18n/locale_scope.dart';

typedef CustomersLoader =
    Future<Map<String, dynamic>> Function(int page, String search);

class CustomersPage extends StatefulWidget {
  const CustomersPage({
    super.key,
    required this.api,
    this.loader,
    this.readOnly = false,
  });

  final ApiClient api;
  final CustomersLoader? loader;
  final bool readOnly;

  @override
  State<CustomersPage> createState() => _CustomersPageState();
}

class _CustomersPageState extends State<CustomersPage> {
  final _searchController = TextEditingController();
  Timer? _debounce;
  int _page = 1;
  late Future<Map<String, dynamic>> _future = _load();

  Future<Map<String, dynamic>> _load() {
    if (widget.loader case final loader?) {
      return loader(_page, _searchController.text);
    }
    final query = Uri(
      queryParameters: {
        'page': '$_page',
        'page_size': '25',
        if (_searchController.text.isNotEmpty) 'search': _searchController.text,
      },
    ).query;
    return widget.api
        .get('/customers/summary?$query')
        .then((value) => value as Map<String, dynamic>);
  }

  void _reload() {
    final next = _load();
    setState(() {
      _future = next;
    });
  }

  void _search(String _) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 300), () {
      _page = 1;
      _reload();
    });
  }

  void _changePage(int page) {
    _page = page;
    _reload();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = AvenqoLocaleScope.translationsOf(context).company;
    final colors = AvenqoColors.of(context);
    return FutureBuilder<Map<String, dynamic>>(
      future: _future,
      builder: (context, snapshot) => ListView(
        padding: const EdgeInsets.all(24),
        children: [
          Text(
            t.navCustomersLabel,
            style: Theme.of(context).textTheme.headlineMedium,
          ),
          const SizedBox(height: 6),
          Text(
            t.navCustomersDescription,
            style: TextStyle(color: colors.muted),
          ),
          const SizedBox(height: 20),
          TextField(
            controller: _searchController,
            onChanged: _search,
            decoration: InputDecoration(
              prefixIcon: const Icon(Icons.search),
              hintText: t.customersSearch,
              border: const OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 20),
          if (snapshot.connectionState != ConnectionState.done)
            const Center(child: CircularProgressIndicator())
          else if (snapshot.hasError)
            _CustomerState(
              message: t.connectionsGenericError,
              action: t.connectionsRetry,
              onPressed: _reload,
            )
          else
            _CustomersContent(
              data: snapshot.data!,
              onPage: _changePage,
              readOnly: widget.readOnly,
            ),
        ],
      ),
    );
  }
}

class _CustomersContent extends StatelessWidget {
  const _CustomersContent({
    required this.data,
    required this.onPage,
    required this.readOnly,
  });
  final Map<String, dynamic> data;
  final ValueChanged<int> onPage;
  final bool readOnly;

  @override
  Widget build(BuildContext context) {
    final t = AvenqoLocaleScope.translationsOf(context).company;
    if (data['status'] == 'processing') {
      return _CustomerState(message: t.connectionsAnalyzing);
    }
    if (data['available'] != true) {
      return _CustomerState(
        message: t.analyticsUnavailable,
        action: readOnly ? null : t.businessConnectButton,
        onPressed: readOnly ? null : () => context.go('/connections'),
      );
    }
    final summary = data['summary'] as Map<String, dynamic>;
    final items = (data['items'] as List<dynamic>).cast<Map<String, dynamic>>();
    final pagination = data['pagination'] as Map<String, dynamic>;
    final currency = data['currency']?.toString() ?? 'USD';
    final locale = Localizations.localeOf(context).toLanguageTag();
    String value(dynamic amount) => amount == null
        ? '—'
        : formatMoney(amount as num, locale: locale, currencyCode: currency);
    String date(dynamic timestamp) => timestamp == null
        ? '—'
        : DateFormat.yMd(locale).format(DateTime.parse(timestamp.toString()));
    final metrics = [
      (t.customersTotal, '${summary['total_customers']}'),
      (t.customersActive, summary['active_customers']?.toString() ?? '—'),
      (t.customersNew, summary['new_customers']?.toString() ?? '—'),
      (t.customersRepeat, '${summary['repeat_customers']}'),
      (t.customersAverageValue, value(summary['average_customer_value'])),
      (t.customersFrequency, '${summary['purchase_frequency']}'),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            for (final metric in metrics)
              _CustomerMetric(label: metric.$1, value: metric.$2),
          ],
        ),
        if ((data['segments'] as List).isNotEmpty ||
            (data['risks'] as List).isNotEmpty) ...[
          const SizedBox(height: 20),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final segment in data['segments'] as List)
                Chip(
                  label: Text(
                    '${t.customersSegment}: ${segment['label']} (${segment['count']})',
                  ),
                ),
              for (final risk in data['risks'] as List)
                Chip(
                  label: Text(
                    '${t.customersRisk}: ${risk['label']} (${risk['count']})',
                  ),
                ),
            ],
          ),
        ],
        const SizedBox(height: 20),
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: DataTable(
            columns: [
              DataColumn(label: Text(t.navCustomersLabel)),
              DataColumn(label: Text(t.customersOrders)),
              DataColumn(label: Text(t.customersValue)),
              DataColumn(label: Text(t.customersLastPurchase)),
              DataColumn(label: Text(t.customersSegment)),
              DataColumn(label: Text(t.customersRisk)),
            ],
            rows: [
              for (final item in items)
                DataRow(
                  cells: [
                    DataCell(Text('${item['customer_id']}')),
                    DataCell(Text('${item['orders']}')),
                    DataCell(Text(value(item['total_value']))),
                    DataCell(Text(date(item['last_purchase']))),
                    DataCell(Text(item['segment']?.toString() ?? '—')),
                    DataCell(Text(item['risk']?.toString() ?? '—')),
                  ],
                ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            Text('${pagination['page']} / ${pagination['pages']}'),
            IconButton(
              tooltip: t.previousPage,
              onPressed: pagination['page'] > 1
                  ? () => onPage(pagination['page'] - 1)
                  : null,
              icon: const Icon(Icons.chevron_left),
            ),
            IconButton(
              tooltip: t.nextPage,
              onPressed: pagination['page'] < pagination['pages']
                  ? () => onPage(pagination['page'] + 1)
                  : null,
              icon: const Icon(Icons.chevron_right),
            ),
          ],
        ),
      ],
    );
  }
}

class _CustomerMetric extends StatelessWidget {
  const _CustomerMetric({required this.label, required this.value});
  final String label;
  final String value;
  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(
      width: 190,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border.all(color: colors.line),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(color: colors.muted)),
          const SizedBox(height: 6),
          Text(
            value,
            style: TextStyle(
              color: colors.ink,
              fontSize: 20,
              fontWeight: FontWeight.w800,
            ),
          ),
        ],
      ),
    );
  }
}

class _CustomerState extends StatelessWidget {
  const _CustomerState({required this.message, this.action, this.onPressed});
  final String message;
  final String? action;
  final VoidCallback? onPressed;
  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border.all(color: colors.line),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Wrap(
        spacing: 14,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          const Icon(Icons.people_outline, color: Color(0xFF087CF0)),
          Text(message, style: TextStyle(color: colors.ink)),
          if (action != null && onPressed != null)
            FilledButton(onPressed: onPressed, child: Text(action!)),
        ],
      ),
    );
  }
}
