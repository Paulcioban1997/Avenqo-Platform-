# Bascule Sandbox vers `avenqo_app` — procédure, non exécutée

Cette procédure prépare le LOGIN du rôle applicatif `avenqo_app` sur **Sandbox uniquement**. Elle n’est **pas** une autorisation d’exécution. Production, DNS, Stripe et Telnyx restent hors périmètre.

État actuel (2026-10-14) : Alembic 0058 crée `avenqo_app` / `avenqo_migrate` / `avenqo_owner` en **NOLOGIN**. 0060 ajoute FORCE RLS sur les tables métier restantes. Tant que l’API se connecte en propriétaire de tables, RLS est inerte.

## Interdits

- Ne pas appliquer cette procédure sans GO explicite du propriétaire, environnement `sandbox` nommé.
- Ne pas pointer Production (`api.avenqo.ca`) vers `avenqo_app`.
- Ne pas réécrire `DATABASE_URL` Railway avant les tests d’authentification verts.
- Ne pas imprimer, committer ou coller le mot de passe du rôle.
- Ne pas `DROP DATABASE`, ne pas recréer le volume Sandbox, ne pas force-push.

## Pré-requis

1. PR #61 (ou successeur) fusionnée dans `promotion/sandbox` **après GO**, API Sandbox déployée sur cette révision.
2. Alembic head `0060_rls_remaining_tenant_tables` déjà appliquée sur une **copie** isolée, puis seulement sur Sandbox après GO migration.
3. Répétition locale verte : `python scripts/rehearse_rls_0060_isolated.py` et `python scripts/rehearse_app_role_cutover.py` (localhost seulement).
4. Sauvegarde PostgreSQL Sandbox **vérifiée** (pg_dump + restore isolée + comptages), hors de ce dépôt.

## Sauvegarde vérifiée (avant tout LOGIN)

1. Fenêtre de maintenance courte ; figer les workers de sync commerce si possible.
2. `pg_dump` format custom, checksum, copie hors volume Railway.
3. Restaurer le dump sur PostgreSQL **localhost** `rotation_test_*`.
4. Comparer : `alembic_version`, nombre de `companies`, `users`, `ai_conversations`, politiques RLS (`relrowsecurity`, `relforcerowsecurity`).
5. Échec de restauration = **stop**. Ne pas activer LOGIN.

## Ordre d’exécution (après GO Sandbox)

1. Dry-run : `python scripts/enable_sandbox_app_role_login.py`  
   Attendu : `app_can_login=false`, `database_url_unchanged=true`.
2. Mot de passe du rôle dans un secret Railway **nouveau**, jamais dans Git. Longueur ≥ 24.
3. Activer LOGIN seulement :  
   `python scripts/enable_sandbox_app_role_login.py --apply --confirm-environment sandbox`  
   `DATABASE_URL` de l’API **n’est pas** modifié à cette étape.
4. Tester une connexion ponctuelle `avenqo_app` depuis un jump localhost (tunnel), pas depuis le laptop perso vers l’URL publique si elle n’est pas déjà le mode opératoire habituel.
5. Vérifier `/api/v1/health` et `/api/v1/ready` **avant** le changement de `DATABASE_URL`.
6. Pointer l’API Sandbox vers `avenqo_app` (variable Railway), redéployer **un** replica.
7. Tests d’authentification (ci-dessous). Tout 5xx ou refus de login légitime = rollback immédiat.
8. Worker / migrateur : `avenqo_migrate` pour Alembic uniquement ; l’API ne doit jamais être `avenqo_migrate`.

## Tests d’authentification (Sandbox, après bascule)

À exécuter sur l’API Sandbox, comptes de test, **pas** Production :

| # | Contrôle | Attendu |
|---|---|---|
| A | `POST /api/v1/auth/login` compte Sandbox connu | 200, cookie `avenqo_access_token` |
| B | `GET /api/v1/auth/me` | 200, `company_id` du compte |
| C | Login mot de passe faux | 401 |
| D | Ancien JWT si rotation de secret concomitante | 401 |
| E | Lecture CRM/Retail entreprise A | 200, données A |
| F | Même jeton, ressource entreprise B | 404/403, jamais le corps B |
| G | `GET /api/v1/health` et `/ready` | 200, `environment=sandbox` |
| H | Worker migrateur `alembic current` | head 0060, pas d’erreur de droit |

## Rollback

1. Remettre `DATABASE_URL` API sur le rôle propriétaire **actuel** (celui qui marche aujourd’hui), redéployer.
2. `ALTER ROLE avenqo_app NOLOGIN` (mot de passe invalidé). L’API ne doit plus pouvoir ouvrir de session avec ce rôle.
3. Si données corrompues : restaurer le dump vérifié sur **copie**, comparer, puis seulement GO restore Sandbox (opération destructrice séparée, hors de cette PR).
4. Ne pas downgrade Alembic 0060 en urgence : `NO FORCE` élargit la visibilité. Préférer revenir au login propriétaire.

## Preuves à consigner (sans secrets)

- Horodatage dump + checksum + résultat restore isolée.
- `roles_constrained=true`, `app_can_login` avant/après.
- Codes HTTP des tests A–H.
- Confirmation `database_url_unchanged` jusqu’à l’étape 6.

Tant que cette checklist n’est pas signée par le propriétaire, Sandbox reste sur le login actuel et `avenqo_app` reste NOLOGIN.
