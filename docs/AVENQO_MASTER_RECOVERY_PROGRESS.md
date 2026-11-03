# AVENQO — MASTER RECOVERY & RELEASE PROGRESS TRACKER

> **Document de référence unique** : Restauration, réparations, gating multi-tenant et alignement Production / Sandbox.
> **Date de mise à jour** : 2026-11-02 (UTC-5)
> **Statut global** : Phase 1 & 2 complétées — Correctifs P0 appliqués et validés par tests unitaires et d'intégration.

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

## 3. Historique Git sur la Branche `release/v1.0.0-rc1`

```
9789572 fix(security): enforce module entitlements on cross-agent tools, accounting router, and unblock reset-password
071c44f fix(backup): create parent directories before downloading metadata from S3
ec718a5 fix(dashboard): avoid labeling historical revenue as live
ed999bb test(crm): keep workspace available on Calendar reconnect
1a0914e fix(calendar): explain rejected preview OAuth origin
8660823 Merge pull request #80 from Paulcioban1997/fix/p0-production-recovery-migration-guard
```

---

## 4. Prochaines Étapes Contrôlées

1. **Validation Sandbox** : Déployer et exécuter la suite de tests automatisée sur Sandbox (`https://avenqo-platform-sandbox.up.railway.app`).
2. **Vérification Multi-Tenant Sandbox** : Exécuter le test de non-régression de l'isolation des données sur 2 entreprises fictives (Tenant A et Tenant B).
3. **Audit de non-régression global** : Exécution de la suite pytest complète.
4. **Demande d'autorisation explicite (GO)** auprès de l'utilisateur avant tout déploiement en Production.
