# Quotas d'usage IA Avenqo

## Objectif

Le Business Copilot Avenqo agrège l'usage IA d'un tenant (messages,
tokens LLM, appels d'outils, appels d'outils prédictifs) sous UN seul
compteur "Avenqo AI", indépendamment du fournisseur LLM réellement utilisé
en coulisse (OpenAI, Anthropic, Gemini). Aucune erreur de quota/facturation
propre à un fournisseur n'est jamais exposée au tenant : seule
`AIQuotaExceededError` (message générique et sûr) peut être renvoyée.

## Composants

- `backend/app/models/ai_usage.py::TenantAIUsage` — une ligne par tenant et
  par période de facturation mensuelle (`billing_period`, format `YYYY-MM`),
  avec les compteurs `ai_requests_count`, `llm_tokens_count`,
  `tool_calls_count`, `predictive_requests_count`.
- `backend/app/ai/usage/policy.py::AIQuotaPolicy` — résout la limite
  configurée pour un plan (`demo`/`professional`/`enterprise`/
  `custom_enterprise`) et une métrique donnée. **Aucune limite n'est
  définie par défaut** : tant qu'une limite n'est pas explicitement
  configurée via `AI_QUOTA_LIMITS`, la métrique correspondante est
  considérée non plafonnée. Cela permet d'activer les quotas
  progressivement (par plan, par métrique) sans bloquer les tenants
  existants et sans inventer de chiffre commercial.
- `backend/app/ai/usage/service.py::AIUsageService` — vérifie
  (`ensure_quota_available`, appelé AVANT tout appel LLM/outil) et
  incrémente (`record_usage`, appelé APRÈS un appel réussi) l'usage.
- `backend/app/ai/usage/exceptions.py::AIQuotaExceededError` — seule
  exception de dépassement de quota vue par le reste de l'application.

## Métriques reconnues

| Métrique | Description | Appliquée aujourd'hui |
| --- | --- | --- |
| `monthly_ai_requests` | Nombre de messages/requêtes IA par mois | Oui (gating avant appel LLM) |
| `monthly_llm_tokens` | Total de tokens LLM (input+output) par mois | Suivi (comptage), pas de blocage actif |
| `monthly_tool_calls` | Nombre d'exécutions d'outils par mois | Suivi (comptage), pas de blocage actif |
| `monthly_predictive_requests` | Nombre d'appels à des outils prédictifs par mois | Suivi (comptage), pas de blocage actif |
| `max_concurrent_ai_requests` | Requêtes IA simultanées par tenant | Réservé (non appliqué) |
| `max_conversation_history` | Messages conservés dans l'historique envoyé au LLM | Réservé (non appliqué) |

Conformément à l'exigence Phase 31, toutes les limites n'ont pas besoin
d'être activées immédiatement : seule `monthly_ai_requests` bloque
aujourd'hui un appel, les autres métriques sont suivies pour une
activation future sans migration de schéma supplémentaire.

## Configuration

`AI_QUOTA_LIMITS` (JSON) dans `backend/.env` :

```json
{
  "demo": {"monthly_ai_requests": 200},
  "enterprise": {"monthly_ai_requests": 5000}
}
```

Un plan absent de la configuration reste non plafonné. Enterprise/Custom
Enterprise ne sont **jamais** automatiquement illimités par le code : une
limite contractuelle doit être configurée explicitement si elle doit être
appliquée.

## Intégration `ChatService`

`ChatService.send()` et `ChatService.stream()` appellent
`AIUsageService.ensure_quota_available(tenant_id, plan_code)` avant tout
appel à l'orchestrateur/fournisseur LLM. En cas de dépassement :

- `send()` laisse remonter `AIQuotaExceededError` (traduite en HTTP 429
  par `backend/app/routers/ai_chat.py`).
- `stream()` émet un unique événement SSE `error` avec un message générique
  et ne persiste rien.

Après un appel réussi, `AIUsageService.record_usage(...)` incrémente les
compteurs à partir du `token_usage` déjà capturé par
`backend/app/ai/llm/schemas.py` (agrégé via `tokens_from_usage`,
indépendant du format exact du fournisseur).

## Tests

```powershell
pytest tests/backend/test_phase31_ai_quota.py -q
```

Couvre : résolution des limites par plan, isolation stricte de l'usage
entre tenants, dépassement de quota contrôlé (aucun détail de fournisseur
exposé), plans Demo/Professional/Enterprise/Enterprise-configuré, suivi
d'usage indépendant du fournisseur, et intégration bout-en-bout dans
`ChatService.send()`/`stream()`.
