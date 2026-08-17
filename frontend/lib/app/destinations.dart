import 'package:flutter/material.dart';

class AppDestination {
  const AppDestination({
    required this.path,
    required this.label,
    required this.description,
    required this.icon,
  });

  final String path;
  final String label;
  final String description;
  final IconData icon;
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
    label: 'Assistant Avenqo',
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
];

AppDestination destinationFor(String path) {
  return appDestinations.firstWhere(
    (destination) => destination.path == path,
    orElse: () => appDestinations.first,
  );
}
