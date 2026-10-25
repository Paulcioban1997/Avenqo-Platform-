# Bascule Sandbox vers `avenqo_app` — procédure, non exécutée

Cette procédure prépare le LOGIN du rôle applicatif `avenqo_app` sur **Sandbox uniquement**. Elle n’est **pas** une autorisation d’exécution. Production, DNS, Stripe et Telnyx restent hors périmètre.

État actuel (2026-10-14) : Alembic 0058 crée `avenqo_app` / `avenqo_migrate` / `avenqo_owner` en **NOLOGIN**. 0060 ajoute FORCE RLS sur les tables métier restantes. 0061 ajoute des index hot-path tenant (`ai_conversations`, `ai_messages`, `login_events`, `crm_clients`, `auth_sessions`). Tant que l’API se connecte en propriétaire de tables, RLS est inerte.

## Interdits

- Ne pas appliquer cette procédure sans GO explicite du propriétaire, environnement `sandbox` nommé.
- Ne pas pointer Production (`api.avenqo.ca`) vers `avenqo_app`.
- Ne pas réécrire `DATABASE_URL` Railway avant les tests d’authentification verts.
- Ne pas imprimer, committer ou coller le mot de passe du rôle.
- Ne pas `DROP DATABASE`, ne pas recréer le volume Sandbox, ne pas force-push.

## Pré-requis

1. PR #61 (ou successeur) fusionnée dans `promotion/sandbox` **après GO**, API Sandbox déployée sur cette révision.
2. Alembic head `0061_tenant_hotpath_indexes` déjà appliquée sur une **copie** isolée, puis seulement sur Sandbox après GO migration (0060 inclus).
3. Répétition locale verte : `python scripts/rehearse_rls_0060_isolated.py` et `python scripts/rehearse_app_role_cutover.py` (localhost seulement). Rollback NOLOGIN vérifié sur cette copie (`login_disabled_after=true`).
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
| H | Worker migrateur `alembic current` | head `0061b_harden_tenant_rls_no_bypass`, pas d’erreur de droit |
| I | Neuf connecteurs (lecture, pas d’appel payant) | voir checklist ci-dessous |
| J | Pool API | `pool_size` + `max_overflow` ≤ `max_connections` PostgreSQL, `pool_timeout` 5s, threads sync ≤ plafond pool |
| K | Timeouts PG | `statement_timeout` 15s et `idle_in_transaction_session_timeout` 60s (défaut) : un LLM lent ne doit plus garder une transaction ouverte ; Central AI libère le pool avant l’await. Un outil SQL >15s échoue proprement — ajuster seulement si un rapport métier mesuré le justifie |
| L | **Avenqo Voice AI (Pré-Production Obligatoire)** | Exécution complète du plan `docs/voice/voice-ai-end-to-end-validation-plan.md` : Webhooks, audio bidirectionnel, vrai appel test (sous accord), création rendez-vous CRM synchronisé, multilingue (FR, EN, RO), zéro fuite inter-tenant et rollback prêt. **Condition bloquante pour tout passage en Production**. |

## Neuf connecteurs existants (après LOGIN, Sandbox test only)

Vérifier **déchiffrement et lecture isolée**, jamais un appel Shopify/Stripe/Telnyx/OpenAI payant :

| # | Surface | Contrôle | Attendu |
|---|---|---|---|
| 1 | Shopify | `commerce_connections` provider `shopify` | ligne du tenant A visible, B absente |
| 2 | WooCommerce | idem `woocommerce` | idem |
| 3 | Etsy | idem `etsy` si présent, sinon catalogue `coming_soon` | pas de fuite inter-tenant |
| 4 | Google Calendar | `crm_calendar_connections` | OAuth tokens restent chiffrés; lecture A seulement |
| 5 | Outlook Calendar | idem | idem |
| 6 | Stripe | `billing_accounts` / webhooks sandbox | pas de charge LIVE |
| 7 | Telnyx | `voice_business_configs` | pas d’appel, pas d’achat de numéro |
| 8 | OpenAI | Central AI | mock ou clé sandbox; `company_id` session uniquement |
| 9 | Scheduler commerce interne | trigger interne authentifié | token service, pas un tenant header |

