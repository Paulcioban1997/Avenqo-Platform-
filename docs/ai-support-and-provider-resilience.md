# Avenqo Support AI & Resilient AI Gateway (Phase 32)

## Vue d'ensemble

Phase 32 ajoute deux capacités indépendantes qui, ensemble, complètent
l'architecture IA d'Avenqo (Phases 28-31.1) sans jamais la reconstruire :

1. **Avenqo Platform Support AI** — un assistant d'aide/support distinct
   du Business Assistant (Copilot métier), qui répond aux questions
   "comment utiliser Avenqo" (import CSV, connexions, plans, erreurs
   courantes) en s'appuyant sur la documentation produit — jamais sur les
   données métier d'un tenant.
2. **Smart AI Gateway** (`AvenqoAIGateway`) — une couche de routage et de
  résilience multi-fournisseur (OpenAI/Anthropic/Gemini) avec scoring,
  retry, circuit breaker et fallback séquentiel, utilisée par le Business
  Assistant **et** le Support AI.

```mermaid
flowchart LR
    subgraph Frontend
        A[Business Assistant UI]
        S[Avenqo Support UI]
    end
    A --> BC[ChatService\nBusiness Copilot]
    S --> SC[SupportChatService]
    BC --> GW[AvenqoAIGateway]
    SC --> GW
    GW --> P1[OpenAI]
    GW --> P2[Anthropic fallback]
    GW --> P3[Gemini fallback]
    BC --> RS[RetrievalService\n(Dataset tenant)]
    SC --> PK[PlatformKnowledgeRetrievalService\n(platform_knowledge/)]
```

## Avenqo Platform Support AI

### Séparation stricte Business Copilot / Support AI

| | Business Assistant | Avenqo Support |
|---|---|---|
| Données | `Dataset` du tenant (ventes, clients...) | `platform_knowledge/` (documentation produit) |
| Tables de conversation | `ai_conversations` / `ai_messages` | `ai_support_conversations` / `ai_support_messages` |
| Outils | 14 outils métier/prédictifs (`build_business_tool_registry`) | 5 outils sûrs en lecture seule (`build_support_tool_registry`) |
| Contexte authentifié | Permissions, plan, capacités, **+ données métier** | Permissions, plan, capacités **uniquement** — jamais de ventes/clients |
| Endpoint | `/api/v1/ai/chat/...` | `/api/v1/support/chat/...` |

Les tables sont physiquement séparées : il n'existe aucune requête possible
qui fasse fuiter une conversation Support AI dans l'historique Business
Copilot ou inversement.

### Outils Support AI (lecture seule)

- `search_avenqo_docs` — recherche mot-clé dans `platform_knowledge/`.
- `get_current_plan` — plan d'abonnement de l'entreprise courante uniquement.
- `get_available_features` — capacités IA activées pour le tenant (réutilise
  `resolve_tenant_capabilities`, Phase 30).
- `get_connection_status` — indique seulement si au moins une source de
  données est connectée (jamais son contenu).
- `get_ai_capability_status` — statut générique (healthy/degraded/
  unavailable), jamais le nom d'un fournisseur.

### Base de connaissances

`backend/app/ai/support/knowledge_base.py` charge des fichiers Markdown
(frontmatter `id`/`title`/`tags`) depuis `platform_knowledge/` (configurable
via `AI_SUPPORT_KNOWLEDGE_ROOT`). `PlatformKnowledgeRetrievalService`
effectue un scoring par recouvrement de mots-clés — pas d'embeddings ni de
base vectorielle dans cette phase (limitation documentée ci-dessous).

### Codes d'erreur sûrs

`backend/app/ai/support/error_codes.py` associe des codes internes
(`DATA_IMPORT_FAILED`, `MODEL_NOT_AVAILABLE`, `AI_QUOTA_REACHED`,
`PROVIDER_TEMPORARILY_UNAVAILABLE`, `CONNECTION_REQUIRED`) à une explication
en langage clair, jamais un détail technique.

## Resilient AI Gateway

### Composants (`backend/app/ai/llm/`)

- `failure_classification.py` — classe une exception en catégorie
  (`timeout`, `network`, `provider_5xx`, `rate_limited`, `overloaded`,
  `auth_config`, `invalid_request`, `content_rejected`, `quota_problem`,
  `unknown`) en inspectant `exc.__cause__` (les providers Phase 28
  enveloppent déjà toute exception SDK avec `raise ... from exc`).
- `circuit_breaker.py` — `ProviderCircuitBreaker`, un état en mémoire par
  fournisseur ; s'ouvre après N échecs consécutifs (configurable), se
  referme après un cooldown (half-open probe).
- `health.py` — `ProviderHealthRegistry`, snapshot interne
  (healthy/degraded/unavailable/rate_limited/unknown) — jamais exposé au
  frontend, avec latence moyenne observée pour le scoring.
- `model_registry.py` — capacités, fenêtre de contexte, classes coût/latence
  et rate card décimale centralisée par fournisseur/modèle.
