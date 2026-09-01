import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/money_formatter.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/i18n/translations.dart';

typedef ProductsLoader = Future<Map<String, dynamic>> Function(
  int page,
  String search,
  String? category,
  String? performance,
  String sortBy,
);
typedef ProductDetailLoader = Future<Map<String, dynamic>> Function(String id);

class ProductsPage extends StatefulWidget {
  const ProductsPage({super.key, required this.api, this.loader, this.detailLoader});

  final ApiClient api;
  final ProductsLoader? loader;
  final ProductDetailLoader? detailLoader;

  @override
  State<ProductsPage> createState() => _ProductsPageState();
}

class _ProductsPageState extends State<ProductsPage> {
  final _search = TextEditingController();
  Timer? _debounce;
  int _page = 1;
  String? _category;
  String? _performance;
  String _sortBy = 'revenue';
  late Future<Map<String, dynamic>> _future = _load();

  Future<Map<String, dynamic>> _load() {
    if (widget.loader case final loader?) {
      return loader(_page, _search.text, _category, _performance, _sortBy);
    }
    final query = Uri(queryParameters: {
      'page': '$_page',
      'page_size': '25',
      'sort_by': _sortBy,
      'sort_direction': 'desc',
      if (_search.text.isNotEmpty) 'search': _search.text,
      'category': ?_category,
      'performance': ?_performance,
    }).query;
    return widget.api
        .get('/products/summary?$query')
        .then((value) => value as Map<String, dynamic>);
  }

  void _reload({bool resetPage = false}) {
    if (resetPage) _page = 1;
    final next = _load();
    setState(() {
      _future = next;
    });
  }

  void _onSearch(String _) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 300), () => _reload(resetPage: true));
  }

  Future<void> _showDetail(String id) async {
    Future<Map<String, dynamic>> request() {
      if (widget.detailLoader case final loader?) return loader(id);
      return widget.api
          .get('/products/${Uri.encodeComponent(id)}')
          .then((value) => value as Map<String, dynamic>);
    }
    await showDialog<void>(
      context: context,
      builder: (context) => _ProductDetailDialog(future: request()),
    );
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final company = AvenqoLocaleScope.translationsOf(context).company;
    final strings = AvenqoLocaleScope.translationsOf(context).phase4d;
    final colors = AvenqoColors.of(context);
    return FutureBuilder<Map<String, dynamic>>(
      future: _future,
      builder: (context, snapshot) => ListView(
        padding: const EdgeInsets.all(24),
        children: [
          Text(company.navProductsLabel, style: Theme.of(context).textTheme.headlineMedium),
          const SizedBox(height: 6),
          Text(company.navProductsDescription, style: TextStyle(color: colors.muted)),
          const SizedBox(height: 20),
          TextField(
            controller: _search,
            onChanged: _onSearch,
            decoration: InputDecoration(
              prefixIcon: const Icon(Icons.search),
              hintText: strings.productsSearch,
              border: const OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 16),
          if (snapshot.connectionState != ConnectionState.done)
            const Center(child: CircularProgressIndicator())
          else if (snapshot.hasError)
            _ProductState(
              message: company.connectionsGenericError,
              action: company.connectionsRetry,
              onPressed: _reload,
            )
          else
            _ProductsContent(
              data: snapshot.data!,
              category: _category,
              performance: _performance,
              sortBy: _sortBy,
              onCategory: (value) {
                _category = value;
                _reload(resetPage: true);
              },
              onPerformance: (value) {
                _performance = value;
                _reload(resetPage: true);
              },
              onSort: (value) {
                _sortBy = value;
                _reload(resetPage: true);
              },
              onPage: (value) {
                _page = value;
                _reload();
              },
              onProduct: _showDetail,
            ),
        ],
      ),
    );
  }
}

class _ProductsContent extends StatelessWidget {
  const _ProductsContent({
    required this.data,
    required this.category,
    required this.performance,
    required this.sortBy,
    required this.onCategory,
    required this.onPerformance,
    required this.onSort,
    required this.onPage,
    required this.onProduct,
  });

  final Map<String, dynamic> data;
  final String? category;
  final String? performance;
  final String sortBy;
  final ValueChanged<String?> onCategory;
  final ValueChanged<String?> onPerformance;
  final ValueChanged<String> onSort;
  final ValueChanged<int> onPage;
  final ValueChanged<String> onProduct;