`CONNECTOR_ENCRYPTION_KEYS` est applicatif : le cutover `avenqo_app` ne le rotate pas. Si le déchiffrement échoue, rollback LOGIN propriétaire, **ne pas** régénérer les clés.

## Rollback Sécurisé (Contrôle d'exposition inter-tenant)

> [!WARNING]
> Un retour direct de l'API au rôle propriétaire `postgres` désactive le verrouillage RLS au niveau base. Pour éviter tout risque d'exposition de données inter-entreprises :

1. **Quarantaine du trafic public immédiate** : Si l'API doit être reconnectée au rôle propriétaire pour diagnostic d'urgence, activer le mode maintenance ou restreindre le domaine Sandbox pour bloquer toute requête externe non contrôlée pendant l'intervention.
2. **Invalidation immédiate du rôle applicatif et rupture des connexions actives** :
   - Bloquer les nouvelles connexions : `ALTER ROLE avenqo_app NOLOGIN;`
   - **CRITIQUE** : `NOLOGIN` n'interrompt PAS les connexions déjà établies dans le pool SQLAlchemy. Il faut obligatoirement forcer la clôture immédiate de tous les backends actifs de l'application :
     ```sql
     SELECT pg_terminate_backend(pid) 
     FROM pg_stat_activity 
     WHERE usename = 'avenqo_app';
     ```
3. **Remise de `DATABASE_URL` sur le rôle d'administration** en environnement de quarantaine uniquement.
4. **En cas de régression de code ou de migration** : Préférer le rollback de révision Git sur Railway (redéploiement du SHA antérieur stable) plutôt qu'un contournement manuel des rôles.
5. **Si données corrompues** : Restaurer l'archive vérifiée `sandbox_20261015T121732Z...dump.age` (disponible localement et sur Tigris `pre-cutover-pr61/`) sur une base isolée avant toute décision de réécriture Sandbox.
6. Ne pas tenter de downgrade Alembic 0060/0061 à chaud : `NO FORCE RLS` élargit la visibilité de manière non désirée. Maintenir le schéma et réparer en avant.

## Preuves à consigner (sans secrets)

- Horodatage dump + checksum + résultat restore isolée.
- `roles_constrained=true`, `app_can_login` avant/après.
- Codes HTTP des tests A–J.
- Confirmation `database_url_unchanged` jusqu’à l’étape 6.
- Head Alembic `0061_tenant_hotpath_indexes` sur la copie isolée.

Tant que cette checklist n’est pas signée par le propriétaire, Sandbox reste sur le login actuel et `avenqo_app` reste NOLOGIN.

## Écarts relevés par la répétition PostgreSQL 16.15 (2026-10-15, base locale jetable, données synthétiques)

Mesures réelles, sans aucun accès à Sandbox ni Production. Seule la version **16.15** a été testée (ni 15 ni 18).

| Constat mesuré | Conséquence pour cette procédure |
|---|---|
| Rejeu Alembic 0001 → 0061 sur base vide : OK, head `0061_tenant_hotpath_indexes`, 70 tables FORCE RLS, 5 index 0061 présents | La chaîne est rejouable de zéro. Cela ne prouve rien sur l’état réel de Sandbox, dont la version Alembic n’a **pas** été lue. |
| `downgrade` 0061 → 0059 : 70 → 21 tables FORCE RLS, 0 index 0061, **toutes les lignes conservées** ; re-`upgrade` OK | Le downgrade ne perd pas de données mais **retire la protection RLS** des tables ajoutées par 0060. Il ne remet ni `DATABASE_URL` ni le rôle. |
| Restauration du dump pris **avant** déploiement : retour à alembic 0059, 21 tables FORCE RLS, 325 index sur 325, **15 clients CRM au lieu de 16** | **Toute écriture postérieure à la sauvegarde est perdue** si on restaure. |
| `ALTER ROLE avenqo_app LOGIN` puis `NOLOGIN` : connexion refusée après retour | Le retour de rôle est instantané et sans perte, mais c’est un état séparé de la base et du schéma. |
| `pg_dump --no-owner --no-privileges` (utilisé par `scripts/backup_db.py`) | Propriétaires et GRANT ne sont pas restaurés. Après une restauration, ré-appliquer propriétaires et privilèges (rôles `avenqo_*`) avant toute connexion applicative. |

