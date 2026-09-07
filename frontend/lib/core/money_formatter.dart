import 'package:intl/intl.dart';

import 'package:avenqo/i18n/locale_info.dart';

/// Formatter monétaire global unique Avenqo.
///
/// - `locale`  : locale de l'utilisateur (formatage : séparateurs, position symbole).
/// - `currencyCode` : devise ISO-4217 de l'ENTREPRISE (ex. CAD) — jamais déduite
///   de la langue.
///
/// Aucun écran ne concatène manuellement € / $ / USD / CAD. Aucune conversion
/// FX n'est effectuée ici : le montant est affiché tel quel dans la devise
/// fournie.
String formatMoney(
  num amount, {
  required String locale,
  required String currencyCode,
  int decimalDigits = 2,
}) {
  final formatter = NumberFormat.currency(
    locale: intlLocaleCode(locale),
    name: currencyCode,
    decimalDigits: decimalDigits,
  );
  return formatter.format(amount);
}
