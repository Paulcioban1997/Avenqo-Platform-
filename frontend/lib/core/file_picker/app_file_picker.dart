/// Point d'entrée unique du sélecteur de fichiers Avenqo.
///
/// Import conditionnel : `file_picker` (plugin) sur mobile/desktop, et un
/// `<input type="file">` natif sur Flutter Web — le plugin reste peu fiable
/// en production Web, alors que l'input natif ouvre le dialogue du navigateur
/// à tous les coups dans le geste utilisateur.
library;

export 'picked_file.dart';
export 'app_file_picker_stub.dart'
    if (dart.library.html) 'app_file_picker_web.dart';
