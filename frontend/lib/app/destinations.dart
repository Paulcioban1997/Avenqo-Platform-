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
AppDestination localizeDestination(AppDestination destination, Translations translations) {
  final t = translations.company;
  return switch (destination.path) {
    '/agents' => destination.copyWith(
      label: translations.agents.navLabel,
      description: translations.agents.subtitle,
    ),
    '/assistant' => destination.copyWith(label: t.navAssistantLabel, description: t.navAssistantDescription),
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
    path: '/agents',
    label: 'Agents',
    description: 'Specialized business capabilities in one workspace.',
    icon: Icons.apps_outlined,
  ),
  AppDestination(
    path: '/assistant',
    label: 'AI Assistant',
    description: 'Posez vos questions et passez à l’action.',
    icon: Icons.auto_awesome_outlined,
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
