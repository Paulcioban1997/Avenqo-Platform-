import 'package:flutter/material.dart';

import 'package:avenqo/i18n/translations.dart';

class AppDestination {
  const AppDestination({
    required this.path,
    required this.label,
    required this.description,
    required this.icon,
    this.sectionBreakBefore = false,
  });

  final String path;
  final String label;
  final String description;
  final IconData icon;
  final bool sectionBreakBefore;

  AppDestination copyWith({String? label, String? description}) => AppDestination(
        path: path,
        label: label ?? this.label,
        description: description ?? this.description,
        icon: icon,
        sectionBreakBefore: sectionBreakBefore,
      );
}

/// Retourne [destination] avec son libellé/description traduits selon la
/// langue active — la liste [appDestinations] elle-même reste un contenu
/// fixe (chemins/icônes/tests unitaires), seule la présentation change.
AppDestination localizeDestination(AppDestination destination, CompanyStrings t) {
  return switch (destination.path) {
    '/dashboard' => destination.copyWith(label: t.navOverviewLabel, description: t.navOverviewDescription),
    '/assistant' => destination.copyWith(label: t.navAssistantLabel, description: t.navAssistantDescription),
    '/sales' => destination.copyWith(label: t.navSalesLabel, description: t.navSalesDescription),
    '/customers' => destination.copyWith(label: t.navCustomersLabel, description: t.navCustomersDescription),
    '/products' => destination.copyWith(label: t.navProductsLabel, description: t.navProductsDescription),
    '/recommendations' =>
      destination.copyWith(label: t.navRecommendationsLabel, description: t.navRecommendationsDescription),
    '/alerts' => destination.copyWith(label: t.navAlertsLabel, description: t.navAlertsDescription),
    '/reports' => destination.copyWith(label: t.navReportsLabel, description: t.navReportsDescription),
    '/connections' => destination.copyWith(label: t.navConnectionsLabel, description: t.navConnectionsDescription),
    '/team' => destination.copyWith(label: t.navTeamLabel, description: t.navTeamDescription),
    '/billing' => destination.copyWith(label: t.navBillingLabel, description: t.navBillingDescription),
    '/settings' => destination.copyWith(label: t.navSettingsLabel, description: t.navSettingsDescription),
    '/support' => destination.copyWith(label: t.navSupportLabel, description: t.navSupportDescription),
    _ => destination,
  };
}

const appDestinations = <AppDestination>[
  AppDestination(
    path: '/dashboard',
    label: 'Vue d’ensemble',
    description: 'Les indicateurs essentiels de votre activité.',
    icon: Icons.home_outlined,
  ),
  AppDestination(
    path: '/assistant',
    label: 'AI Assistant',
    description: 'Posez vos questions et passez à l’action.',
    icon: Icons.auto_awesome_outlined,
  ),
  AppDestination(
    path: '/sales',
    label: 'Ventes',
    description: 'Suivez le chiffre d’affaires et les tendances.',
    icon: Icons.trending_up,
  ),
  AppDestination(
    path: '/customers',
    label: 'Clients',
    description: 'Comprenez la fidélité et les risques de départ.',
    icon: Icons.people_outline,
  ),
  AppDestination(
    path: '/products',
    label: 'Produits',
    description: 'Pilotez la demande et les performances du catalogue.',
    icon: Icons.inventory_2_outlined,
  ),
  AppDestination(
    path: '/recommendations',
    label: 'Recommandations',
    description: 'Retrouvez les opportunités prioritaires.',
    icon: Icons.lightbulb_outline,
  ),
  AppDestination(
    path: '/alerts',
    label: 'Alertes',
    description: 'Surveillez les changements qui demandent votre attention.',
    icon: Icons.notifications_none,
  ),
  AppDestination(
    path: '/reports',
    label: 'Rapports',
    description: 'Consultez et partagez vos synthèses de direction.',
    icon: Icons.description_outlined,
  ),
  AppDestination(
    path: '/connections',
    label: 'Connexions',
    description: 'Reliez vos outils de ventes et de gestion.',
    icon: Icons.sync_alt,
    sectionBreakBefore: true,
  ),
  AppDestination(
    path: '/team',
    label: 'Équipe',
    description: 'Gérez les accès de vos collaborateurs.',
    icon: Icons.group_outlined,
  ),
  AppDestination(
    path: '/billing',
    label: 'Facturation',
    description: 'Gérez votre abonnement et vos factures.',
    icon: Icons.receipt_long_outlined,
  ),
  AppDestination(
    path: '/settings',
    label: 'Paramètres',
    description: 'Préférences de votre entreprise et de votre compte.',
    icon: Icons.settings_outlined,
  ),
  AppDestination(
    path: '/support',
    label: 'Avenqo Support',
    description: "Besoin d'aide pour utiliser Avenqo ? Posez votre question ici.",
    icon: Icons.help_outline,
    sectionBreakBefore: true,
  ),
];

AppDestination destinationFor(String path) {
  return appDestinations.firstWhere(
    (destination) => destination.path == path,
    orElse: () => appDestinations.first,
  );
}
