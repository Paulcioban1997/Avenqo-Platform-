import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
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
}

class RetailInventoryPage extends StatefulWidget {
  const RetailInventoryPage({super.key, required this.api});

  final ApiClient api;

  @override
  State<RetailInventoryPage> createState() => _RetailInventoryPageState();
}

class _RetailInventoryPageState extends State<RetailInventoryPage> {
  late Future<_InventoryData> _future;
  String _filter = 'all'; // 'all', 'low', 'out'
  String _searchQuery = '';

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

  Future<_InventoryData> _fetch() async {
    final results = await Future.wait([
      widget.api.get('/products/summary?page_size=100').catchError((_) => <String, dynamic>{}),
      widget.api.get('/connectors').catchError((_) => <dynamic>[]),
    ]);

    final prodMap = (results[0] is Map) ? results[0] as Map<String, dynamic> : <String, dynamic>{};
    final products = (prodMap['items'] is List)
        ? (prodMap['items'] as List).cast<Map<String, dynamic>>()
        : (prodMap['products'] is List)
            ? (prodMap['products'] as List).cast<Map<String, dynamic>>()
            : <Map<String, dynamic>>[];
    final connections = (results[1] is List)
        ? (results[1] as List).cast<Map<String, dynamic>>()
        : <Map<String, dynamic>>[];

    return _InventoryData(products: products, connections: connections);
  }

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);

    return Scaffold(
      backgroundColor: colors.canvas,
      body: FutureBuilder<_InventoryData>(
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
                  Text('Erreur lors du chargement de l’inventaire', style: TextStyle(color: colors.ink, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 8),
                  FilledButton.icon(onPressed: _reload, icon: const Icon(Icons.refresh), label: const Text('Réessayer')),
                ],
              ),
            );
          }

          final data = snapshot.data ?? const _InventoryData(products: [], connections: []);
          final allProducts = data.products;

          // Compute Inventory Stats
          var totalUnits = 0;
          var lowStockCount = 0;
          var outOfStockCount = 0;

          for (final p in allProducts) {
            final stock = (p['stock_level'] as num?)?.toInt() ?? (p['stock'] as num?)?.toInt() ?? (p['quantity'] as num?)?.toInt() ?? (p['inventory_level'] as num?)?.toInt() ?? 0;
            totalUnits += stock;
            if (stock <= 0) {
              outOfStockCount++;
            } else if (stock <= 10) {
              lowStockCount++;
            }
          }

          // Filter products
          final filtered = allProducts.where((p) {
            final name = (p['name']?.toString() ?? p['title']?.toString() ?? '').toLowerCase();
            final category = (p['category']?.toString() ?? '').toLowerCase();
            final matchesSearch = _searchQuery.isEmpty || name.contains(_searchQuery) || category.contains(_searchQuery);
            if (!matchesSearch) return false;

            final stock = (p['stock_level'] as num?)?.toInt() ?? (p['stock'] as num?)?.toInt() ?? (p['quantity'] as num?)?.toInt() ?? (p['inventory_level'] as num?)?.toInt() ?? 0;
            if (_filter == 'low') return stock > 0 && stock <= 10;
            if (_filter == 'out') return stock <= 0;
            return true;
          }).toList();

          // Active connector info
          final activeConn = data.connections.firstWhere((c) => c['status'] == 'READY', orElse: () => {});
          final syncProvider = activeConn['provider']?.toString() ?? 'Non connecté';
          final lastSync = activeConn['last_successful_sync']?.toString() ?? 'Récemment';

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
                      Text('Inventaire & Stocks', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w800, color: colors.ink)),
                      const SizedBox(height: 4),
                      Text('Suivi des niveaux de stock, ruptures et alertes de réapprovisionnement en temps réel.', style: TextStyle(fontSize: 14, color: colors.muted)),
                    ],
                  ),
                  Row(
                    children: [
                      IconButton(onPressed: _reload, tooltip: 'Actualiser', icon: const Icon(Icons.refresh)),
                      const SizedBox(width: 8),
                      OutlinedButton.icon(
                        onPressed: () => context.go('/connections'),
                        icon: const Icon(Icons.sync_alt, size: 16),
                        label: const Text('Gérer les flux'),
                      ),
                    ],
                  ),
                ],
              ),
              const SizedBox(height: 20),

              // Architecture Notice: Separation of business_sync and data_cleaning
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                decoration: BoxDecoration(
                  color: _Brand.blue.withValues(alpha: 0.08),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: _Brand.blue.withValues(alpha: 0.25)),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.verified_outlined, size: 20, color: _Brand.blue),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        'Architecture de synchronisation : Les variations de stock proviennent du flux métier direct (business_sync). Le nettoyage structurel (data_cleaning) opère de manière strictement indépendante.',
                        style: TextStyle(fontSize: 13, color: colors.ink, height: 1.35),
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: colors.surface,
                        borderRadius: BorderRadius.circular(4),
                        border: Border.all(color: colors.line),
                      ),
                      child: Text(
                        'Source : $syncProvider',
                        style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: colors.ink),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 20),

              // Metric Cards Row
              LayoutBuilder(
                builder: (context, constraints) {
                  final wide = constraints.maxWidth > 800;
                  final cards = [
                    _buildMetricCard('Unités en stock total', '$totalUnits', Icons.warehouse_outlined, _Brand.blue, colors),
                    _buildMetricCard('Stocks faibles (≤ 10)', '$lowStockCount', Icons.warning_amber_rounded, _Brand.amber, colors, isAlert: lowStockCount > 0),
                    _buildMetricCard('Ruptures de stock', '$outOfStockCount', Icons.remove_shopping_cart_outlined, _Brand.rose, colors, isAlert: outOfStockCount > 0),
                    _buildMetricCard('Dernière synchro', lastSync.length > 16 ? lastSync.substring(0, 16).replaceAll('T', ' ') : lastSync, Icons.schedule, _Brand.emerald, colors),
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

              // Filter & Search Controls
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      onChanged: (val) => setState(() => _searchQuery = val.trim().toLowerCase()),
                      decoration: InputDecoration(
                        hintText: 'Rechercher un produit, SKU ou catégorie...',
                        prefixIcon: const Icon(Icons.search, size: 20),
                        filled: true,
                        fillColor: colors.surface,
                        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: colors.line)),
                        enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: colors.line)),
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  SegmentedButton<String>(
                    segments: const [
                      ButtonSegment(value: 'all', label: Text('Tous')),
                      ButtonSegment(value: 'low', label: Text('Faible stock')),
                      ButtonSegment(value: 'out', label: Text('Rupture')),
                    ],
                    selected: {_filter},
                    onSelectionChanged: (set) => setState(() => _filter = set.first),
                  ),
                ],
              ),
              const SizedBox(height: 16),

              // Inventory Table
              Container(
                decoration: BoxDecoration(
                  color: colors.surface,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: colors.line),
                ),
                child: filtered.isEmpty
                    ? Padding(
                        padding: const EdgeInsets.symmetric(vertical: 40),
                        child: Center(
                          child: Text('Aucun produit ne correspond aux filtres.', style: TextStyle(color: colors.muted)),
                        ),
                      )
                    : ClipRRect(
                        borderRadius: BorderRadius.circular(12),
                        child: AvenqoDataTable(
                          semanticLabel: 'Tableau d\'inventaire des stocks',
                          columns: const [
                            DataColumn(label: Text('Produit')),
                            DataColumn(label: Text('Catégorie')),
                            DataColumn(label: Text('Stock disponible'), numeric: true),
                            DataColumn(label: Text('Prix unitaire'), numeric: true),
                            DataColumn(label: Text('Statut inventaire')),
                            DataColumn(label: Text('Action')),
                          ],
                          rows: [
                            for (final p in filtered)
                              DataRow(
                                cells: [
                                  DataCell(
                                    Text(
                                      p['name']?.toString() ?? p['title']?.toString() ?? 'Produit sans titre',
                                      style: TextStyle(fontWeight: FontWeight.bold, color: colors.ink),
                                    ),
                                  ),
                                  DataCell(Text(p['category']?.toString() ?? 'Standard', style: TextStyle(color: colors.muted))),
                                  DataCell(
                                    Builder(
                                      builder: (context) {
                                        final s = (p['stock_level'] as num?)?.toInt() ?? (p['stock'] as num?)?.toInt() ?? (p['quantity'] as num?)?.toInt() ?? (p['inventory_level'] as num?)?.toInt() ?? 0;
                                        return Text(
                                          '$s',
                                          style: TextStyle(
                                            fontWeight: FontWeight.bold,
                                            color: (s <= 0)
                                                ? _Brand.rose
                                                : ((s <= 10) ? _Brand.amber : colors.ink),
                                          ),
                                        );
                                      },
                                    ),
                                  ),
                                  DataCell(Text(_formatMoney(context, (p['price'] as num?)?.toDouble() ?? (p['average_price'] as num?)?.toDouble() ?? 0.0, 'CAD'))),
                                  DataCell(_buildStockBadge((p['stock_level'] as num?)?.toInt() ?? (p['stock'] as num?)?.toInt() ?? (p['quantity'] as num?)?.toInt() ?? (p['inventory_level'] as num?)?.toInt() ?? 0)),
                                  DataCell(
                                    TextButton(
                                      onPressed: () => context.go('/retail/products?product_id=${p['product_id'] ?? p['id']}'),
                                      child: const Text('Détails'),
                                    ),
                                  ),
                                ],
                              ),
                          ],
                        ),
                      ),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildMetricCard(String label, String value, IconData icon, Color color, AvenqoColors colors, {bool isAlert = false}) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: isAlert ? color.withValues(alpha: 0.4) : colors.line),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(8)),
            child: Icon(icon, color: color, size: 22),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: TextStyle(color: colors.muted, fontSize: 12, fontWeight: FontWeight.w600)),
                const SizedBox(height: 4),
                Text(
                  value,
                  style: TextStyle(color: isAlert ? color : colors.ink, fontSize: 20, fontWeight: FontWeight.w800),
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStockBadge(num stock) {
    final qty = stock.toInt();
    if (qty <= 0) {
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(color: _Brand.rose.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(4)),
        child: const Text('Rupture', style: TextStyle(color: _Brand.rose, fontSize: 11, fontWeight: FontWeight.bold)),
      );
    }
    if (qty <= 10) {
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(color: _Brand.amber.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(4)),
        child: const Text('Stock faible', style: TextStyle(color: _Brand.amber, fontSize: 11, fontWeight: FontWeight.bold)),
      );
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(color: _Brand.emerald.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(4)),
      child: const Text('En stock', style: TextStyle(color: _Brand.emerald, fontSize: 11, fontWeight: FontWeight.bold)),
    );
  }
}

class _InventoryData {
  const _InventoryData({required this.products, required this.connections});
  final List<Map<String, dynamic>> products;
  final List<Map<String, dynamic>> connections;
}

String _formatMoney(BuildContext context, num value, [String currency = 'CAD']) {
  final locale = AvenqoLocaleScope.of(context).code;
  return formatMoney(value, locale: locale, currencyCode: currency);
}

