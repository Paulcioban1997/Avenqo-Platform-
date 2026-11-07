# AVENQO PR #93 — incident `pg_dump` et preuve de sauvegarde

Date : 7 novembre 2026. Périmètre : Production, sauvegarde et restauration isolée uniquement. Aucune migration `0074`, fusion PR #93, modification Stripe, signature légale ou modification des données d'entreprise n'a été effectuée.

## Diagnostic démontré

L'exécution autorisée de `scripts/backup_db.py` dans le service API a échoué avec `BackupError: pg_dump a échoué (code 1)` avant tout upload S3. Le code capture `stderr` et ne publie que le code de sortie.

Diagnostic ciblé, sans divulgation de secrets : `pg_dump` 18.6 et PostgreSQL serveur 18.6 ; DNS privé résolu ; connexion SQL réussie sous TLS ; révision active `0073_contract_signing_challenges` ; `/tmp` inscriptible et espace libre suffisant ; URL PostgreSQL reconnue et `PGPASSWORD` transmis par `_postgres_subprocess_connection`. Un essai de dump vers `/dev/null` a reproduit le code 1. La catégorie extraite de `stderr` est **RLS / privilèges**, table `accounting_invoices`. Le rôle applicatif `avenqo_app` possède SELECT mais n'a pas `BYPASSRLS` ; `pg_dump` refuse une sauvegarde potentiellement incomplète. Aucune politique RLS n'a été désactivée et aucun droit applicatif n'a été élargi.

## Sauvegarde complète réelle

Le rôle administrateur existant dans le service PostgreSQL a produit un dump complet dans `/tmp`, sans modifier la base active. SHA-256 du dump : `fcf0b65b1beff63b9351ad34ff584d013ce754bb2bcec74ee8860d5b6ff7bc2c` ; taille : 2 371 822 octets. Le dump a été transféré directement entre les deux services Railway par TLS avec authentification mutuelle ; le conteneur API a recalculé la même empreinte. Aucune donnée Production n'a été exportée vers le poste local.

Dans l'API portant `/data/artifacts`, la sauvegarde au format `BackupService` a été créée puis chargée vers le bucket S3 persistant `avenqo-backups-u7bgklgz2`, préfixe `production/`, sans appliquer la rétention :

| Élément | Valeur vérifiée |
|---|---|
| Backup ID | `20261107T162834350977Z` |
| Révision du dump et de la base | `0073_contract_signing_challenges` |
| SQL | 2 371 822 octets ; SHA-256 `fcf0b65b1beff63b9351ad34ff584d013ce754bb2bcec74ee8860d5b6ff7bc2c` |
| Artefacts | 61 fichiers ; archive 2 591 993 octets ; SHA-256 `0a858ebcb25094fe2f606ff79b099223783807fc877348282bb0c3a2178272ef` |
| Persistance | Trois objets S3 (`.sql`, `.json`, `_artifacts.tar.gz`) relus depuis le bucket ; SHA-256 distants identiques aux fichiers source |

## Restauration isolée réelle

Un second cluster PostgreSQL 18 a été initialisé dans `/tmp` du conteneur PostgreSQL existant, sur socket Unix séparé et sans écoute TCP. Son répertoire de données n'était pas le volume actif. La restauration SQL s'est terminée avec code 0 et `ON_ERROR_STOP=1` dans une transaction. La base restaurée et la source présentent 96 tables et la même révision `0073_contract_signing_challenges`.

Comparaisons par comptes, sans données clients affichées : `companies` 18/18, `users` 18/18, `billing_accounts` 18/18, `billing_invoices` 2/2, `crm_leads` 0/0, `datasets` 28/28, `audit_log_entries` 34/34, `company_contracts` 4/4, `company_legal_profiles` 0/0, `contract_signing_challenges` 0/0. Ce sont des contrôles de structure et de volumétrie ; ils ne prouvent pas une identité ligne par ligne de toutes les tables. Le dump restauré avait le même SHA-256 que l'objet S3 revérifié.

Le service API a aussi re-téléchargé le backup depuis S3 via `verify_backup`, puis extrait les artefacts dans `/tmp`. Les empreintes individuelles des 61 fichiers restaurés sont identiques à celles de `/data/artifacts`. Le cluster temporaire a été arrêté, ses fichiers `/tmp` supprimés, et la base active reste à `0073_contract_signing_challenges`.

## Statut et suite nécessaire

**Sauvegarde complète pré-bascule et restauration isolée : PASS.** **Sauvegarde quotidienne automatique complète : FAIL persistant.** Lecture Railway du 7 novembre : le cron a terminé à `07:01:46Z` avec le backup ID `20261107T070127389835Z`, SQL de 2 371 822 octets et révision `0073_contract_signing_challenges`. Ses journaux indiquent toutefois `artifact_file_count=0` et `artifacts_archived=False`. Le service n'a aucun volume monté. Cette exécution prouve une sauvegarde SQL, pas une sauvegarde complète des fichiers. Le compte de base utilisé par ce cron n'a pas été identifié ; ne pas supposer qu'il est identique au compte `avenqo_app` utilisé par l'API et concerné par l'échec RLS reproduit plus haut.

Correctif durable minimal à préparer sur branche dédiée : diagnostic expurgé des erreurs `pg_dump` dans le service API ; rôle de sauvegarde distinct si une sauvegarde est lancée depuis l'API ; stratégie d'archivage des artefacts depuis le service qui monte `/data/artifacts` ou processus coordonné. Le cron existant sauvegarde déjà le SQL, mais ne remplit pas à lui seul l'objectif de reprise des fichiers. Les nouveaux secrets/variables Production et tout déploiement Production demandent une autorisation distincte. Ne jamais utiliser `--enable-row-security` pour faire passer le dump en excluant silencieusement des lignes.

**La transition PR #93 reste arrêtée.** Une sauvegarde ponctuelle vérifiée ne vaut pas autorisation de migration ou de fusion.
