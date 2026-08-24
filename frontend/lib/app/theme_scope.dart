import 'package:flutter/widgets.dart';

import 'package:avenqo/app/theme_controller.dart';

/// Rend le [ThemeController] disponible à tout l'arbre de widgets, même
/// esprit que `AvenqoLocaleScope` (InheritedNotifier, pas de prop-drilling).
class AvenqoThemeScope extends InheritedNotifier<ThemeController> {
  const AvenqoThemeScope({super.key, required ThemeController controller, required super.child})
      : super(notifier: controller);

  static ThemeController of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<AvenqoThemeScope>();
    assert(scope != null, 'AvenqoThemeScope introuvable dans le contexte.');
    return scope!.notifier!;
  }
}
