import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/app/destinations.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/i18n/translations.dart';

class _Brand {
  const _Brand._();
  static const blue = Color(0xFF087CF0);
}

class BusinessPage extends StatelessWidget {
  const BusinessPage({super.key, required this.destination});
  final AppDestination destination;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final t = AvenqoLocaleScope.translationsOf(context).company;
    final localized = localizeDestination(
      destination,
      AvenqoLocaleScope.translationsOf(context),
    );
    final content = _contentFor(destination.path, t) ??
        (t.businessDefaultTitle, t.businessDefaultDescription);
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1200),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(localized.label, style: Theme.of(context).textTheme.headlineMedium),
              const SizedBox(height: 6),
              Text(localized.description, style: TextStyle(color: colors.muted)),
              const SizedBox(height: 28),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(28),
                decoration: BoxDecoration(color: colors.surface, border: Border.all(color: colors.line), borderRadius: BorderRadius.circular(12)),
                child: Column(
                  children: [
                    Icon(destination.icon, size: 36, color: _Brand.blue),
                    const SizedBox(height: 14),
                    Text(content.$1, style: Theme.of(context).textTheme.titleLarge),
                    const SizedBox(height: 8),
                    Text(content.$2, textAlign: TextAlign.center, style: TextStyle(color: colors.muted)),
                    const SizedBox(height: 20),
                    FilledButton.icon(
                      onPressed: () => context.go('/connections'),
                      style: FilledButton.styleFrom(backgroundColor: _Brand.blue),
                      icon: const Icon(Icons.add_link),
                      label: Text(t.businessConnectButton),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

(String, String)? _contentFor(String path, CompanyStrings t) => switch (path) {
      '/sales' => (t.businessSalesTitle, t.businessSalesDescription),
      '/customers' => (t.businessCustomersTitle, t.businessCustomersDescription),
      '/products' => (t.businessProductsTitle, t.businessProductsDescription),
      '/recommendations' => (t.businessRecommendationsTitle, t.businessRecommendationsDescription),
      '/alerts' => (t.businessAlertsTitle, t.businessAlertsDescription),
      '/reports' => (t.businessReportsTitle, t.businessReportsDescription),
      _ => null,
    };