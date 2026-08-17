# Ingestion universelle de datasets d'entreprise (Phase 26)

## Objectif
Permettre à n'importe quelle entreprise cliente d'importer ses propres
données (peu importe les noms de colonnes) sans dépendance au schéma
Olist historique, avec isolation stricte multi-tenant.

## Formats supportés
CSV, XLSX, JSON, Parquet — via `CompanyDatasetLoader`
(`shared/ai_engine/dataset_ingestion/loader.py`). Extensions non supportées,
fichiers vides, corrompus ou trop volumineux sont rejetés avec des
exceptions métier explicites (`exceptions.py`).

## Pipeline
1. **Chargement** (`loader.py`) → lignes normalisées + typage natif
   (int/float/bool/datetime).
2. **Détection de schéma** (réutilise `SchemaDetector` existant).
3. **Mapping sémantique** (`column_mapper.py`, `SemanticColumnMapper`) :
   combine alias exacts, similarité de nom ET compatibilité de type inféré
   (`type_inference.py`) — pas un simple "fuzzy matching" par nom, pour
   éviter les faux positifs (ex. `customer_review` vs `customer_id`).
   Champs canoniques centralisés dans `canonical_fields.py`.
4. **Statut de mapping** : `MAPPING_REQUIRED` si une colonne a une confiance
   `MEDIUM`/`LOW` → une revue manuelle est nécessaire via
   `POST /datasets/{id}/mapping`.
5. **Nettoyage non destructif** (`cleaning.py`, `CompanyDatasetCleaner`) :
   supprime uniquement les doublons stricts, convertit les types selon le
   mapping validé, ne supprime jamais silencieusement des lignes.
6. **Qualité** (`quality.py`) : statut `good`/`warning`/`poor` en langage
   métier (pas de pourcentage brut).
7. **Profilage** (`profiling.py`) : statistiques par colonne sans jamais
   logger de valeurs brutes individuelles.
8. **Préparation à l'entraînement** (`readiness.py` +
   `prepared_dataset.py`) : évalue, par capacité IA (churn, demande, prix,
   etc.), si les champs canoniques nécessaires sont présents — toujours en
   langage business, jamais en jargon ML.

## Versionnement
Chaque ré-upload d'un fichier de même nom pour le même tenant crée une
nouvelle `DatasetVersion` (jamais d'écrasement silencieux). Les relations
1-1 (`profile`, `mapping`, `quality_report`) sont explicitement supprimées
et purgées de l'identity map SQLAlchemy (`session.expire`) avant d'être
recréées, pour éviter les conflits d'unicité.

## Stockage
`LocalDatasetStorage` (`storage.py`) sépare les données brutes des données
préparées, par tenant/dataset/version, avec protection anti-traversée de
chemin. Une interface abstraite `DatasetStorage` permet un futur backend
S3/GCS (non implémenté en Phase 26).

## Passation à l'entraînement
`CompanyDatasetIngestionService.get_prepared_dataset(tenant, dataset_id)`
reconstruit un `PreparedCompanyDataset` (colonnes canoniques, lignes
nettoyées, profil, mapping, qualité, disponibilité par capacité) pour un
dataset au statut `READY`. Aucun entraînement n'est déclenché
automatiquement : ceci est uniquement le point d'entrée que les futurs
moteurs de capacité pourront consommer.

## Endpoints
- `POST /api/v1/datasets/upload` — upload universel (tous formats).
- `GET /api/v1/datasets/{id}/profile` — profil, mapping suggéré, qualité,
  disponibilité par capacité.
- `POST /api/v1/datasets/{id}/mapping` — validation/correction manuelle du
  mapping (déclenche nettoyage + qualité + passage à `READY`).

L'ancien endpoint `POST /api/v1/datasets/csv` (pipeline historique) reste
inchangé et pleinement fonctionnel.

## Tests
`tests/backend/test_phase26_universal_company_data_ingestion.py` (45 tests)
couvre les 4 formats, le rejet des cas invalides, l'isolation tenant, le
mapping (y compris deux entreprises aux colonnes totalement différentes),
le nettoyage, la qualité, le profilage, la disponibilité par capacité, le
versionnement et la passation à l'entraînement.
