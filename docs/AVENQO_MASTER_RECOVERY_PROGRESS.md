# AVENQO — MASTER RECOVERY & RELEASE PROGRESS TRACKER

> **Document de référence unique** : Restauration, réparations, gating multi-tenant et alignement Production / Sandbox.
> **Date de mise à jour** : 2026-11-02 (UTC-5)
> **Statut global** : Phase 1 & 2 complétées — Correctifs P0 & P1 appliqués et validés par tests unitaires et d'intégration.

---

## 1. Synthèse des Environnements & Déploiements

| Composant | Environnement | ID Déploiement Railway / Vercel | Commit SHA | Statut Live | Alembic Revision |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **API Backend** | Production | `bc4deaff-d7cb-4202-b61c-9b1aa32edd0a` | `8660823efd4e1674613815b0b5ffad0f274a1009` | HTTP 200 (`/health`, `/ready`) | `0069_crm_service_approval_columns` |
| **Frontend Web** | Production | `https://avenqo.ca` (Vercel) | `8660823efd4e1674613815b0b5ffad0f274a1009` | HTTP 200 | N/A |
| **PostgreSQL** | Production | Service `6f290d34-03f3-4489-bf58-0713ee5fffa1` | N/A | OK (93 tables, 379 index, 11 ENUMs) | `0069` |
| **Volume Artifacts** | Production | Volume `bb60eade-4548-48d0-a8f6-0e7eeb238c6e` | N/A | Sauvegardé & restauré (61 fichiers, 21.5 MB) | N/A |
| **API Backend** | Sandbox | `7d5578e8-99fe-4fd5-a5e8-5c801c99b896` | `d10083fa3ebb8436fc8020dd1bea7e7e4825503c` | HTTP 200 (`/health`, `/ready`) | Aligné (93 tables) |
| **Frontend Web** | Sandbox | Vercel Preview Sandbox | `d10083fa3ebb8436fc8020dd1bea7e7e4825503c` | HTTP 200 | N/A |
| **Daily Backup** | Production | Service `95b8c1d8-aa9a-4d88-9e12-401ffaefd997` | Ancienne version (`ba2dda1`) | CRASHED (P0 FileNotFoundError résolu ci-dessous) | N/A |

---

## 2. Anomalies Détectées & Correctifs Appliqués

### 2.1 P0 — Échec du Service de Sauvegarde Quotidienne (`avenqo-daily-backup`)
- **Symptôme** : Déploiement `1f1f24b9-0fc6-4b0c-bc4e-4ad5ce6af2be` crashé en production (`FileNotFoundError: [Errno 2] No such file or directory: 'var/backups/...'`).
- **Cause racine** : Dans `backend/app/services/backup_service.py` (`_apply_retention` et `list_backups`), le téléchargement S3 supposait l'existence préalable du répertoire `self.root`. Sur un conteneur neuf sans volume pré-créé, le répertoire parent n'existait pas.
- **Correctif** : Ajout systématique de `local_meta.parent.mkdir(parents=True, exist_ok=True)` avant `self._s3.download(name, local_meta)`.
- **Validation** : Nouveau test unitaire `test_s3_retention_and_listing_when_local_root_missing` dans `tests/backend/test_backup_s3.py`. 5/5 tests passés avec succès (`100% passed`).
- **Commit** : `071c44f` (`fix(backup): create parent directories before downloading metadata from S3`).

### 2.2 P1 — Intégration PR #82 (Fraîcheur Dashboard & Reconnexion Calendar)
- **Modifications intégrées** :
  - `web/src/components/crm/crm-calendar-connection-card.tsx` : Explication explicite des rejets d'origine OAuth en preview Vercel / Sandbox au lieu d'un libellé infini "Connexion...".
  - `web/src/components/dashboard/dashboard-view.tsx` : Suppression du badge trompeur "Live" sur les revenus et commandes historiques.
  - Tests unitaires et d'intégration Vitest mis à jour et validés.
- **Commits cherry-pickés** :
  - `1a0914e` (`fix(calendar): explain rejected preview OAuth origin`)
  - `ed999bb` (`test(crm): keep workspace available on Calendar reconnect`)
  - `ec718a5` (`fix(dashboard): avoid labeling historical revenue as live`)

