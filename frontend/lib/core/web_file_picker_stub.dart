import 'package:avenqo/pages/connections_page.dart';

/// Stub pour les plateformes non-Web (tests VM, mobile, desktop).
/// Le vrai picker Web est dans `web_file_picker_web.dart` (dart:html).
Future<List<PickedFile>> pick({required String accept, bool multiple = true}) =>
    throw UnsupportedError('WebFilePicker is only available on Flutter Web');