- `router.py` — filtre les modèles incompatibles et les classe selon tâche,
  complexité, contexte, capacités, santé, latence, coût, plan et crédits.
- `gateway.py` — `AvenqoAIGateway`, implémente **exactement** l'interface
  `LLMProvider` (Phase 28) et n'appelle jamais plusieurs fournisseurs en
  parallèle.

### Comportement de fallback

1. Un seul modèle primaire compatible est choisi par le routeur. L'ordre
  configuré sert de départage stable et de fallback.
2. En cas d'échec **éligible au fallback** (timeout, réseau, 5xx, rate
   limit, surcharge, inconnu) : retry avec backoff exponentiel + jitter
   borné sur le même fournisseur (`AI_GATEWAY_MAX_RETRIES`), puis passage
   au fournisseur suivant configuré (`AI_FALLBACK_PROVIDER_1`,
   `AI_FALLBACK_PROVIDER_2`).
3. En cas d'échec **non éligible** (clé API absente/config invalide,
   requête invalide, contenu rejeté) : l'erreur remonte **immédiatement**,
   sans masquage — ce n'est jamais un problème "temporaire".
4. Si tous les fournisseurs échouent ou ont leur circuit ouvert :
   `AIProvidersUnavailableError`, traduite par `ChatService`/
   `SupportChatService` en `AIServiceUnavailableError` (503 générique,
   jamais de détail fournisseur).

### Streaming

Le fallback pour `stream()` n'est tenté qu'**avant le premier chunk émis** :
une fois le flux démarré sur un fournisseur, on ne bascule jamais en cours
de route (pour ne jamais dupliquer/mélanger une sortie partielle entre deux
fournisseurs). Limitation documentée ci-dessous.

### Configuration (`backend/app/config/settings.py`)

| Variable | Défaut | Rôle |
|---|---|---|
| `AI_PRIMARY_PROVIDER` | `openai` | Fournisseur primaire |
| `AI_FALLBACK_PROVIDER_1` | _(aucun)_ | 1er fallback (ignoré si pas de clé API) |
| `AI_FALLBACK_PROVIDER_2` | _(aucun)_ | 2e fallback (idem) |
| `AI_GATEWAY_MAX_RETRIES` | `2` | Tentatives sur le même fournisseur |
| `AI_GATEWAY_BASE_DELAY_SECONDS` | `0.5` | Base du backoff exponentiel |
| `AI_GATEWAY_MAX_DELAY_SECONDS` | `4.0` | Plafond du backoff |
| `AI_GATEWAY_CIRCUIT_FAILURE_THRESHOLD` | `3` | Échecs avant ouverture du circuit |
| `AI_GATEWAY_CIRCUIT_COOLDOWN_SECONDS` | `30.0` | Délai avant sonde half-open |
| `AVENQO_PROVIDER_COST_PER_CREDIT_USD` | `0.00030` | Coût fournisseur correspondant à un crédit Avenqo |
| `AI_CREDIT_RESERVATION_TTL_MINUTES` | `1440` | Délai avant restitution atomique d'une réservation abandonnée |
| `AI_MODEL_RATE_CARD` | `{}` | Surcharges JSON des tarifs/activation par provider ou modèle |
| `AI_SUPPORT_KNOWLEDGE_ROOT` | `platform_knowledge` | Dossier de la base de connaissances Support |

### Quota et sécurité

Le quota est réservé atomiquement **avant** tout appel au Gateway. Une seule
exécution peut réclamer un couple tenant/request ID; les doublons sont rejetés
avant le fournisseur. Après succès, chaque tentative est inscrite
dans `tenant_ai_provider_attempts` avec ses tokens, sa latence, son coût réel
et le snapshot des tarifs appliqués. La somme des coûts est convertie par
`ceil(coût / AVENQO_PROVIDER_COST_PER_CREDIT_USD)` puis débitée des crédits
inclus avant les crédits achetés. Le reliquat réservé est restitué au règlement;
une réservation abandonnée est libérée après le TTL configuré. Aucun nom de
fournisseur, clé API ni détail technique n'est exposé au frontend.

## Limitations connues

- Le circuit breaker et le registre de santé sont **en mémoire, par
  process** — pas partagés entre plusieurs workers/instances. Acceptable
  pour cette phase ; une implémentation distribuée (Redis) serait
  nécessaire pour un déploiement multi-workers avec état partagé strict.
- Le fallback de streaming ne s'applique qu'avant le premier chunk.
- La recherche documentaire du Support AI est un scoring par mots-clés
  (pas d'embeddings/vecteurs) — suffisant pour le corpus initial, à
  réévaluer si `platform_knowledge/` grossit significativement.
- Les tarifs par défaut sont des paramètres techniques et doivent être
  contrôlés lors d'un changement tarifaire fournisseur; le journal conserve
  toujours le snapshot effectivement appliqué aux usages historiques.