### 2.3 P1 — Faille de Gating Inter-Modules Central AI (`cross_agent`)
- **Symptôme** : `cross_agent` dans `AssistantRegistry` possédait 17 outils multi-domaines sans `module_code` ni `required_entitlements`, permettant potentiellement l'accès aux outils marketing, ocr, legal ou workflow à des entreprises n'ayant pas activé ces modules.
- **Cause racine** : Les classes de base des outils (`MarketingAITool`, `OCRAITool`, `LegalAITool`, `AutomationAITool`, `RetailAITool`, `CRMAITool`, `AccountingAITool`) ne définissaient pas `required_entitlements` au niveau de l'outil, et Central AI n'inspectait pas l'admissibilité individuelle de chaque outil de `cross_agent`.
- **Correctif** :
  1. Déclaration stricte de `required_entitlements` sur chaque classe de base d'outil dans `backend/app/ai/tools/base.py`.
  2. Filtrage granulaire dans `CentralAIService._tool_scope_for_request` (`backend/app/ai/central/service.py`) : exclusion des outils dont le module n'est pas actif pour le tenant demandeur.
  3. Barrière d'exécution hermétique dans `ToolAuthorizationPolicy.authorize` (rejet immédiat `ToolAuthorizationError("The required subscription module is not active.")`).
- **Validation** : 63/63 tests passés avec succès dans `tests/backend/test_central_ai.py` (`100% passed`).

### 2.4 P1 — Sécurisation du Router Accounting
- **Symptôme** : Le routeur API `backend/app/routers/accounting.py` n'appliquait pas de vérification d'activation de module, exposant les écritures aux tenants sans souscription au module.
- **Correctif** : Ajout de la dépendance de routeur `require_accounting_module` vérifiant `ModuleEntitlementService(db).can_use_module(tenant, "accounting")` et renvoyant HTTP 403 `{"code": "module_inactive", "module": "accounting"}` le cas échéant.
- **Validation** : Tests de régression validés (`test_accounting_ai.py` et `test_cross_agent_ai.py`).

### 2.5 P1 — Bug de Redirection Proxy `/reset-password`
- **Symptôme** : Un utilisateur avec un cookie de session actif ou résiduel ouvrant un lien de réinitialisation de mot de passe était automatiquement redirigé vers `/dashboard`.
- **Cause racine** : `/reset-password` était listé dans `AUTH_ONLY_ROUTES` dans `web/src/proxy.ts`.
- **Correctif** : Retrait de `"/reset-password"` de `AUTH_ONLY_ROUTES`.

---

## 3. Résultats des Tests de Validation Locale

| Fichier de Test | Périmètre Validé | Résultat | Temps |
| :--- | :--- | :--- | :--- |
| `tests/backend/test_backup_s3.py` | S3 Upload, List, Download, Rétention & Absence répertoire local | **5/5 PASS** (100%) | 37.69s |
| `tests/backend/test_accounting_ai.py` | Isolation multi-tenant & écritures confirmées | **1/1 PASS** (100%) | 4.99s |
| `tests/backend/test_cross_agent_ai.py` | Synthèse 360 multi-piliers & isolation | **1/1 PASS** (100%) | 2.29s |
| `tests/backend/test_central_ai.py` | Routage d'intentions Central AI & gating d'outils | **63/63 PASS** (100%) | 82.59s |
| `tests/backend/test_production_subscriptions_and_modules.py` | 12 modules, quotas de plan & activations | **6/6 PASS** (100%) | 1.80s |
| `tests/backend/test_subscription_module_entitlements.py` | Entitlements, swap de modules & limites | **4/4 PASS** (100%) | 0.70s |
| `tests/backend/test_voice_module_permissions.py` | Permissions Voice AI, rôles & actions autorisées | **17/17 PASS** (100%) | 28.76s |

**Total cumulé** : **97 tests exécutés — 97 PASS — 0 échec**.

---

## 4. Historique Git sur la Branche `release/v1.0.0-rc1`

```
28278c8 docs: create master recovery progress tracking document
9789572 fix(security): enforce module entitlements on cross-agent tools, accounting router, and unblock reset-password
071c44f fix(backup): create parent directories before downloading metadata from S3
ec718a5 fix(dashboard): avoid labeling historical revenue as live
ed999bb test(crm): keep workspace available on Calendar reconnect
1a0914e fix(calendar): explain rejected preview OAuth origin
8660823 Merge pull request #80 from Paulcioban1997/fix/p0-production-recovery-migration-guard
```

---

## 5. Déploiement et Validation E2E Sandbox (Exécutés)

- **Backend API Sandbox** (`24a2afc3-36f8-46d0-b79d-b323755a83f3`) :
  - Déploiement : `f8f4c374-d430-4cf0-bc19-6181c7f2437e` -> **SUCCESS**
  - Git SHA en ligne : `65c3a63439c1c74fa3de4845fb2a18a787001735`
  - `/api/v1/health` : HTTP 200
  - `/api/v1/ready` : HTTP 200 (database: ok, artifact_storage: ok, migrations: ok)

