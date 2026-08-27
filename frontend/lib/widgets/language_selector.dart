import 'package:flutter/material.dart';

import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/i18n/locale_controller.dart';
import 'package:avenqo/i18n/locale_info.dart';
import 'package:avenqo/i18n/locale_scope.dart';

/// Sélecteur de langue mince, miroir de web/src/components/region-language-selector.tsx :
/// regroupe les langues disponibles par région dans un menu déroulant.
class LanguageSelector extends StatelessWidget {
  const LanguageSelector({super.key, this.foregroundColor});

  final Color? foregroundColor;

  static const Map<String, String> _regionLabels = {
    'americas': 'Amériques',
    'europe': 'Europe',
    'middle-east': 'Moyen-Orient',
    'africa': 'Afrique',
    'asia': 'Asie-Pacifique',
  };

  @override
  Widget build(BuildContext context) {
    final controller = AvenqoLocaleScope.of(context);
    final effectiveForeground = foregroundColor ?? AvenqoColors.of(context).muted;
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final current = controller.currentLocaleInfo;
        return PopupMenuButton<String>(
          tooltip: 'Changer de langue',
          onSelected: controller.setLocale,
          itemBuilder: (context) => _buildMenuItems(controller),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(current?.flag ?? '🌐', style: const TextStyle(fontSize: 16)),
                const SizedBox(width: 6),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 150),
                  child: Text(
                    current?.nativeName ?? current?.code.toUpperCase() ?? '',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: effectiveForeground,
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                const SizedBox(width: 2),
                Icon(Icons.expand_more, size: 16, color: effectiveForeground),
              ],
            ),
          ),
        );
      },
    );
  }

  List<PopupMenuEntry<String>> _buildMenuItems(LocaleController controller) {
    final byRegion = <String, List<LocaleInfo>>{};
    for (final locale in controller.availableLocales) {
      byRegion.putIfAbsent(locale.region, () => []).add(locale);
    }
    final entries = <PopupMenuEntry<String>>[];
    for (final region in _regionLabels.keys) {
      final locales = byRegion[region];
      if (locales == null || locales.isEmpty) {
        continue;
      }
      entries.add(
        PopupMenuItem<String>(
          enabled: false,
          child: Text(
            _regionLabels[region]!,
            style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 12),
          ),
        ),
      );
      for (final locale in locales) {
        entries.add(
          PopupMenuItem<String>(
            value: locale.code,
            child: Row(
              children: [
                Text(locale.flag),
                const SizedBox(width: 8),
                Text(locale.nativeName),
              ],
            ),
          ),
        );
      }
    }
    return entries;
  }
}
