import 'dart:typed_data';

/// Fichier choisi par l'utilisateur, découplé de `PlatformFile` (classe `base`
/// non sous-classable hors de son package) afin de rester injectable en test.
/// Partagé par l'implémentation file_picker (mobile/desktop) et l'implémentation
/// Web native (`<input type="file">`).
class PickedFile {
  const PickedFile(this.name, this.bytes);

  final String name;
  final Uint8List bytes;
}
