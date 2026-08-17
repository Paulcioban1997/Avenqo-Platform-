# Avenqo Flutter

Client unique Flutter/Dart d'Avenqo pour Web, Android, iOS, Windows, macOS et Linux.

## Architecture

- `lib/app`: thème, destinations et routage global.
- `lib/auth`: état et écrans d'authentification.
- `lib/core`: configuration, client HTTP et stockage sécurisé.
- `lib/pages`: widgets des routes métier.
- `lib/widgets`: composants Material partagés et pages dynamiques.

Le client utilise la même API FastAPI sur toutes les plateformes. Le JWT d'accès et le refresh token sont conservés avec `flutter_secure_storage`. Le client renouvelle automatiquement le JWT après une réponse `401`.

## Exécution

```powershell
flutter pub get
flutter analyze
flutter test
flutter run -d chrome --dart-define=API_BASE_URL=http://127.0.0.1:8000/api/v1
```

Pour Android Emulator, utiliser généralement `http://10.0.2.2:8000/api/v1`. Pour un appareil physique, utiliser l'adresse IP locale de la machine backend.

## Routes

Le registre `lib/app/destinations.dart` pilote automatiquement la navigation Material et les widgets de Dashboard, Marketplace, Modules IA, Entreprise, Utilisateurs, Historique IA, Facturation, Paramètres, Documentation, Support, API et Profil.