  @override
  Widget build(BuildContext context) {
    final company = AvenqoLocaleScope.translationsOf(context).company;
    final strings = AvenqoLocaleScope.translationsOf(context).phase4d;
    if (data['status'] == 'processing') {
      return _ProductState(message: company.connectionsAnalyzing);
    }
    if (data['available'] != true) {
      return _ProductState(
        message: company.analyticsUnavailable,
        action: company.businessConnectButton,
        onPressed: () => context.go('/connections'),
      );
    }
    final summary = data['summary'] as Map<String, dynamic>;
    final items = (data['items'] as List<dynamic>).cast<Map<String, dynamic>>();
    final categories = (data['categories'] as List<dynamic>).cast<Map<String, dynamic>>();
    final pagination = data['pagination'] as Map<String, dynamic>;
    final currency = data['currency']?.toString() ?? 'USD';
    final locale = Localizations.localeOf(context).toLanguageTag();
    String money(dynamic value) => value == null
        ? '—'
        : formatMoney(value as num, locale: locale, currencyCode: currency);
    String number(dynamic value) => value == null ? '—' : NumberFormat.decimalPattern(locale).format(value);
    final metrics = <(String, String)>[
      (strings.productsTotal, '${summary['total_products']}'),
      if (summary['active_products'] != null) (strings.productsActive, '${summary['active_products']}'),
      if (summary['revenue'] != null) (strings.productsRevenue, money(summary['revenue'])),
      if (summary['units'] != null) (strings.productsUnits, number(summary['units'])),
      if (summary['average_selling_price'] != null)
        (strings.productsAveragePrice, money(summary['average_selling_price'])),
      if (summary['top_product_revenue_share'] != null)
        (strings.productsConcentration, '${summary['top_product_revenue_share']}%'),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (data['status'] == 'partial_ready') ...[
          _ProductState(message: strings.partialReady, icon: Icons.info_outline),
          const SizedBox(height: 16),
        ],
        Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [for (final metric in metrics) _ProductMetric(label: metric.$1, value: metric.$2)],
        ),
        const SizedBox(height: 20),
        Wrap(
          spacing: 12,
          runSpacing: 12,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            DropdownButton<String?>(
              value: category,
              hint: Text(strings.categoryLabel),
              items: [
                DropdownMenuItem(value: null, child: Text(strings.allLabel)),
                for (final item in categories)
                  DropdownMenuItem(value: '${item['category']}', child: Text('${item['category']}')),
              ],
              onChanged: onCategory,
            ),
            SegmentedButton<String?>(
              segments: [
                ButtonSegment(value: null, label: Text(strings.allLabel)),
                ButtonSegment(value: 'strong', label: Text(strings.strongLabel)),
                ButtonSegment(value: 'weak', label: Text(strings.weakLabel)),
              ],
              selected: {performance},
              onSelectionChanged: (value) => onPerformance(value.first),
            ),
            DropdownButton<String>(
              value: sortBy,
              items: [
                DropdownMenuItem(value: 'revenue', child: Text('${strings.sortLabel}: ${strings.revenueLabel}')),
                DropdownMenuItem(value: 'quantity', child: Text('${strings.sortLabel}: ${strings.unitsLabel}')),
                DropdownMenuItem(value: 'last_activity', child: Text('${strings.sortLabel}: ${strings.lastActivityLabel}')),
              ],
              onChanged: (value) {
                if (value != null) onSort(value);
              },
            ),
          ],
        ),
        const SizedBox(height: 16),
        LayoutBuilder(
          builder: (context, constraints) => constraints.maxWidth < 720
              ? Column(
                  children: [
                    for (final item in items)
                      _ProductListTile(
                        item: item,
                        money: money,
                        number: number,
                        onTap: () => onProduct('${item['product_id']}'),
                      ),
                  ],
                )
              : SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: DataTable(
                    columns: [
                      DataColumn(label: Text(strings.productLabel)),
                      DataColumn(label: Text(strings.categoryLabel)),
                      DataColumn(label: Text(strings.revenueLabel)),
                      DataColumn(label: Text(strings.unitsLabel)),
                      DataColumn(label: Text(strings.averagePriceLabel)),
                      DataColumn(label: Text(strings.lastActivityLabel)),
                      DataColumn(label: Text(strings.performanceLabel)),
                    ],
                    rows: [
                      for (final item in items)
                        DataRow(
                          onSelectChanged: (_) => onProduct('${item['product_id']}'),
                          cells: [
                            DataCell(Text(item['name']?.toString() ?? '${item['product_id']}')),
                            DataCell(Text(item['category']?.toString() ?? '—')),
                            DataCell(Text(money(item['revenue']))),
                            DataCell(Text(number(item['quantity']))),
                            DataCell(Text(money(item['average_price']))),
                            DataCell(Text(_date(context, item['last_activity']))),
                            DataCell(Text(_performance(strings, item['performance']))),
                          ],
                        ),
                    ],
                  ),
                ),
        ),
        const SizedBox(height: 12),
        Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            Text('${pagination['page']} / ${pagination['pages']}'),
            IconButton(
              tooltip: company.previousPage,
              onPressed: pagination['page'] > 1 ? () => onPage(pagination['page'] - 1) : null,
              icon: const Icon(Icons.chevron_left),
            ),
            IconButton(
              tooltip: company.nextPage,
              onPressed: pagination['page'] < pagination['pages'] ? () => onPage(pagination['page'] + 1) : null,
              icon: const Icon(Icons.chevron_right),
            ),
          ],
        ),
      ],
    );
  }
}

