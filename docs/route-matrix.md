# Matrice des routes Avenqo (rôles × accès)

Basée sur les routes réelles définies dans
`frontend/lib/app/avenqo_app.dart` et protégées côté backend par
`require_platform_admin` (`backend/app/dependencies/auth.py`).

| Route                     | Anonyme | Client (tenant) | Platform Admin |
|---------------------------|:-------:|:----------------:|:---------------:|
| `/`                       | ✅       | ✅                | ✅               |
| `/pricing`                | ✅       | ✅                | ✅               |
| `/login`                  | ✅       | ✅ (redirigé)     | ✅ (redirigé)    |
| `/register`               | ✅       | ✅ (redirigé)     | ✅ (redirigé)    |
| `/forgot-password`        | ✅       | ✅                | ✅               |
| `/verify-email`           | ✅       | ✅                | ✅               |
| `/reset-password`         | ✅       | ✅                | ✅               |
| `/dashboard`              | ❌ → `/login` | ✅          | ✅ (accès manuel possible) |
| `/assistant` (Business Copilot) | ❌ → `/login` | ✅    | ✅               |
| `/sales`, `/customers`, `/products`, `/recommendations`, `/alerts`, `/reports`, `/connections` | ❌ → `/login` | ✅ | ✅ |
| `/team`                   | ❌ → `/login` | ✅          | ✅               |
| `/billing`                | ❌ → `/login` | ✅ (droits selon rôle tenant) | ✅ |
| `/settings`               | ❌ → `/login` | ✅          | ✅               |
| `/support` (Avenqo Support AI) | ❌ → `/login` | ✅    | ✅               |
| `/admin`                  | ❌ → `/login` | ❌ → `/dashboard` | ✅ |
| `/admin/companies`        | ❌ → `/login` | ❌ → `/dashboard` | ✅ |
| `/admin/companies/:id`    | ❌ → `/login` | ❌ → `/dashboard` | ✅ |
| `/admin/audit-log`        | ❌ → `/login` | ❌ → `/dashboard` | ✅ |

## Notes

- La redirection frontend (`redirect()` dans `avenqo_app.dart`) est une
  défense en profondeur : elle évite d'afficher l'écran, mais n'est jamais la
  seule protection.
- Le backend refuse indépendamment tout accès `/api/v1/admin/*` sans
  `is_platform_admin=true` via `require_platform_admin` → `403`.
- Un client authentifié qui accède manuellement à `/admin` (URL directe) est
  redirigé vers `/dashboard` sans qu'aucune donnée admin ne soit chargée.
- Un Platform Admin conserve l'accès à son propre workspace client
  (`/dashboard`, etc.) — il peut naviguer entre les deux espaces via le
  bouton « Retour à mon espace » (AdminShell) ou l'entrée « Avenqo Admin »
  (AppShell, visible uniquement si `isPlatformAdmin == true`).
