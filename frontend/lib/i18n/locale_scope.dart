import 'package:flutter/widgets.dart';

import 'package:avenqo/i18n/locale_controller.dart';
import 'package:avenqo/i18n/translations.dart';

/// Rend le [LocaleController] disponible à tout l'arbre de widgets sans le
/// passer manuellement de page en page — même esprit que AuthController mais
/// via InheritedNotifier (aucune dépendance externe type provider/riverpod).
class AvenqoLocaleScope extends InheritedNotifier<LocaleController> {
  const AvenqoLocaleScope({super.key, required LocaleController controller, required super.child})
      : super(notifier: controller);

  static LocaleController of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<AvenqoLocaleScope>();
    assert(scope != null, 'AvenqoLocaleScope introuvable dans le contexte.');
    return scope!.notifier!;
  }

  /// Traductions de la langue active. Retombe sur les libellés fournis en cas
  /// de chargement initial (première frame, avant que le JSON soit lisible).
  static Translations translationsOf(BuildContext context) {
    final controller = of(context);
    final translations = controller.translations;
    assert(translations != null, 'LocaleController.initialize() doit être appelé avant le premier build.');
    return translations!;
  }

  /// Comme [translationsOf], mais retourne `null` (au lieu de planter) si le
  /// scope est absent — utile pour des widgets réutilisés dans des tests
  /// isolés qui ne montent pas toute l'app (ex. `AssistantPage` seul).
  static Translations? maybeTranslationsOf(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<AvenqoLocaleScope>();
    return scope?.notifier?.translations;
  }
}
