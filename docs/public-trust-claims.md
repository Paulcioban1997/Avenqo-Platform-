# Public Trust Copy Evidence

Scope: public landing sections, `/trust`, `/privacy`. This is a code-evidence review, not an external security audit or legal opinion.

## Implemented And Publicly Claimed

- Tenant-scoped context: `backend/app/dependencies/auth.py:get_tenant_context`, `backend/app/ai/chat/conversation_service.py:get/messages`, `backend/app/ai/tools/contracts.py:ToolExecutionContext`. Identity determines organization context; copy does not promise dedicated databases or absolute isolation.
- Role, entitlement, agent and capability checks: `backend/app/ai/tools/authorization.py:authorize`, `backend/app/ai/central/service.py:_tool_scope_for_request`. Copy limits this to supported workflows.
- Human confirmations and mutation idempotency: `backend/app/ai/tools/executor.py:execute`, `backend/app/ai/tools/idempotency.py`. Confirmations bind to the action; supported mutations have execution receipts. This is not a promise that every application mutation uses AI confirmation.
- Usage attribution: `backend/app/ai/usage/service.py`, `backend/app/models/ai_usage.py:TenantAIProviderAttempt`. Tenant, conversation, agent, provider, model and usage fields exist. No internal IDs are displayed publicly.
- Configured multi-model routing: `backend/app/ai/llm/router.py`, `factory.py`, `gateway.py`, `health.py`. Candidate compatibility and availability are considered. No provider is labelled connected on these pages.
- Privacy controls: scoped retrieval/context and server-derived tool authorization limit unnecessary data exposure. This does not assert zero knowledge, provider non-training, perfect minimization or no external processing.
- Privacy categories: account/organization models; dataset import/storage and AI conversation messages; server integration credentials; operational/audit logs; Stripe references/invoices; `web/src/proxy.ts` authentication cookies and `locale-context.tsx` local preferences.
- Deletion limits: dataset selection deletion and conversation deletion exist. No universal retention/deletion deadline or immediate removal of backups/provider copies is promised. Requests link to the existing `/contact` route.

## Verified Without Public Absolute Guarantees

- `backend/app/core/security.py` uses password hashing; authentication validates sessions server-side.
- `web/src/proxy.ts` uses HttpOnly production authentication cookies; access credentials are not placed in the new frontend copy.
- `backend/app/core/exception_handlers.py` hides unexpected exception details in client responses; server logs exist. Copy does not claim all historical logs have been audited or are secret-free.
- LawZero research context checked against `https://lawzero.org/`. Text names only; no third-party photos or logos, partnership, endorsement, certification, technology adoption or Scientist AI implementation claim.

## Unsupported Claim Groups Removed From Privacy

1. Declared legal compliance with Quebec Law 25 and PIPEDA.
2. A named privacy/compliance department or unverified dedicated mailbox.
3. SOC standards-based audit requirements.
4. Absolute prohibition on provider training/reuse.
5. Dedicated execution environment/property guarantees.
6. Cryptographic validation of every tenant query.
7. End-to-end encryption and precise TLS 1.3/AES-256 claims.
8. Guaranteed response within 30 days.
9. Universal six-year retention/deletion commitment.
10. Certified destruction/anonymization protocols.

All new visible prose uses `getTranslations(locale).trust` through the existing canonical locale context. Each of the 44 locales has a native catalog; regional locales share appropriate written copy. Human linguistic/legal review remains advisable before treating these explanatory pages as contractual legal terms.