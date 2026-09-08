import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/agents/retail_source_controller.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/i18n/locale_scope.dart';

class RetailAgentDestination {
  const RetailAgentDestination(this.path, this.labelKey, this.icon);

  final String path;
  final String labelKey;
  final IconData icon;
}

const retailAgentDestinations = <RetailAgentDestination>[
  RetailAgentDestination('/retail', 'retailOverviewLabel', Icons.dashboard_outlined),
  RetailAgentDestination('/retail/sales', 'retailSalesLabel', Icons.trending_up),
  RetailAgentDestination('/retail/customers', 'retailCustomersLabel', Icons.people_outline),
  RetailAgentDestination('/retail/products', 'retailProductsLabel', Icons.inventory_2_outlined),
  RetailAgentDestination('/retail/recommendations', 'retailRecommendationsLabel', Icons.lightbulb_outline),
];

class RetailAgentShell extends StatefulWidget {
  const RetailAgentShell({
    super.key,
    required this.api,
    required this.currentPath,
    required this.child,
    this.onSelect,
  });

  final ApiClient api;
  final String currentPath;
  final Widget child;
  final ValueChanged<String>? onSelect;

  @override
  State<RetailAgentShell> createState() => _RetailAgentShellState();
}

class _RetailAgentShellState extends State<RetailAgentShell> {
  late final RetailSourceController _sources = RetailSourceController(widget.api);

  @override
  void initState() {
    super.initState();
    _sources.load();
  }

  @override
  void dispose() {
    _sources.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final strings = AvenqoLocaleScope.translationsOf(context).agents;
    final colors = AvenqoColors.of(context);
    return Column(
      children: [
        Material(
          color: colors.surface,
          child: DecoratedBox(
            decoration: BoxDecoration(
              border: Border(bottom: BorderSide(color: colors.line)),
            ),
            child: SizedBox(
              height: 66,
              child: Row(
                children: [
                  Expanded(
                    child: ListView(
                      scrollDirection: Axis.horizontal,
                      padding: const EdgeInsets.fromLTRB(16, 8, 8, 8),
                      children: [
                        Padding(
                          padding: const EdgeInsets.only(right: 14),
                          child: Row(
                            children: [
                              const Icon(Icons.storefront_outlined, color: Color(0xFF087CF0), size: 20),
                              const SizedBox(width: 8),
                              Text(strings.value('retailName'), style: TextStyle(color: colors.ink, fontWeight: FontWeight.w800)),
                            ],
                          ),
                        ),
                        for (final destination in retailAgentDestinations)
                          Padding(
                            padding: const EdgeInsets.only(right: 6),
                            child: _RetailNavigationItem(
                              destination: destination,
                              label: strings.value(destination.labelKey),
                              selected: widget.currentPath == destination.path,
                              onTap: () => (widget.onSelect ?? context.go)(destination.path),
                            ),
                          ),
                      ],
                    ),
                  ),
                  ListenableBuilder(
                    listenable: _sources,
                    builder: (context, _) => _RetailSourceSelector(
                      controller: _sources,
                      onSelected: (source) async {
                        await _sources.select(source);
                        if (context.mounted) context.go('${widget.currentPath}?source=${source.sourceId}');
                      },
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        Expanded(child: RetailSourceScope(controller: _sources, child: widget.child)),
      ],
    );
  }
}

class _RetailSourceSelector extends StatelessWidget {
  const _RetailSourceSelector({required this.controller, required this.onSelected});

  final RetailSourceController controller;
  final ValueChanged<RetailSource> onSelected;

  @override
  Widget build(BuildContext context) {
    final active = controller.active;
    if (controller.loading && active == null) {
      return const Padding(padding: EdgeInsets.symmetric(horizontal: 16), child: SizedBox.square(dimension: 20, child: CircularProgressIndicator(strokeWidth: 2)));
    }
    if (controller.sources.isEmpty) return const SizedBox.shrink();
    final locale = Localizations.localeOf(context).languageCode;
    final activeLabel = locale == 'fr' ? 'Source active' : 'Active source';
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 5, 16, 5),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(activeLabel, style: TextStyle(color: AvenqoColors.of(context).muted, fontSize: 12, fontWeight: FontWeight.w700)),
          const SizedBox(width: 8),
          DropdownButtonHideUnderline(
            child: DropdownButton<String>(
              key: const Key('retail-source-selector'),
              value: active?.sourceId,
              borderRadius: BorderRadius.circular(6),
              itemHeight: 62,
              onChanged: controller.loading ? null : (value) {
                if (value != null) onSelected(controller.sources.firstWhere((item) => item.sourceId == value));
              },
              items: [
                for (final source in controller.sources)
                  DropdownMenuItem(
                    value: source.sourceId,
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 270),
                      child: Row(
                        children: [
                          Icon(source.isShopify ? Icons.shopping_bag_outlined : Icons.table_chart_outlined, size: 18, color: source.active ? const Color(0xFF1B9E5A) : null),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(source.isShopify ? 'Shopify' : source.displayName, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w700)),
                                Text(_sourceMetadata(source, locale), maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 12, color: AvenqoColors.of(context).muted)),
                              ],
                            ),
                          ),
                        ],
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
}

String _sourceMetadata(RetailSource source, String locale) {
  final synchronized = source.lastSynchronizedAt;
  final timestamp = synchronized == null ? (locale == 'fr' ? 'Pas encore synchronisé' : 'Not synchronized yet') : synchronized.toLocal().toString().substring(0, 16);
  final detail = source.isShopify ? source.displayName : (locale == 'fr' ? 'Dataset importé' : 'Imported dataset');
  return '$detail · ${source.status} · $timestamp';
}

class _RetailNavigationItem extends StatelessWidget {
  const _RetailNavigationItem({
    required this.destination,
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final RetailAgentDestination destination;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => TextButton.icon(
        onPressed: onTap,
        icon: Icon(destination.icon, size: 17),
        label: Text(label, maxLines: 1, overflow: TextOverflow.ellipsis),
        style: TextButton.styleFrom(
          backgroundColor: selected
              ? const Color(0xFF087CF0).withValues(alpha: 0.1)
              : Colors.transparent,
          foregroundColor: selected
              ? const Color(0xFF087CF0)
              : AvenqoColors.of(context).muted,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
        ),
      );
}