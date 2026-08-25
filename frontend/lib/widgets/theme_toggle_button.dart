import 'package:flutter/material.dart';

import 'package:avenqo/app/theme_controller.dart';
import 'package:avenqo/app/theme_scope.dart';
import 'package:avenqo/i18n/locale_scope.dart';

/// Petit menu clair/sombre/système, même esprit que [LanguageSelector] —
/// aucun état local, lit/écrit directement le [ThemeController] partagé.
/// Icône soleil/lune : signature visuelle constante à côté du sélecteur de
/// langue sur tout Avenqo (landing, auth, client, admin).
class ThemeToggleButton extends StatelessWidget {
  const ThemeToggleButton({super.key, this.foregroundColor});

  final Color? foregroundColor;

  IconData _iconFor(ThemeMode mode) => switch (mode) {
    ThemeMode.light => Icons.light_mode_outlined,
    ThemeMode.dark => Icons.dark_mode_outlined,
    ThemeMode.system => Icons.brightness_auto_outlined,
  };

  @override
  Widget build(BuildContext context) {
    final controller = AvenqoThemeScope.of(context);
    final t = AvenqoLocaleScope.translationsOf(context).company;
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        final tooltip = controller.mode == ThemeMode.dark
            ? t.themeToggleSwitchToLight
            : t.themeToggleSwitchToDark;
        return PopupMenuButton<ThemeMode>(
          tooltip: tooltip,
          icon: Icon(_iconFor(controller.mode), color: foregroundColor),
          onSelected: controller.setMode,
          itemBuilder: (context) => [
            PopupMenuItem(
              value: ThemeMode.light,
              child: Text(t.settingsThemeLight),
            ),
            PopupMenuItem(
              value: ThemeMode.dark,
              child: Text(t.settingsThemeDark),
            ),
            PopupMenuItem(
              value: ThemeMode.system,
              child: Text(t.settingsThemeSystem),
            ),
          ],
        );
      },
    );
  }
}
