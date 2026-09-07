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

Depuis la racine du dépôt, la commande recommandée démarre et vérifie le
backend avant Flutter :

```powershell
.\scripts\start_local.ps1
```

Pour utiliser les comptes et données du sandbox dans l'interface locale :

```powershell
.\scripts\start_local.ps1 -ApiTarget sandbox
```

Pour lancer uniquement le client lorsque l'API écoute déjà sur le port 8000 :

```powershell
flutter pub get
flutter analyze
flutter test
flutter run -d chrome --web-port=8080 --dart-define=API_BASE_URL=http://127.0.0.1:8000/api/v1
```

`--web-port=8080` est requis en développement local : `CORS_ORIGINS` (backend/.env)
autorise explicitement `http://localhost:8080` et `http://127.0.0.1:8080`.
Sans port fixe, Chrome démarre sur un port aléatoire et les appels API échouent
silencieusement (CORS).

Pour Android Emulator, utiliser généralement `http://10.0.2.2:8000/api/v1`. Pour un appareil physique, utiliser l'adresse IP locale de la machine backend.

## Routes

Le registre `lib/app/destinations.dart` pilote automatiquement la navigation Material et les widgets de Dashboard, Marketplace, Modules IA, Entreprise, Utilisateurs, Historique IA, Facturation, Paramètres, Documentation, Support, API et Profil.
