// ignore_for_file: deprecated_member_use, avoid_web_libraries_in_flutter
// dart:html est requis pour le file picker natif Web fiable (input type=file).
// Import conditionnel : cette lib n'existe que sur Flutter Web.

import 'dart:async';

import 'package:avenqo/pages/connections_page.dart';

import 'web_file_picker_stub.dart'
    if (dart.library.html) 'web_file_picker_web.dart' as impl;

/// Sélecteur de fichiers natif pour Flutter Web — utilise `<input type="file">`
/// déclenché immédiatement dans le handler de clic utilisateur.
///
/// Contrainte navigateur : le file picker DOIT être invoqué dans le contexte
/// du geste utilisateur (clic). Aucun `await` réseau/dialog/navigation avant
/// l'invocation, sinon le navigateur rejette l'ouverture.
class WebFilePicker {
  /// Ouvre immédiatement le sélecteur natif et retourne les fichiers choisis.
  ///
  /// - `accept` : extensions MIME/EXT (ex. `.csv,.xlsx,.json,.parquet`)
  /// - `multiple` : sélection multiple autorisée
  static Future<List<PickedFile>> pick({
    required String accept,
    bool multiple = true,
  }) =>
      impl.pick(accept: accept, multiple: multiple);
}
