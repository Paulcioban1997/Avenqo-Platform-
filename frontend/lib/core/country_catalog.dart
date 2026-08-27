/// Catalogue central pays → devise — source de vérité UNIQUE Flutter.
library;

/// Miroir de backend/app/core/locale_catalog.py (même mapping, même logique).
///
/// Ce mapping fournit uniquement les DEFAULTS suggérés à la création
/// d'organisation : pays → devise officielle ISO-4217.
/// Après création, la devise réellement utilisée est Company.currency_code
/// (jamais déduite de la langue).
///
/// NE JAMAIS utiliser ce catalogue pour convertir des montants (aucun FX inventé).

class CountryDefinition {
  const CountryDefinition({
    required this.countryCode,
    required this.countryName,
    required this.currencyCode,
  });

  final String countryCode; // ISO-3166-1 alpha-2
  final String countryName;
  final String currencyCode; // ISO-4217
}

/// Tous les pays sélectionnables dans l'onboarding Avenqo, avec leur devise
/// officielle ISO-4217. Aligné sur backend/app/core/locale_catalog.py.
const countryCatalog = <CountryDefinition>[
  CountryDefinition(countryCode: 'CA', countryName: 'Canada', currencyCode: 'CAD'),
  CountryDefinition(countryCode: 'US', countryName: 'United States', currencyCode: 'USD'),
  CountryDefinition(countryCode: 'MX', countryName: 'Mexico', currencyCode: 'MXN'),
  CountryDefinition(countryCode: 'ES', countryName: 'Spain', currencyCode: 'EUR'),
  CountryDefinition(countryCode: 'PT', countryName: 'Portugal', currencyCode: 'EUR'),
  CountryDefinition(countryCode: 'FR', countryName: 'France', currencyCode: 'EUR'),
  CountryDefinition(countryCode: 'DE', countryName: 'Germany', currencyCode: 'EUR'),
  CountryDefinition(countryCode: 'IT', countryName: 'Italy', currencyCode: 'EUR'),
  CountryDefinition(countryCode: 'NL', countryName: 'Netherlands', currencyCode: 'EUR'),
  CountryDefinition(countryCode: 'GR', countryName: 'Greece', currencyCode: 'EUR'),
  CountryDefinition(countryCode: 'RO', countryName: 'Romania', currencyCode: 'RON'),
  CountryDefinition(countryCode: 'PL', countryName: 'Poland', currencyCode: 'PLN'),
  CountryDefinition(countryCode: 'CZ', countryName: 'Czech Republic', currencyCode: 'CZK'),
  CountryDefinition(countryCode: 'SE', countryName: 'Sweden', currencyCode: 'SEK'),
  CountryDefinition(countryCode: 'GB', countryName: 'United Kingdom', currencyCode: 'GBP'),
  CountryDefinition(countryCode: 'CH', countryName: 'Switzerland', currencyCode: 'CHF'),
  CountryDefinition(countryCode: 'UA', countryName: 'Ukraine', currencyCode: 'UAH'),
  CountryDefinition(countryCode: 'GE', countryName: 'Georgia', currencyCode: 'GEL'),
  CountryDefinition(countryCode: 'AM', countryName: 'Armenia', currencyCode: 'AMD'),
  CountryDefinition(countryCode: 'TR', countryName: 'Turkey', currencyCode: 'TRY'),
  CountryDefinition(countryCode: 'JP', countryName: 'Japan', currencyCode: 'JPY'),
  CountryDefinition(countryCode: 'CN', countryName: 'China', currencyCode: 'CNY'),
  CountryDefinition(countryCode: 'KR', countryName: 'South Korea', currencyCode: 'KRW'),
  CountryDefinition(countryCode: 'IN', countryName: 'India', currencyCode: 'INR'),
  CountryDefinition(countryCode: 'BD', countryName: 'Bangladesh', currencyCode: 'BDT'),
  CountryDefinition(countryCode: 'PK', countryName: 'Pakistan', currencyCode: 'PKR'),
  CountryDefinition(countryCode: 'NP', countryName: 'Nepal', currencyCode: 'NPR'),
  CountryDefinition(countryCode: 'VN', countryName: 'Vietnam', currencyCode: 'VND'),
  CountryDefinition(countryCode: 'TH', countryName: 'Thailand', currencyCode: 'THB'),
  CountryDefinition(countryCode: 'ID', countryName: 'Indonesia', currencyCode: 'IDR'),
  CountryDefinition(countryCode: 'MY', countryName: 'Malaysia', currencyCode: 'MYR'),
  CountryDefinition(countryCode: 'PH', countryName: 'Philippines', currencyCode: 'PHP'),
  CountryDefinition(countryCode: 'KH', countryName: 'Cambodia', currencyCode: 'KHR'),
  CountryDefinition(countryCode: 'MN', countryName: 'Mongolia', currencyCode: 'MNT'),
  CountryDefinition(countryCode: 'AU', countryName: 'Australia', currencyCode: 'AUD'),
  CountryDefinition(countryCode: 'NZ', countryName: 'New Zealand', currencyCode: 'NZD'),
  CountryDefinition(countryCode: 'EG', countryName: 'Egypt', currencyCode: 'EGP'),
  CountryDefinition(countryCode: 'IL', countryName: 'Israel', currencyCode: 'ILS'),
  CountryDefinition(countryCode: 'MA', countryName: 'Morocco', currencyCode: 'MAD'),
  CountryDefinition(countryCode: 'ZA', countryName: 'South Africa', currencyCode: 'ZAR'),
  CountryDefinition(countryCode: 'KE', countryName: 'Kenya', currencyCode: 'KES'),
  CountryDefinition(countryCode: 'ET', countryName: 'Ethiopia', currencyCode: 'ETB'),
];

/// Fallback technique uniquement quand le pays n'est pas reconnu.
const fallbackCurrencyCode = 'USD';

final _byCode = {for (final c in countryCatalog) c.countryCode.toLowerCase(): c};
final _byName = {for (final c in countryCatalog) c.countryName.toLowerCase(): c};

/// Retourne la devise officielle ISO-4217 pour un pays (code ou nom).
/// Fallback USD si pays inconnu (technique uniquement, jamais un choix métier).
String currencyForCountry(String country) {
  final key = country.trim().toLowerCase();
  return _byCode[key]?.currencyCode ?? _byName[key]?.currencyCode ?? fallbackCurrencyCode;
}

/// Retourne la définition complète d'un pays, ou null si inconnu.
CountryDefinition? countryDefinitionFor(String country) {
  final key = country.trim().toLowerCase();
  return _byCode[key] ?? _byName[key];
}
