import 'package:file_picker/file_picker.dart';

import 'picked_file.dart';

/// Formats acceptés par le pipeline d'ingestion universel côté backend
/// (`CompanyDatasetLoader` : CSV/XLSX/JSON/Parquet).
const acceptedDataFileExtensions = ['csv', 'xlsx', 'json', 'parquet'];

/// Implémentation mobile/desktop via le plugin `file_picker`.
/// (Sur Flutter Web, l'implémentation native `app_file_picker_web.dart`
/// est utilisée à la place via l'import conditionnel.)
Future<List<PickedFile>> pickDataFiles() async {
  // L'appel DOIT rester synchrone avec le geste utilisateur (pas d'await avant).
  final result = await FilePicker.pickFiles(
    type: FileType.custom,
    allowedExtensions: acceptedDataFileExtensions,
    // ignore: deprecated_member_use — API multi-fichiers correcte pour v12.
    allowMultiple: true,
  );
  final files = <PickedFile>[];
  for (final platformFile in result) {
    files.add(PickedFile(platformFile.name, await platformFile.readAsBytes()));
  }
  return files;
}
