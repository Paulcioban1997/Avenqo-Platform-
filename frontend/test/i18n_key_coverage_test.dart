// Dedicated release-gate test (AVENQO localization directive Part A1).
//
// Protects the 42-locale i18n catalog against silent regressions: it fails
// the normal `flutter test` suite if a future developer adds a key to
// en.json but forgets another locale, removes a locale from _locales.json,
// or breaks `Translations.fromJson` parsing for any locale file.
import 'dart:convert';
import 'dart:io';

import 'package:avenqo/agents/agent_registry.dart';
import 'package:avenqo/i18n/translations.dart';
import 'package:flutter_test/flutter_test.dart';

const List<String> kExpectedLocaleCodes = [
  'fr-CA', 'fr-FR', 'en', 'es', 'pt', 'ro', 'de', 'it', 'nl', 'pl', 'ru', 'uk',
  'el', 'sv', 'tr', 'cs', 'ka', 'hy', 'ar', 'ar-EG', 'he', 'fa', 'sw', 'am',
  'af', 'ha', 'zh', 'ja', 'ko', 'hi', 'bn', 'ur', 'ta', 'pa', 'ne', 'vi',
  'th', 'id', 'ms', 'tl', 'my', 'km', 'mn',
];

/// Locale legacy conservée sur disque comme alias backward-compatible pour les
/// utilisateurs existants ayant `fr` persisté (migrée vers fr-CA à la lecture
/// via LocaleController) — jamais exposée comme option visible du sélecteur.
const List<String> kLegacyAliasLocaleCodes = ['fr'];

/// Set of top-level sections that must never silently fall back to English
/// via `Translations.fromJson`'s `json['x'] != null ? ... : Fallback()`
/// pattern — every one of the 42 locales must genuinely define them.
const List<String> kFallbackProneSections = [
  'assistant', 'auth', 'dashboardHome', 'admin', 'onboarding', 'company', 'agents',
];

Set<String> _leafKeyPaths(dynamic node, [String prefix = '']) {
  final paths = <String>{};
  if (node is Map<String, dynamic>) {
    for (final entry in node.entries) {
      final path = prefix.isEmpty ? entry.key : '$prefix.${entry.key}';
      paths.addAll(_leafKeyPaths(entry.value, path));
    }
  } else {
    paths.add(prefix);
  }
  return paths;
}

Map<String, dynamic> _readLocaleJson(String code) {
  final file = File('assets/i18n/$code.json');
  return jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
}

final RegExp _errorPageContamination = RegExp(
  r'error\s*500|server error|404\s*not found|that(?:\x27|’|â€™)s an error|please try again later|<html|<!doctype',
  caseSensitive: false,
);

void main() {
  final localesCatalog =
      jsonDecode(File('assets/i18n/_locales.json').readAsStringSync()) as List<dynamic>;
  final registeredCodes =
      localesCatalog.map((e) => (e as Map<String, dynamic>)['code'] as String).toList();

  test('exactly the 43 expected locales are registered in _locales.json', () {
    expect(registeredCodes.toSet(), equals(kExpectedLocaleCodes.toSet()));
    expect(registeredCodes.length, 43);
    // Le legacy `fr` ne doit JAMAIS apparaître comme option visible.
    expect(registeredCodes, isNot(contains('fr')));
    expect(registeredCodes, containsAll(['fr-CA', 'fr-FR']));
  });

  test('no stale/unsupported locale file is accidentally exposed', () {
    final onDisk = Directory('assets/i18n')
        .listSync()
        .whereType<File>()
        .map((f) => f.uri.pathSegments.last)
        .where((name) => name.endsWith('.json') && name != '_locales.json')
        .map((name) => name.substring(0, name.length - '.json'.length))
        .toSet();
    final expectedOnDisk = {...kExpectedLocaleCodes, ...kLegacyAliasLocaleCodes};
    expect(onDisk, equals(expectedOnDisk));
  });

  final enLeaves = _leafKeyPaths(_readLocaleJson('en'));
  final englishAgents = _readLocaleJson('en')['agents'] as Map<String, dynamic>;

  test('en.json (reference catalog) has at least one leaf key', () {
    expect(enLeaves, isNotEmpty);
  });

  for (final code in kExpectedLocaleCodes) {
    test('$code.json has 100% key parity with en.json (no missing/extra keys)', () {
      final json = _readLocaleJson(code);
      final leaves = _leafKeyPaths(json);
      final missing = enLeaves.difference(leaves);
      final extra = leaves.difference(enLeaves);
      expect(missing, isEmpty, reason: 'Locale "$code" is missing keys: $missing');
      expect(extra, isEmpty, reason: 'Locale "$code" has unexpected extra keys: $extra');
    });

    test('$code.json defines every fallback-prone section directly (no silent English fallback)', () {
      final json = _readLocaleJson(code);
      for (final section in kFallbackProneSections) {
        expect(
          json[section],
          isNotNull,
          reason: 'Locale "$code" is missing top-level section "$section" and would '
              'silently fall back to English via Translations.fromJson.',
        );
      }
    });

    test('$code.json parses cleanly through Translations.fromJson', () {
      final json = _readLocaleJson(code);
      expect(() => Translations.fromJson(json), returnsNormally);
    });
  }

  test('French Agent catalog is translated and includes the approved Marketing copy', () {
    for (final code in ['fr', 'fr-CA', 'fr-FR']) {
      final agents = _readLocaleJson(code)['agents'] as Map<String, dynamic>;
      expect(
        agents['marketingDescription'],
        'Préparez vos campagnes, vos audiences et vos actions de croissance mesurables.',
      );
      for (final key in [
        'subtitle',
        'adminTitle',
        'adminSubtitle',
        'availableCount',
        'marketingDescription',
        'hrDescription',
        'appointmentsDescription',
        'workflowDescription',
      ]) {
        expect(agents[key], isNot(englishAgents[key]), reason: '$code agents.$key is still English');
      }
    }
  });

  test('all 44 Agent catalogs are complete and free of HTTP error-page contamination', () {
    final requiredKeys = <String>{
      'navLabel',
      'title',
      'subtitle',
      'availableNow',
      'comingSoon',
      'openAgent',
      'adminTitle',
      'adminSubtitle',
      'availableCount',
      'comingSoonCount',
      'retailOverviewLabel',
      'retailSalesLabel',
      'retailCustomersLabel',
      'retailProductsLabel',
      'retailRecommendationsLabel',
      for (final agent in avenqoAgentRegistry) agent.nameKey,
      for (final agent in avenqoAgentRegistry) agent.descriptionKey,
    };
    for (final code in [...kExpectedLocaleCodes, ...kLegacyAliasLocaleCodes]) {
      final agents = _readLocaleJson(code)['agents'] as Map<String, dynamic>;
      for (final key in requiredKeys) {
        final value = agents[key]?.toString().trim() ?? '';
        expect(value, isNotEmpty, reason: '$code agents.$key is empty or missing');
        expect(
          _errorPageContamination.hasMatch(value),
          isFalse,
          reason: '$code agents.$key contains HTTP/error-page content',
        );
      }
      for (final entry in agents.entries) {
        expect(
          _errorPageContamination.hasMatch(entry.value.toString()),
          isFalse,
          reason: '$code agents.${entry.key} contains HTTP/error-page content',
        );
      }
    }
  });
}
