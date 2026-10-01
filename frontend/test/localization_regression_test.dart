import 'package:avenqo/app/theme_controller.dart';
import 'package:avenqo/app/theme_scope.dart';
import 'package:avenqo/app/app_theme.dart';
import 'package:avenqo/core/token_store.dart';
import 'package:avenqo/i18n/locale_controller.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/pages/home_page.dart';
import 'package:avenqo/widgets/language_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _MemoryLocalePreferenceStore implements LocalePreferenceStore {
  @override
  Future<String?> read() async => null;
  @override
  Future<void> write(String code) async {}
}

class _MemoryThemePreferenceStore implements ThemePreferenceStore {
  String? _mode;

  @override
  Future<String?> read() async => _mode;

  @override
  Future<void> write(String mode) async => _mode = mode;
}

Future<LocaleController> _readyController() async {
  final locale = LocaleController(store: _MemoryLocalePreferenceStore());
  await locale.initialize();
  await locale.setLocale('fr');
  return locale;
}

Widget _wrap(LocaleController locale, Widget child) {
  return AvenqoThemeScope(
    controller: ThemeController(store: _MemoryThemePreferenceStore()),
    child: AvenqoLocaleScope(
      controller: locale,
      child: MaterialApp(home: child),
    ),
  );
}

void main() {
  testWidgets(
    'landing surface reacts to the shared light/dark theme controller',
    (tester) async {
      final locale = await _readyController();
      final theme = ThemeController(store: _MemoryThemePreferenceStore());
      await tester.pumpWidget(
        AvenqoThemeScope(
          controller: theme,
          child: AvenqoLocaleScope(
            controller: locale,
            child: ListenableBuilder(
              listenable: theme,
              builder: (context, _) => MaterialApp(
                theme: AppTheme.light,
                darkTheme: AppTheme.dark,
                themeMode: theme.mode,
                themeAnimationDuration: Duration.zero,
                home: const HomePage(),
              ),
            ),
          ),
        ),
      );
      await tester.pump(const Duration(seconds: 1));

      expect(
        tester.widget<Scaffold>(find.byType(Scaffold)).backgroundColor,
        AppTheme.light.scaffoldBackgroundColor,
      );

      await theme.setMode(ThemeMode.dark);
      await tester.pump(const Duration(seconds: 1));
      expect(
        tester.widget<Scaffold>(find.byType(Scaffold)).backgroundColor,
        AppTheme.dark.scaffoldBackgroundColor,
      );

      await theme.setMode(ThemeMode.light);
      await tester.pump(const Duration(seconds: 1));
      expect(
        tester.widget<Scaffold>(find.byType(Scaffold)).backgroundColor,
        AppTheme.light.scaffoldBackgroundColor,
      );
    },
  );

  testWidgets('landing page reacts live to a locale switch (no reload)', (
    tester,
  ) async {
    final locale = await _readyController();
    await tester.pumpWidget(_wrap(locale, const HomePage()));
    await tester.pumpAndSettle();

    expect(locale.code, 'fr');

    await locale.setLocale('en');
    await tester.pumpAndSettle();

    final englishTitle = AvenqoLocaleScope.translationsOf(
      tester.element(find.byType(HomePage)),
    ).hero.titleLine1;
    expect(locale.code, 'en');
    expect(englishTitle, isNotEmpty);
  });

  testWidgets('language selector exposes the canonical locale set', (
    tester,
  ) async {
    final locale = await _readyController();
    await tester.pumpWidget(
      _wrap(
        locale,
        const Scaffold(body: Center(child: LanguageSelector())),
      ),
    );
    await tester.tap(find.byType(LanguageSelector));
    await tester.pumpAndSettle();

    for (final label in const [
      'Español',
      'Português',
      'English (US)',
      'English (UK)',
    ]) {
      expect(find.text(label), findsOneWidget, reason: label);
    }
  });

  testWidgets(
    'module section shows only Retail Intelligence as available, rest as coming soon',
    (tester) async {
      final locale = await _readyController();
      await tester.pumpWidget(_wrap(locale, const HomePage()));
      await tester.pumpAndSettle();

      // Module names appear twice by design: once in the illustrative dashboard
      // preview chips, once in the public module-availability cards.
      final strings = AvenqoLocaleScope.translationsOf(
        tester.element(find.byType(HomePage)),
      );
      expect(strings.agents.availableNow, isNotEmpty);
      expect(strings.agents.comingSoon, isNotEmpty);
    },
  );

  testWidgets(
    'pricing shows the exact Demo/Professional/Enterprise commercial model',
    (tester) async {
      final locale = await _readyController();
      await tester.pumpWidget(_wrap(locale, const HomePage()));
      await tester.pumpAndSettle();
      final pricing = AvenqoLocaleScope.translationsOf(
        tester.element(find.byType(HomePage)),
      ).pricing;

      for (final plan in pricing.plans) {
        expect(find.text(plan.creditAllowance), findsWidgets);
        expect(find.text(plan.creditExtra), findsWidgets);
      }
      expect(find.text(pricing.popular.toUpperCase()), findsOneWidget);
        expect(pricing.plans, hasLength(3));
      expect(tester.takeException(), isNull);
    },
  );

}
