# Architecture

The platform follows a layered enterprise architecture:

Frontend
↓
API Gateway
↓
Backend
↓
Modules
↓
AI Agents
↓
Database

## Layer responsibilities

- Frontend: user experience, presentation, and UI orchestration
- API Gateway: routing, traffic control, authentication boundaries, and cross-cutting concerns
- Backend: core application services, integration orchestration, and domain orchestration
- Modules: business- and product-specific AI tasks
- AI Agents: role-based intelligent assistants and specialized automation flows
- Database: persistence, data lifecycle, and future data governance

## Phase 2 implementation details

The current backend foundation includes:
- create_application() as the FastAPI application factory
- centralized settings through pydantic-settings
- request ID middleware for tracing and observability
- centralized logging and exception handling
- a health endpoint under /api/v1/health
- a root endpoint returning platform metadata

## Phase 4 AI Engine foundation

The shared AI Engine is a framework-neutral application layer under
`shared/ai_engine`. It defines stable contracts for ingestion, schema
detection, column mapping, validation, cleaning, preprocessing, feature
engineering, task-specific dataset building, AutoML, evaluation, model
selection, registry access, prediction, retraining, drift, monitoring, jobs,
and scheduling.

Source adapters are isolated below `connectors/` for CSV, Excel, SQLite,
PostgreSQL, MySQL, SQL Server, and REST APIs. Their vendor-specific logic is
intentionally deferred; orchestration depends only on connector protocols.

Every dataset, job, pipeline, model path, and prediction begins with a trusted
`TenantContext`. Model artifacts resolve below a company UUID namespace:

```text
var/models/{company_id}/{module}/{task}/{version}/
```

No model is shared between companies. Olist is not referenced by the engine
and may remain only in external demonstration or test assets.

`var` means variable runtime data: files produced or changed while the
application runs, unlike source code committed to Git. It follows a common
server filesystem convention and is not an environment variable. The model
repository root remains configurable, so a deployment may replace
`var/models` with mounted storage, an object store adapter, or another path.

Industry modules own their principal agent and task selection. Agents
delegate model resolution and prediction to the AI Engine and do not embed
pre-trained models.

## Module access boundary

Chaque opération d'un module commence par `ModuleAccessService`. Ce service
vérifie les droits d'accès de l'entreprise avant la validation de la tâche ou
l'orchestration de l'AI Engine. L'accès est refusé par défaut.

Le service dépend d'un petit contrat de lecture indépendant du stockage. Le
backend fournit `SQLAlchemyModuleEntitlements`, qui accepte uniquement les
droits actifs, commencés et non expirés pour les modules disponibles. Stripe
mettra à jour ces droits via la couche de facturation. Les agents et l'AI
Engine n'appelleront jamais Stripe directement.
