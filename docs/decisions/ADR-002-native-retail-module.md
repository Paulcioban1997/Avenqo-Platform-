# ADR-002: RetailSenseAI est un module natif de Avenqo

## Status

Accepted on 2026-08-04.

## Context

RetailSenseAI began as a standalone development project. Avenqo now needs one
consistent customer experience, one tenant boundary, and one shared AI Engine.

## Decision

- The customer-facing product is Avenqo.
- RetailSenseAI utilise le code de module stable `retail`.
- Les entreprises activent le module avec les abonnements et droits Avenqo.
- The module owns task definitions, not model implementations.
- AI Engine owns ingestion, training, model storage, and prediction workflows.
- Every artifact remains isolated by company, module, task, and version.
- The standalone RetailSenseAI project is not imported or deployed by Avenqo.

The existing internal Python package path `modules.retailsense` is retained
temporarily to avoid an unrelated bulk file move. It is not a public product
name or an integration boundary.

## Consequences

Le code stable `retail` peut Ãªtre utilisÃ© par les API, les droits associÃ©s Ã 
Stripe, les tÃ¢ches et les chemins de modÃ¨les. Les futurs modules suivront le
mÃªme contrat sans modifier le cÅ“ur de l'AI Engine.
