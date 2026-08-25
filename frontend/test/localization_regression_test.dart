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

Future<LocaleController> _readyController() async {
  final locale = LocaleController(store: _MemoryLocalePreferenceStore());
  await locale.initialize();
  await locale.setLocale('fr');
  return locale;
}

void main() {
  testWidgets('landing page reacts live to a locale switch (no reload)', (tester) async {
    final locale = await _readyController();
    await tester.pumpWidget(
      AvenqoLocaleScope(controller: locale, child: const MaterialApp(home: HomePage())),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('Toute votre entreprise.'), findsOneWidget);
    expect(find.textContaining('Your whole business.'), findsNothing);

    await locale.setLocale('en');
    await tester.pumpAndSettle();

    expect(find.textContaining('Your whole business.'), findsOneWidget);
    expect(find.textContaining('Toute votre entreprise.'), findsNothing);
  });

  testWidgets('module section shows only Retail Intelligence as available, rest as coming soon', (tester) async {
    final locale = await _readyController();
    await tester.pumpWidget(
      AvenqoLocaleScope(controller: locale, child: const MaterialApp(home: HomePage())),
    );
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
  });

  testWidgets('pricing shows Demo/Professional/Enterprise only, no Essentiel, no invented prices', (tester) async {
    final locale = await _readyController();
    await tester.pumpWidget(
      AvenqoLocaleScope(controller: locale, child: const MaterialApp(home: HomePage())),
    );
    await tester.pumpAndSettle();

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
    expect(find.text('Tarification à confirmer'), findsNWidgets(2));
    expect(find.text('Contacter les ventes'), findsNWidgets(2));
  });
}
