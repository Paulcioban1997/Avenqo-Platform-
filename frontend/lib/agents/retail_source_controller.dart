import 'package:flutter/widgets.dart';

import 'package:avenqo/core/api_client.dart';

class RetailSource {
  const RetailSource({
    required this.sourceType,
    required this.sourceId,
    required this.displayName,
    required this.status,
    required this.active,
    this.datasetId,
    this.connectionId,
    this.provider,
    this.lastSynchronizedAt,
  });

  factory RetailSource.fromJson(Map<String, dynamic> json) => RetailSource(
    sourceType: json['source_type'].toString(),
    sourceId: json['source_id'].toString(),
    datasetId: json['dataset_id']?.toString(),
    connectionId: json['connection_id']?.toString(),
    displayName: json['display_name'].toString(),
    provider: json['provider']?.toString(),
    status: json['status'].toString(),
    lastSynchronizedAt: json['last_synchronized_at'] == null
        ? null
        : DateTime.tryParse(json['last_synchronized_at'].toString()),
    active: json['active'] == true,
  );

  final String sourceType;
  final String sourceId;
  final String? datasetId;
  final String? connectionId;
  final String displayName;
  final String? provider;
  final String status;
  final DateTime? lastSynchronizedAt;
  final bool active;

  bool get isShopify => provider == 'shopify';
}

class RetailSourceController extends ChangeNotifier {
  RetailSourceController(this.api);

  final ApiClient api;
  List<RetailSource> sources = const [];
  bool loading = false;
  Object? error;

  RetailSource? get active {
    for (final source in sources) {
      if (source.active) return source;
    }
    return null;
  }

  Future<void> load() async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      final payload = await api.get('/retail/sources') as List<dynamic>;
      sources = payload
          .cast<Map<String, dynamic>>()
          .map(RetailSource.fromJson)
          .toList(growable: false);
    } on Object catch (caught) {
      error = caught;
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<void> select(RetailSource source) async {
    if (source.active || loading) return;
    loading = true;
    error = null;
    notifyListeners();
    try {
      await api.put(
        '/retail/sources/active',
        body: {'source_type': source.sourceType, 'source_id': source.sourceId},
      );
      sources = [
        for (final item in sources)
          RetailSource(
            sourceType: item.sourceType,
            sourceId: item.sourceId,
            datasetId: item.datasetId,
            connectionId: item.connectionId,
            displayName: item.displayName,
            provider: item.provider,
            status: item.status,
            lastSynchronizedAt: item.lastSynchronizedAt,
            active: item.sourceId == source.sourceId,
          ),
      ];
    } on Object catch (caught) {
      error = caught;
      rethrow;
    } finally {
      loading = false;
      notifyListeners();
    }
  }
}

class RetailSourceScope extends InheritedNotifier<RetailSourceController> {
  const RetailSourceScope({
    super.key,
    required RetailSourceController controller,
    required super.child,
  }) : super(notifier: controller);

  static RetailSourceController of(BuildContext context) {
    final scope = context
        .dependOnInheritedWidgetOfExactType<RetailSourceScope>();
    assert(scope != null, 'RetailSourceScope is missing');
    return scope!.notifier!;
  }

  static RetailSourceController? maybeOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<RetailSourceScope>()?.notifier;
}

enum RetailEmptyKind { overview, sales, customers, products }

String? activeShopifyEmptyMessage(BuildContext context, RetailEmptyKind kind) {
  if (RetailSourceScope.maybeOf(context)?.active?.isShopify != true) {
    return null;
  }
  final french = Localizations.localeOf(context).languageCode == 'fr';
  return switch ((french, kind)) {
    (true, RetailEmptyKind.overview) =>
      'Aucune donnée Shopify disponible pour cette période.',
    (true, RetailEmptyKind.sales) => 'Aucune commande Shopify synchronisée.',
    (true, RetailEmptyKind.customers) => 'Aucun client Shopify synchronisé.',
    (true, RetailEmptyKind.products) => 'Aucun produit Shopify synchronisé.',
    (false, RetailEmptyKind.overview) =>
      'No Shopify data is available for this period.',
    (false, RetailEmptyKind.sales) =>
      'No Shopify orders have been synchronized.',
    (false, RetailEmptyKind.customers) =>
      'No Shopify customers have been synchronized.',
    (false, RetailEmptyKind.products) =>
      'No Shopify products have been synchronized.',
  };
}
