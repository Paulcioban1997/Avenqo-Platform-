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

  static const _regionOrder = [
    'americas',
    'europe',
    'middle-east',
    'africa',
    'asia',
  ];

  @override
  Widget build(BuildContext context) {
    final controller = AvenqoLocaleScope.of(context);
    final effectiveForeground = foregroundColor ?? AvenqoColors.of(context).muted;
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final current = controller.currentLocaleInfo;
        return PopupMenuButton<String>(
          tooltip: AvenqoLocaleScope.translationsOf(context)
              .company
              .settingsLanguageLabel,
          constraints: const BoxConstraints(minWidth: 280, maxWidth: 360),
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
    for (final region in _regionOrder) {
      final locales = byRegion[region];
      if (locales == null || locales.isEmpty) {
        continue;
      }
      if (entries.isNotEmpty) {
        entries.add(const PopupMenuDivider());
      }
      for (final locale in locales) {
        entries.add(
          PopupMenuItem<String>(
            value: locale.code,
            height: 56,
            child: Row(
              children: [
                Text(locale.flag),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    locale.nativeName,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          ),
        );
      }
    }
    return entries;
  }
}
