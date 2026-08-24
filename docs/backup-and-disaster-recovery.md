# Sauvegarde & Reprise après sinistre — Avenqo

## 1. Ce qui doit être sauvegardé

| Donnée | Emplacement actuel | Criticité |
|---|---|---|
| Base de données applicative (utilisateurs, entreprises, conversations, factures, audit log...) | Fichier SQLite `var/avenqo.db` (dev) ou `DATABASE_URL` configuré | Critique |
| Artefacts de modèles ML entraînés | `var/models` (`MODEL_REGISTRY_ROOT`) | Élevée |
| Jeux de données / documents uploadés par les tenants | `var/artifacts` (`ARTIFACT_ROOT`) | Élevée |
| Base de connaissances du Support AI (contenu produit, pas de données tenant) | `platform_knowledge/` (`AI_SUPPORT_KNOWLEDGE_ROOT`) | Faible (reconstructible depuis le dépôt Git) |
| Configuration de facturation (mapping plans ↔ Stripe price IDs) | Variables d'environnement + table `companies`/`subscriptions` en base | Critique |

**Note** : `platform_knowledge/` étant versionné/reconstructible depuis le
code, il n'est pas un actif de sauvegarde critique contrairement aux
données de base et aux artefacts générés à l'exécution.

## 2. Stratégie de sauvegarde — implémentée (remédiation finale)

`backend/app/services/backup_service.py` implémente une sauvegarde/
restauration réelle de la base de données, exclusivement via des **outils
CLI internes** (`scripts/backup_db.py`, `scripts/restore_db.py`) — **aucune
route HTTP n'expose jamais ces opérations** (voir
`tests/security/test_idor_and_isolation.py::test_no_http_route_exposes_backup_or_restore`),
de sorte qu'aucun tenant ni le frontend ne peut jamais déclencher une
sauvegarde/restauration de la plateforme.

### Création d'une sauvegarde

```bash
python scripts/backup_db.py
```

- Utilise l'API native SQLite `sqlite3.Connection.backup()` (et non une
  simple copie de fichier) : produit un instantané cohérent même si des
  écritures sont en cours pendant la sauvegarde.
- Chaque sauvegarde produit deux fichiers dans `BACKUP_ROOT` (par défaut
  `var/backups/`, configurable) : `<id>.db` (l'archive) et `<id>.json`
  (métadonnées : `created_at`, `environment`, `database_type`, `app_version`,
  `git_revision`, `format_version`, `checksum_sha256`, `size_bytes` —
  **jamais de secret**, voir `tests/backend/test_phase34_backup_restore.py::test_backup_metadata_never_contains_secrets`).
- Une politique de rétention (`BACKUP_RETENTION_DAYS`, 30 jours par défaut)
  supprime automatiquement les sauvegardes plus anciennes à chaque nouvelle
  création.
- Abstraction de stockage (`LocalBackupStorage`) : implémentation locale
  actuelle, remplacable plus tard par un stockage S3-compatible sans changer
  la logique de `BackupService` — aucun fournisseur cloud n'est imposé avant
  qu'il ne soit choisi.

### Restauration (vers une base CIBLE explicite)

```bash
python scripts/restore_db.py --backup-id <id> --target-database-url sqlite:///var/restored.db
```

- Vérifie TOUJOURS la somme de contrôle (`checksum_sha256`) avant de
  restaurer — une archive corrompue est **rejetée** (`CorruptBackupError`),
  jamais restaurée silencieusement.
- `--target-database-url` est **obligatoire** : le script ne restaure jamais
  silencieusement vers `DATABASE_URL` actif. Si la cible coïncide avec la
  base active, `--force` est requis explicitement.
- L'identifiant de sauvegarde est validé contre toute tentative de
  traversée de chemin (`../`, chemins absolus) avant toute lecture disque.

### Limitation connue

Ce service ne prend en charge que **SQLite** pour l'instant (seule base
utilisée par ce dépôt). Une migration vers PostgreSQL (voir
`docs/production-deployment.md` §4) nécessiterait `pg_dump`/`pg_restore` à la
place de l'API de sauvegarde SQLite utilisée ici.

Artefacts (`var/models`, `var/artifacts`) : **toujours pas de mécanisme
automatisé** dans ce dépôt — recommandation inchangée : synchronisation vers
un stockage objet durable côté infrastructure d'hébergement.

## 3. Procédure de restauration (base de données)

1. Arrêter le trafic applicatif (mode maintenance) pour éviter les écritures
   concurrentes pendant la restauration.
2. Vérifier l'intégrité de la sauvegarde choisie (automatique via
   `scripts/restore_db.py`, qui refuse toute archive dont la somme de
   contrôle ne correspond pas).
3. Restaurer vers une base cible explicite avec `scripts/restore_db.py`
   (voir §2).
4. Redémarrer le backend et vérifier `GET /api/v1/ready` → `status: "ready"`.
5. Exécuter une vérification manuelle minimale : connexion d'un compte de
   test, lecture d'une conversation existante, lecture d'une facture
   existante.
6. Réactiver le trafic.

Cette procédure a été validée par un **exercice de restauration réel** sur
une base temporaire isolée (jamais la base de développement principale) :
création de fixtures minimales (tenant, utilisateur, compte de facturation)
→ sauvegarde → destruction → restauration → vérification des comptages de
lignes et des relations tenant (`company_id`) — voir
`tests/backend/test_phase34_backup_restore.py::test_real_restore_exercise_preserves_tenant_data_integrity`.

## 4. Scénarios de reprise après sinistre

| Scénario | Impact | Réponse |
|---|---|---|
| Perte de la base de données (corruption/suppression) | Interruption totale du service | Restaurer depuis la dernière sauvegarde valide (§3). Perte de données = delta entre la sauvegarde et l'incident. |
| Échec de déploiement (nouvelle version cassée) | Interruption ou dégradation | Rollback vers l'image conteneur précédente (voir `docs/production-deployment.md` §9). Sans Alembic, un rollback reste sûr tant qu'aucune migration de schéma cassante n'a eu lieu. |
| Panne d'un fournisseur IA (OpenAI/Anthropic/Google) | Dégradation des fonctionnalités IA uniquement | L'AI Gateway (Phase 32) bascule automatiquement vers les fournisseurs de secours configurés (`AI_FALLBACK_PROVIDER_1/2`) via circuit breaker ; si tous les fournisseurs sont indisponibles, les endpoints IA renvoient une erreur explicite sans impacter le reste de l'application (auth, facturation, dashboard restent fonctionnels). |
| Panne Stripe | Facturation/paiement indisponibles temporairement | Le reste de l'application continue de fonctionner (facturation isolée). Les webhooks Stripe redélivrent automatiquement les événements manqués une fois le service rétabli. |
| Panne du stockage d'artefacts (`var/artifacts`/`var/models`) | Impossibilité de charger/entraîner de nouveaux modèles ou datasets | Le reste de l'application (auth, facturation, chat IA sans dépendance à un artefact) continue de fonctionner ; restaurer depuis la sauvegarde du stockage objet (§2). |

## 5. Statut de validation

Un exercice de restauration RÉEL a été exécuté et automatisé en test
(`tests/backend/test_phase34_backup_restore.py`) sur une base isolée, avec
vérification de checksum, rejet d'archives corrompues, et validation de
l'intégrité des relations tenant après restauration. Non exécuté :
un DR drill à l'échelle infrastructure complète (multi-région, bascule DNS,
etc.) — hors périmètre d'un lancement V1 mono-instance.
