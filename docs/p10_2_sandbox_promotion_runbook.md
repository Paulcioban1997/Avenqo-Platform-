# 🚀 Runbook de Promotion Sandbox — Migration Alembic 0069 (P10.2)

> **Document de Référence Opérationnelle**  
> **Statut** : Approuvé pour répétition Sandbox / Staging  
> **Principe Directeur** : Strict Fail-Closed (Aucune approbation commerciale inférée)  
> **Interdictions** : Aucun merge vers `main`, aucun déploiement automatique, aucune mutation en Production, aucune activation de la ligne Telnyx.

---

## 1. 📋 Résumé Exécutif & Changements P10.2

Dans la version P10.1, la migration 0069 auto-approuvait les prestations disposant d'anciens rendez-vous confirmés ou complétés.  
**Correction P10.2** : Un rendez-vous historique ne constitue **pas** une preuve d'approbation commerciale explicite de l'OWNER.  
- La migration 0069 initialise **100 % des prestations** à `is_approved_by_owner = false` et `is_published = false`.
- **Zéro perte de données** : Toutes les prestations (`crm_services`) et tous les rendez-vous (`crm_appointments`) sont intégralement préservés.
- L'activation commerciale se fait exclusivement via validation explicite de l'OWNER dans l'interface ou confirmation formelle auditée.
- Central AI et le moteur Voice masquent systématiquement toute prestation non approuvée.

---

## 2. 🛡️ Garde-fous et Conditions Préalables (Pre-Flight)

Avant d'initier toute opération sur l'environnement cible (Sandbox / Staging) :

1. **Vérification de l'environnement** :
   ```bash
   echo $ENVIRONMENT # Doit être sandbox ou staging
   ```
2. **Sauvegarde transactionnelle complète** :
   ```bash
   python scripts/backup_db.py --tag pre_0069_hardening
   ```
   *Vérifier la taille et la validité de l'archive de dump générée.*

3. **Exécution de l'inventaire en lecture seule (ZÉRO mutation)** :
   ```bash
   python scripts/crm_migration_services_inventory.py --output /tmp/inventory_pre_0069.md
   ```
   *Analyser la liste des prestations avec historique de rendez-vous qui nécessiteront une re-validation OWNER.*

---

## 3. ⚙️ Procédure de Migration Contrôlée

### Étape 1 : Vérification de la version Alembic courante
```bash
python scripts/read_alembic_version.py
# Sortie attendue : 0068_resolve_voice_phone_number_tenant
```

### Étape 2 : Application contrôlée de la migration 0069
```bash
alembic upgrade 0069_crm_service_approval_columns
```

### Étape 3 : Contrôle post-migration immédiat
```bash
python scripts/crm_migration_services_inventory.py --output /tmp/inventory_post_0069.md
```
Vérifications obligatoires :
- Colonnes `is_approved_by_owner` et `is_published` présentes.
- `services_requiring_owner_review` correspond exactement au nombre de prestations historiques actives.
- Aucun service n'a été publié silencieusement (ex: clinique `Produits_Ero` reste `false`).

---

## 4. 👤 Procédure de Validation OWNER (Sans manipulation SQL)

1. L'administrateur ou propriétaire de l'entreprise se connecte à la console Avenqo :
   `https://<sandbox-domain>/dashboard/crm/settings`
2. Les prestations existantes s'affichent avec le badge ambre :  
   `Non approuvé — Réservation bloquée`
3. Le propriétaire examine le libellé, la durée et le prix réel.
4. Le propriétaire clique sur **Approuver et publier** :
   - Requête déclenchée : `POST /api/v1/crm/services/{service_id}/toggle-approval`
   - Un journal d'audit immuable `AuditLogEntry` est enregistré :
     - `action`: `crm_service_approval_toggled`
     - `actor_user_id`: `<uuid-owner>`
     - `metadata`: `{"service_name": "...", "is_approved_by_owner": true, "is_published": true}`
5. Le badge passe au vert : `Approuvé & Publié`.
6. Le service redevient immédiatement disponible pour :
   - La prise de rendez-vous client en ligne.
   - Les recommandations de créneaux par Central AI Copilot.
   - La réservation par l'agent Voice Avenqo.

---

## 5. 🔄 Procédure de Restauration Testée (Rollback)

Si une anomalie inattendue survient post-migration :

### Option A : Rétrogradation Alembic (Downgrade réversible)
```bash
alembic downgrade 0068_resolve_voice_phone_number_tenant
```
- Supprime les colonnes `is_approved_by_owner` et `is_published`.
- Préserve 100 % des tables, lignes, données clients et historiques de rendez-vous.
- Testé et certifié unitaire et intégration (`test_alembic_0069_migration.py`).

### Option B : Restauration de dump complet (Disaster Recovery)
```bash
python scripts/restore_db.py --tag pre_0069_hardening
```

---

## 6. 🛑 Checklist de Clôture

| Contrôle | Statut Requis | Méthode de Validation |
|---|---|---|
| Zéro auto-approbation inférée | ✅ VALIDÉ | `test_alembic_0069_migration.py` |
| Produits_Ero clinique bloquée | ✅ VALIDÉ | Inventaire + tests d'intégration |
| Étanchéité multi-tenant | ✅ VALIDÉ | `test_multi_tenant_isolation_on_service_approval` (HTTP 404) |
| Rôle non autorisé rejeté | ✅ VALIDÉ | `test_non_owner_forbidden_from_approving_service` (HTTP 403) |
| Central AI & Voice hermétiques | ✅ VALIDÉ | `test_central_ai_and_voice_catalog_hides_unapproved_services` |
| Ligne Telnyx inactive | 🔒 INACTIF | Pas de trafic voix live engagé |
| Sauvegarde testée | 💾 PRÊT | Script `backup_db.py` opérationnel |