### Écart critique : le déploiement applique les migrations

`railway.json` lance `python -m alembic upgrade head && uvicorn ...` à **chaque démarrage** du service API. Donc, si le déploiement Sandbox se déclenche à la fusion de la PR #61, les migrations 0060 et 0061 s’appliqueront **au démarrage, avant** la sauvegarde exigée ci-dessus. L’ordre « pré-requis 1 : fusion, puis sauvegarde » est donc dangereux. Non vérifié : si la fusion dans `promotion/sandbox` déclenche réellement un déploiement automatique Railway.

Règle à appliquer : **la sauvegarde vérifiée doit être terminée avant la fusion**, ou le déclenchement automatique doit être suspendu et le déploiement lancé à la main après sauvegarde.

### Risque de perte des écritures postérieures à la sauvegarde

- Le dump fige l’état à un instant T. Les écritures entre T et un éventuel retour arrière (inscriptions, CRM, messages Central AI, crédits IA, factures, événements Stripe) sont **absentes** du dump.
- Le downgrade Alembic **conserve** ces écritures, la restauration les **perd** : à privilégier tant que la base n’est pas corrompue (voir Rollback, point 4).
- Les événements externes déjà émis (paiement Stripe, appel Telnyx) ne se « restaurent » pas : leur écriture locale perdue crée un écart avec le fournisseur. À réconcilier à la main.

### Procédure à perte minimale (fenêtre de maintenance)

1. Annoncer la fenêtre ; faire cette bascule hors des heures d’usage.
2. Suspendre les écritures : arrêter les crons `avenqo-connector-ai-cron` (toutes les 5 min) et `avenqo-commerce-reconciliation-cron` (toutes les 15 min) **de l’environnement Sandbox**, puis passer l’API en lecture seule ou la mettre en maintenance.
3. Prendre le dump **après** l’arrêt des écritures. Écart T → bascule ≈ 0 donc perte ≈ 0 si rollback immédiat.
4. Vérifier le dump (checksum + restauration isolée + comparaison de comptages), comme dans « Sauvegarde vérifiée ».
5. Appliquer, tester (tableau A–K), et ne **réouvrir les écritures** qu’après les tests verts.
6. Après réouverture, la fenêtre de perte repart de zéro : en cas d’échec tardif, préférer le retour au rôle propriétaire + `NOLOGIN` (aucune perte) à la restauration.
7. Critères d’arrêt immédiat : 5xx sur login, refus de login légitime, `42501`, déchiffrement de connecteur en échec, ligne d’une autre entreprise visible, pool saturé (`QueuePool limit`).

### Contrôles à ajouter avant GO (non encore faits)

- Version Alembic **réelle** de Sandbox (lecture seule) : non lue à ce jour.
- Première sauvegarde Sandbox : le job `avenqo-daily-backup` de Sandbox existe, mais aucune exécution n’est visible dans ses journaux ; sa capacité à produire un dump restaurable est **non démontrée**.
- Chiffrement : `scripts/backup_db.py` produit un dump SQL en clair (SHA-256 seulement). Chiffrer côté client avant tout stockage durable.
- `users` et `company_memberships` n’ont pas de RLS (voulu : connexion et changement d’entreprise) ; leur isolation est applicative et couverte par `tests/security/test_users_memberships_access.py`.

