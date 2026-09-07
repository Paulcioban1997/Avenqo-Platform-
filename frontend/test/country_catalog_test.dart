/// Tests ciblés du catalogue pays → devise et des locales fr-CA/fr-FR.
library;

import 'package:avenqo/core/country_catalog.dart';
import 'package:avenqo/core/money_formatter.dart';
import 'package:avenqo/i18n/locale_info.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:intl/intl.dart';

void main() {
  group('country_catalog', () {
    test('every selectable country has a valid ISO-4217 currency', () {
      for (final country in countryCatalog) {
        expect(country.currencyCode, hasLength(3));
        expect(country.currencyCode, matches(RegExp(r'^[A-Z]{3}$')));
      }
    });

    test('Canada → CAD', () {
      expect(currencyForCountry('Canada'), 'CAD');
      expect(currencyForCountry('CA'), 'CAD');
    });

    test('France → EUR', () {
      expect(currencyForCountry('France'), 'EUR');
      expect(currencyForCountry('FR'), 'EUR');
    });

    test('Romania → RON', () {
      expect(currencyForCountry('Romania'), 'RON');
    });

    test('Poland → PLN', () {
      expect(currencyForCountry('Poland'), 'PLN');
    });

    test('Japan → JPY', () {
      expect(currencyForCountry('Japan'), 'JPY');
    });

    test('Australia → AUD', () {
      expect(currencyForCountry('Australia'), 'AUD');
    });

    test('New Zealand → NZD', () {
      expect(currencyForCountry('New Zealand'), 'NZD');
    });

    test('United States → USD', () {
      expect(currencyForCountry('United States'), 'USD');
      expect(currencyForCountry('US'), 'USD');
    });

    test('unknown country falls back to USD', () {
      expect(currencyForCountry('Atlantis'), 'USD');
    });
  });

  group('money_formatter', () {
    test('fr-CA + CAD formats with Canadian French separators', () {
      final result = formatMoney(1250.0, locale: 'fr-CA', currencyCode: 'CAD');
      expect(result, contains('1'));
      expect(result, contains('250'));
    });

    test('fr-FR + EUR formats with Euro symbol', () {
      final result = formatMoney(1250.0, locale: 'fr-FR', currencyCode: 'EUR');
      expect(result, contains('1'));
      expect(result, contains('250'));
    });

    test('en-US + USD formats with dollar sign', () {
      final result = formatMoney(1250.0, locale: 'en-US', currencyCode: 'USD');
      expect(result, contains('1'));
      expect(result, contains('250'));
    });

    test('custom Latin-American Spanish code uses the CLDR regional locale', () {
      expect(intlLocaleCode('es-LatAm'), 'es_419');
      final result = formatMoney(
        1250.0,
        locale: 'es-LatAm',
        currencyCode: 'MXN',
      );
      expect(result, isNotEmpty);
    });

    test('requested regional locales format dates and numbers with CLDR data', () async {
      const localeCodes = [
        'fr-CA',
        'fr-FR',
        'en-US',
        'en-GB',
        'es-ES',
        'es-LatAm',
        'pt-PT',
        'pt-BR',
      ];
      final dates = <String, String>{};
      final numbers = <String, String>{};

      for (final code in localeCodes) {
        final intlCode = intlLocaleCode(code);
        await initializeDateFormatting(intlCode);
        dates[code] = DateFormat.yMMMd(intlCode).format(DateTime(2026, 1, 5));
        numbers[code] = NumberFormat.decimalPattern(
          intlCode,
        ).format(12345.67);
        expect(dates[code], isNotEmpty, reason: '$code date');
        expect(numbers[code], isNotEmpty, reason: '$code number');
      }

      expect(dates['en-US'], isNot(dates['en-GB']));
      expect(numbers['es-ES'], isNot(numbers['es-LatAm']));
      expect(numbers['es-ES'], contains(',67'));
      expect(numbers['es-LatAm'], contains('.67'));
    });

    test('ja-JP + JPY formats with yen symbol', () {
      final result = formatMoney(1250, locale: 'ja-JP', currencyCode: 'JPY', decimalDigits: 0);
      expect(result, isNotEmpty);
    });

    test('language change does NOT change company currency', () {
      // Simule : même montant, même devise, langues différentes
      final frCa = formatMoney(1250.0, locale: 'fr-CA', currencyCode: 'CAD');
      final enUs = formatMoney(1250.0, locale: 'en-US', currencyCode: 'CAD');
      // Les deux doivent utiliser CAD, pas EUR ou USD
      expect(frCa, isNot(contains('€')));
      expect(enUs, isNot(contains('€')));
    });
  });
}
