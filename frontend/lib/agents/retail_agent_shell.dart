import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/app/avenqo_colors.dart';
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

class RetailAgentShell extends StatelessWidget {
  const RetailAgentShell({
    super.key,
    required this.currentPath,
    required this.child,
    this.onSelect,
  });

  final String currentPath;
  final Widget child;
  final ValueChanged<String>? onSelect;

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
              height: 58,
              child: ListView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                children: [
                  Padding(
                    padding: const EdgeInsets.only(right: 14),
                    child: Row(
                      children: [
                        const Icon(Icons.storefront_outlined, color: Color(0xFF087CF0), size: 20),
                        const SizedBox(width: 8),
                        Text(
                          strings.value('retailName'),
                          style: TextStyle(color: colors.ink, fontWeight: FontWeight.w800),
                        ),
                      ],
                    ),
                  ),
                  for (final destination in retailAgentDestinations)
                    Padding(
                      padding: const EdgeInsets.only(right: 6),
                      child: _RetailNavigationItem(
                        destination: destination,
                        label: strings.value(destination.labelKey),
                        selected: currentPath == destination.path,
                        onTap: () => (onSelect ?? context.go)(destination.path),
                      ),
                    ),
                ],
              ),
            ),
          ),
        ),
        Expanded(child: child),
      ],
    );
  }
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