String _date(BuildContext context, dynamic value) => value == null
    ? '—'
    : DateFormat.yMd(Localizations.localeOf(context).toLanguageTag()).format(DateTime.parse('$value'));

String _performance(Phase4dStrings strings, dynamic value) => switch (value) {
      'strong' => strings.strongLabel,
      'weak' => strings.weakLabel,
      _ => '—',
    };

class _ProductListTile extends StatelessWidget {
  const _ProductListTile({required this.item, required this.money, required this.number, required this.onTap});
  final Map<String, dynamic> item;
  final String Function(dynamic) money;
  final String Function(dynamic) number;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final strings = AvenqoLocaleScope.translationsOf(context).phase4d;
    final colors = AvenqoColors.of(context);
    return ListTile(
      onTap: onTap,
      contentPadding: const EdgeInsets.symmetric(horizontal: 4),
      title: Text(item['name']?.toString() ?? '${item['product_id']}', style: TextStyle(color: colors.ink, fontWeight: FontWeight.w700)),
      subtitle: Text(item['category']?.toString() ?? '—', style: TextStyle(color: colors.muted)),
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(money(item['revenue']), style: TextStyle(color: colors.ink, fontWeight: FontWeight.w700)),
          Text('${number(item['quantity'])} ${strings.unitsLabel}', style: TextStyle(color: colors.muted, fontSize: 12)),
        ],
      ),
    );
  }
}

class _ProductMetric extends StatelessWidget {
  const _ProductMetric({required this.label, required this.value});
  final String label;
  final String value;
  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(
      width: 190,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: colors.surface, border: Border.all(color: colors.line), borderRadius: BorderRadius.circular(8)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: TextStyle(color: colors.muted)),
        const SizedBox(height: 6),
        Text(value, style: TextStyle(color: colors.ink, fontSize: 20, fontWeight: FontWeight.w800)),
      ]),
    );
  }
}

class _ProductState extends StatelessWidget {
  const _ProductState({required this.message, this.icon = Icons.inventory_2_outlined, this.action, this.onPressed});
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

class _ProductDetailDialog extends StatelessWidget {
  const _ProductDetailDialog({required this.future});
  final Future<Map<String, dynamic>> future;
  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(AvenqoLocaleScope.translationsOf(context).phase4d.productLabel),
        content: SizedBox(
          width: 420,
          child: FutureBuilder<Map<String, dynamic>>(
            future: future,
            builder: (context, snapshot) {
              if (snapshot.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
              if (snapshot.hasError) return Text(AvenqoLocaleScope.translationsOf(context).company.connectionsGenericError);
              final item = snapshot.data!;
              final currency = item['currency']?.toString() ?? 'USD';
              final locale = Localizations.localeOf(context).toLanguageTag();
              return Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(item['name']?.toString() ?? '${item['product_id']}', style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: 12),
                if (item['revenue'] is num)
                  Text(formatMoney(item['revenue'] as num, locale: locale, currencyCode: currency)),
                if (item['category'] != null) Text('${item['category']}'),
              ]);
            },
          ),
        ),
        actions: [IconButton(onPressed: () => Navigator.pop(context), icon: const Icon(Icons.close))],
      );
}