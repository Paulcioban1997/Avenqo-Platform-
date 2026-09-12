import 'dart:async';
// dart:html est l'API stable supportée pour Flutter Web (le passage à
// package:web pourra se faire plus tard sans changer l'interface publique).
// ignore: avoid_web_libraries_in_flutter, deprecated_member_use
import 'dart:html' as html;
import 'dart:typed_data';

import 'picked_file.dart';

/// Implémentation Flutter Web 100% native : `<input type="file">` créé et
/// cliqué SYNCHRONEMENT dans le geste utilisateur (crucial : les navigateurs
/// rejettent l'ouverture du file dialog si le geste a été perdu par un await
/// ou une opération intermédiaire).
///
/// - multiple = true
/// - accept = .csv,.xlsx,.json,.parquet
/// - annulation → liste vide (jamais de crash, jamais de future pendante)
/// - lecture en bytes (FileReader.readAsArrayBuffer) — jamais File.path.
Future<List<PickedFile>> pickDataFiles() async {
  final input = html.FileUploadInputElement()
    ..multiple = true
    ..accept = '.csv,.xlsx,.json,.parquet';

  final completer = Completer<List<PickedFile>>();

  input.onChange.first.then((_) async {
    final files = <PickedFile>[];
    for (final file in input.files ?? const <html.File>[]) {
      files.add(PickedFile(file.name, await _readAsBytes(file)));
    }
    if (!completer.isCompleted) {
      completer.complete(files);
    }
  });

  // Annulation : le navigateur ne fire pas onChange quand l'utilisateur ferme
  // le dialogue sans choisir. La fenêtre reprend alors le focus — on résout
  // avec une liste vide après un court délai pour laisser onChange gagner
  // s'il a réellement été émis.
  html.window.onFocus.first.then((_) {
    Timer(const Duration(milliseconds: 400), () {
      if (!completer.isCompleted) {
        completer.complete(const <PickedFile>[]);
      }
    });
  });

  input.click();
  return completer.future;
}

Future<Uint8List> _readAsBytes(html.File file) {
  final reader = html.FileReader();
  final completer = Completer<Uint8List>();
  reader.onLoad.first.then((_) {
    completer.complete(reader.result as Uint8List);
  });
  reader.onError.first.then((_) {
    completer.completeError(StateError('file_read_failed'));
  });
  reader.readAsArrayBuffer(file);
  return completer.future;
}

Future<void> saveExportFile(String fileName, Uint8List bytes) async {
  String mimeType = 'application/octet-stream';
  final lower = fileName.toLowerCase();
  if (lower.endsWith('.csv')) {
    mimeType = 'text/csv;charset=utf-8';
  } else if (lower.endsWith('.xlsx')) {
    mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
  } else if (lower.endsWith('.pdf')) {
    mimeType = 'application/pdf';
  } else if (lower.endsWith('.docx')) {
    mimeType = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
  }

  final blob = html.Blob([bytes], mimeType);
  final url = html.Url.createObjectUrlFromBlob(blob);
  final anchor = html.AnchorElement(href: url)
    ..setAttribute('download', fileName)
    ..style.display = 'none';

  html.document.body?.children.add(anchor);
  anchor.click();

  Timer(const Duration(seconds: 15), () {
    anchor.remove();
    html.Url.revokeObjectUrl(url);
  });
}