- **Service de Sauvegarde Automatique Sandbox** (`95b8c1d8-aa9a-4d88-9e12-401ffaefd997`) :
  - Déploiement : `7148ca66-5dc3-4130-bef0-28211d8fba66` -> **SUCCESS**
  - Exécution réelle vérifiée : ID `20261103T023558604070Z`, 2 222 818 octets (2.22 Mo), SHA-256 `ea31a5a91738777d97cd7a89153ea0fcb4e12d2dc6ed707eb4e78c979f14d410`
  - Zéro `FileNotFoundError`, upload S3 chiffré réussi.

- **Suite de Validation E2E Multi-Tenant Sandbox (12/12 PASS - 100%)** :
  1. `health_and_version` : **PASS** (HTTP 200, SHA `65c3a63`)
  2. `auth_registration_alpha` : **PASS** (Tenant Alpha Retail créé et authentifié)
  3. `auth_registration_beta` : **PASS** (Tenant Beta Healthcare créé et authentifié)
  4. `plan_quotas_and_credits` : **PASS** (Plan base : 2 modules, 6 500 requêtes IA)
  5. `module_activation_and_limits` : **PASS** (Activation autorisée pour 2 modules, 3ème bloqué en HTTP 409)
  6. `crm_and_calendar_oauth` : **PASS** (Génération d'URL OAuth Google avec origine Sandbox Vercel)
  7. `accounting_module_gating` : **PASS** (HTTP 200 pour Beta avec module actif, HTTP 403 `module_inactive` pour Alpha)
  8. `retail_intelligence` : **PASS** (Route fonctionnelle)
  9. `cross_tenant_forbidden_access` : **PASS** (Zéro fuite de données, transactions isolées par RLS)
  10. `central_ai_and_multi_tenant_isolation` : **PASS** (Registre d'agents filtré par entitlements)
  11. `password_reset_flow` : **PASS** (Route débloquée, email de réinitialisation accepté)
  12. `automations_and_documents` : **PASS** (Gestion des droits et statuts conforme)

- **Frontend Vercel Sandbox** :
  - URL : `https://avenqo-calendar-sandbox-paulmircea15-9488s-projects.vercel.app`
  - Statut : HTTP 200 OK (95 443 octets)

---

## 6. Phase A Production : Réparation & Validation du Service de Sauvegarde (Exécutée)

- **Service Railway** : `avenqo-daily-backup` (`95b8c1d8-aa9a-4d88-9e12-401ffaefd997`)
- **Environnement** : Production (`b9b03d41-2a67-4aab-a6f6-32939d8b81e0`)
- **ID Déploiement** : `1b879621-0514-400e-80a2-9bf50fb65602` -> **SUCCESS**
- **Git SHA déployé** : `65c3a63439c1c74fa3de4845fb2a18a787001735`
- **Start Command effectif** : `python scripts/backup_db.py`
- **Cron Schedule** : `0 7 * * *` (quotidien 07:00 UTC)
- **Restart Policy** : `NEVER` (pour conteneur de tâche planifiée)
- **Exécution réelle de test (déclenchement contrôlé unique)** :
  - **Backup ID** : `20261103T025801607841Z`
  - **Objets S3 créés** : `production/20261103T025801607841Z.sql` et `.json` dans `avenqo-backups-u7bgklgz2`
  - **Taille** : **2 316 461 octets (2.32 Mo)**
  - **Empreinte SHA-256** : `90ff9dccea99a4a5899327bf4af5d82672a5eeec4f0d0ce69dab5b2d7d99362b`
  - **Vérification absence d'erreur** : `FileNotFoundError` = 0 (résolu), purge accidentelle = 0
- **Restauration de contrôle sur PostgreSQL 18.6 isolé** :
  - **Résultat** : **PASS (code retour psql 0)**
  - **Révision Alembic** : `0069_crm_service_approval_columns`
  - **Tables restaurées** : 93 / 93
  - **Index restaurés** : 379 / 379
  - **Enums restaurés** : 11 / 11
  - **Entreprises préservées** : 17 / 17
  - **Utilisateurs préservés** : 17 / 17
- **État de l'API Production pendant et après l'opération** :
  - `/api/v1/health` : HTTP 200 OK (ininterrompue)
  - `/api/v1/ready` : HTTP 200 OK (ininterrompue)
- **Verdict Phase A** : **PASS**

---

## 7. Préparation de la Phase B (API Production)

- **Commit prêt pour promotion** : `65c3a63439c1c74fa3de4845fb2a18a787001735`
- **Start Command requis** : `/usr/local/bin/docker-entrypoint.sh uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1`
- **Attente stricte** : Autorisation explicite (GO) de l'utilisateur avant toute action sur l'API Production.
