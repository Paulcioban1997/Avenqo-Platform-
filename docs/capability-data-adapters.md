# Capability Data Adapters (Phase 27)

## Purpose

Phase 26 produces a `PreparedCompanyDataset`: a validated, cleaned, tenant-scoped
dataset with canonical column mapping applied. Phase 27 adds the layer that
turns that generic prepared dataset into a **capability-specific**,
ML-ready `CapabilityDataset` for one of RetailSenseAI's 9 capabilities
(`churn`, `segmentation`, `recommendation`, `sentiment`, `demand`,
`weekly_forecast`, `price`, `bad_review`, `anomaly`), without ever leaking
tenant data across companies and without ever bypassing business validation
with raw pandas/sklearn errors.

## The boundary: `PreparedCompanyDataset` → `CapabilityDataset`

```
PreparedCompanyDataset (Phase 26)
        │  canonical_columns: {original_column -> canonical_field}
        │  rows: tuple[dict[str, object], ...]   (keyed by ORIGINAL column names)
        ▼
CapabilityDatasetAdapter.validate() / .prepare()
        │  checks CAPABILITY_DATA_REQUIREMENTS[capability] against
        │  available canonical fields + usable row count
        ▼
CapabilityDataset (Phase 27)
        │  required_fields / available_fields (canonical names)
        │  rows: SAME tuple object as `prepared.rows` (zero-copy)
        ▼
RetailSenseAI capability (training / inference — unchanged, out of scope)
```

`CapabilityDataset` never duplicates row data: `rows` is the exact same
tuple reference as `PreparedCompanyDataset.rows`. No copy, no mutation.

## Components

- **`shared/ai_engine/capability_dataset/contracts.py`**
  `CapabilityDataset` (frozen dataclass) and `CapabilityDatasetValidation`
  (non-throwing readiness result: `ready`, `missing_fields`, `warnings`,
  `row_count`, `usable_row_count`).

- **`shared/ai_engine/capability_dataset/exceptions.py`**
  Business-language exceptions, never raw KeyError/pandas errors:
  - `UnknownCapability` — capability name not registered.
  - `MissingCapabilityFields` — e.g. *"Price analysis requires unit price."*
  - `InvalidCapabilityDataset` — required fields present but no row has
    usable values.

- **`shared/ai_engine/capability_dataset/adapter.py`**
  `CapabilityDatasetAdapter`:
  - `validate(prepared, capability) -> CapabilityDatasetValidation` — never
    raises except `UnknownCapability` for an unregistered capability name.
  - `prepare(prepared, capability) -> CapabilityDataset` — raises the
    business exceptions above when the dataset isn't ready; otherwise
    returns the immutable `CapabilityDataset`.
  - Reuses `CAPABILITY_DATA_REQUIREMENTS` from
    `shared/ai_engine/dataset_ingestion/capability_requirements.py`
    (Phase 26) — requirements are defined once, not duplicated.

- **`shared/ai_engine/capability_dataset/feature_engineering.py`**
  Illustrates the canonical-data vs. derived-features boundary for
  `segmentation` (RFM: recency/frequency/monetary). Derived features are
  computed from a `CapabilityDataset` but are never written back into it —
  canonical fields stay canonical. This module is intentionally scoped to
  one example; it does not replace or modify the existing RetailSenseAI
  training pipelines under `modules/retailsense/tasks/`.

- **`backend/app/services/capability_execution_gate.py`**
  `CapabilityExecutionGate` — the tenant-scoped entry point used by the API
  layer:
  - `check_readiness(tenant, dataset_id, capability)` → resolves the
    prepared dataset via `CompanyDatasetIngestionService.get_prepared_dataset`
    (Phase 26, unmodified) and delegates to `adapter.validate()`.
  - `prepare(tenant, dataset_id, capability)` → same resolution, delegates
    to `adapter.prepare()`.
  - `prepare_training_input(gate, tenant, dataset_id, capability)` — the
    training handoff function: the only way a training pipeline should
    obtain a `CapabilityDataset`.
  - Tenant isolation is inherited entirely from
    `CompanyDatasetIngestionService.get_prepared_dataset`, which raises
    `DatasetNotFoundError` for cross-tenant or non-existent datasets. The
    gate never bypasses this check.

## HTTP API

`POST /api/v1/datasets/{dataset_id}/capabilities/{capability}/prepare`

Response: `CapabilityDatasetResponse` (dataset id/version, capability,
required/available fields, row count, warnings, adapter version).

Error mapping:

| Business exception | HTTP status |
|---|---|
| `CompanyDatasetNotFoundError` (incl. cross-tenant) | 404 |
| `UnknownCapability` | 400 |
| `DatasetIngestionError` (dataset not READY) | 409 |
| `CapabilityNotReady` (missing fields / no usable rows) | 422 |

All error responses go through the application's existing global exception
handler (`backend/app/core/exception_handlers.py`), which wraps
`HTTPException` into the standard envelope:
`{"success": false, "error": {"code": ..., "message": ...}, "request_id": ...}`.

## Provenance & determinism

Every `CapabilityDataset` carries `company_id`, `dataset_id`,
`dataset_version`, `mapping_version`, `cleaning_version`, and
`adapter_version`, so downstream training can record exactly which
prepared dataset and adapter version produced its inputs. Given the same
`PreparedCompanyDataset` and capability, `adapter.prepare(...)` is
deterministic and side-effect free — repeated calls produce equal
`CapabilityDataset` values.

## Out of scope (deliberately not touched in Phase 27)

- Existing RetailSenseAI training tasks (`modules/retailsense/tasks/*`),
  `TrainingDispatcher`, hyperparameter search (GridSearchCV/Optuna/KerasTuner).
- Chatbot / RAG / LLM / embeddings / vector DB / cloud storage integration.
- Phase 26 ingestion, cleaning, profiling, and storage code (reused as-is).
