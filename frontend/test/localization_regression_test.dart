import 'package:avenqo/app/theme_controller.dart';
import 'package:avenqo/app/theme_scope.dart';
import 'package:avenqo/app/app_theme.dart';
import 'package:avenqo/core/token_store.dart';
import 'package:avenqo/i18n/locale_controller.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/pages/home_page.dart';
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

    expect(find.textContaining('Toute votre entreprise.'), findsOneWidget);
    expect(find.textContaining('Your whole business.'), findsNothing);

    await locale.setLocale('en');
    await tester.pumpAndSettle();

    expect(find.textContaining('Your whole business.'), findsOneWidget);
    expect(find.textContaining('Toute votre entreprise.'), findsNothing);
  });

  testWidgets(
    'module section shows only Retail Intelligence as available, rest as coming soon',
    (tester) async {
      final locale = await _readyController();
      await tester.pumpWidget(_wrap(locale, const HomePage()));
      await tester.pumpAndSettle();

      // Module names appear twice by design: once in the illustrative dashboard
      // preview chips, once in the public module-availability cards.
      expect(find.text('Retail Intelligence'), findsNWidgets(2));
      expect(find.text('Disponible maintenant'), findsOneWidget);
      expect(find.text('CRM AI'), findsNWidgets(2));
      expect(find.text('OCR AI'), findsNWidgets(2));
      expect(find.text('Voice AI'), findsNWidgets(2));
      expect(find.text('Media AI'), findsNWidgets(2));
      expect(find.text('Accounting AI'), findsNWidgets(2));
      expect(find.text('Legal AI'), findsNWidgets(2));
      expect(find.text('Bientôt disponible'), findsNWidgets(6));
      expect(find.text('Découvrir'), findsOneWidget);
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

      expect(find.text('DEMO'), findsOneWidget);
      expect(find.text('PROFESSIONAL'), findsOneWidget);
      expect(find.text('ENTERPRISE'), findsOneWidget);
      expect(find.text('ESSENTIEL'), findsNothing);
      expect(find.text('ESSENTIAL'), findsNothing);
      expect(find.text('Essayer gratuitement'), findsNothing);
      expect(find.text('Sans carte bancaire'), findsNothing);
      expect(find.textContaining(r'$29'), findsNothing);
      expect(find.textContaining(r'$99'), findsNothing);
      expect(find.textContaining(r'$299'), findsNothing);
      expect(find.text(r'$28 USD / mois'), findsOneWidget);
      expect(find.text(r'$49 USD / mois'), findsOneWidget);
      expect(find.text(r'$$28 USD / mois'), findsNothing);
      expect(find.text(r'$$49 USD / mois'), findsNothing);
      for (final plan in pricing.plans) {
        expect(find.text(plan.creditAllowance), findsOneWidget);
        expect(find.text(plan.creditExtra), findsOneWidget);
      }
      expect(find.text(pricing.popular.toUpperCase()), findsOneWidget);
      final demoPriceY = tester.getTopLeft(find.text(r'$28 USD / mois')).dy;
      final demoAllowanceY = tester
          .getTopLeft(find.text(pricing.plans.first.creditAllowance))
          .dy;
      final demoExtraY = tester
          .getTopLeft(find.text(pricing.plans.first.creditExtra))
          .dy;
      final demoFeatureY = tester
          .getTopLeft(find.text(pricing.plans.first.items[1]))
          .dy;
      expect(demoAllowanceY, greaterThan(demoPriceY));
      expect(demoExtraY, greaterThan(demoAllowanceY));
      expect(demoExtraY, lessThan(demoFeatureY));
      expect(find.text('Contacter les ventes'), findsNWidgets(2));
      expect(tester.takeException(), isNull);
    },
  );

}
