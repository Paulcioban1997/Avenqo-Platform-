// ignore_for_file: deprecated_member_use, avoid_web_libraries_in_flutter
// Implémentation Web réelle — dart:html requis pour input type=file natif.

import 'dart:async';
import 'dart:html' as html;
import 'dart:typed_data';

import 'package:avenqo/pages/connections_page.dart';

/// Ouvre immédiatement le sélecteur natif et retourne les fichiers choisis.
Future<List<PickedFile>> pick({required String accept, bool multiple = true}) {
  final completer = Completer<List<PickedFile>>();
  final input = html.FileUploadInputElement()
    ..accept = accept
    ..multiple = multiple;

  // Déclenchement immédiat dans le contexte du clic — pas d'await avant.
  input.click();

  input.onChange.listen((_) async {
    final files = <PickedFile>[];
    for (final file in input.files ?? []) {
      final bytes = await _readFileAsBytes(file);
      files.add(PickedFile(file.name, bytes));
    }
    input.remove();
    completer.complete(files);
  });

  input.onAbort.listen((_) {
    input.remove();
    if (!completer.isCompleted) completer.complete(<PickedFile>[]);
  });

  Timer(const Duration(minutes: 5), () {
    input.remove();
    if (!completer.isCompleted) completer.complete(<PickedFile>[]);
  });

  return completer.future;
}

Future<Uint8List> _readFileAsBytes(html.File file) {
  final reader = html.FileReader();
  final completer = Completer<Uint8List>();
  reader.onLoad.listen((_) {
    final result = reader.result;
    if (result is Uint8List) {
      completer.complete(result);
    } else if (result is List<int>) {
      completer.complete(Uint8List.fromList(result));
    } else {
      completer.complete(Uint8List(0));
    }
  });
  reader.onError.listen((_) => completer.complete(Uint8List(0)));
  reader.readAsArrayBuffer(file);
  return completer.future;
}
