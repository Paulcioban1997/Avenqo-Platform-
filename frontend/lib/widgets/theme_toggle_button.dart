import 'package:flutter/material.dart';

import 'package:avenqo/app/theme_controller.dart';
import 'package:avenqo/app/theme_scope.dart';

/// Petit menu clair/sombre/système, même esprit que [LanguageSelector] —
/// aucun état local, lit/écrit directement le [ThemeController] partagé.
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
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        return PopupMenuButton<ThemeMode>(
          tooltip: 'Theme',
          icon: Icon(_iconFor(controller.mode), color: foregroundColor),
          onSelected: controller.setMode,
          itemBuilder: (context) => const [
            PopupMenuItem(value: ThemeMode.light, child: Text('Light')),
            PopupMenuItem(value: ThemeMode.dark, child: Text('Dark')),
            PopupMenuItem(value: ThemeMode.system, child: Text('System')),
          ],
        );
      },
    );
  }
}
