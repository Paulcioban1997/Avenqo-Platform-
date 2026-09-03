/// Métadonnées d'une langue disponible — miroir de web/src/lib/i18n/locales.ts.
class LocaleInfo {
  const LocaleInfo({
    required this.code,
    required this.region,
    required this.flag,
    required this.nativeName,
    required this.englishName,
    required this.direction,
  });

  factory LocaleInfo.fromJson(Map<String, dynamic> json) => LocaleInfo(
        code: json['code'] as String,
        region: json['region'] as String,
        flag: json['flag'] as String,
        nativeName: json['nativeName'] as String,
        englishName: json['englishName'] as String,
        direction: json['direction'] as String,
      );

  final String code;
  final String region;
  final String flag;
  final String nativeName;
  final String englishName;
  final String direction;

  bool get isRtl => direction == 'rtl';
}

const String defaultLocaleCode = 'fr-CA';
