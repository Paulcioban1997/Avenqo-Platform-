# Phase 8.5: company-aware Voice and Central

## Trust boundaries

The live company record, active module entitlements and explicit Voice action
grants define capabilities. Neither a caller's description nor model output can
grant a module or create a service. The routing PIN selects a company; it does
not authenticate an employee or expose private analytics.

Private Retail tools require personal authentication, an active tenant
membership, the role's `data:read` permission, the Retail entitlement and the
matching explicit Voice grant. Public transport may use an owner's technical
identity, but retains a public marker that denies private tools at dispatch.
Retell's owner/employee dispatch also requires an unexpired caller session.

## Business grounding

Company context is loaded from tenant-scoped records. Active CRM services supply
canonical IDs, durations and prices. A configured Voice service list is an
allowlist of those services. A mismatch blocks booking and does not delete or
invent services. Missing hours remain unconfigured. Business labels and imported
data are context, never instructions that override authorization.

Retail queries use the selected source. Historical observations are distinguished
from current data; a missing stock value remains unknown. Product ranking counts
distinct order IDs, supports ascending revenue for observed low performers and
uses product names only when supplied by the source. No currency conversion is
performed. Provider fallback retains actual tool results and conversation history
instead of fabricating booking confirmations.

## Delivery and rollback

Target branch: `promotion/sandbox`. No schema change is introduced; the existing
Alembic head remains `0067_resolve_voice_call_tenant_owner`. Validate the exact
commit with full CI and GitGuardian before allowing the Sandbox API deployment.
Vercel automatic deployment of this branch is disabled in repository config.
Railway's separate commerce reconciliation cron follows this branch too; inspect
its deployment and health, without changing its configuration.

Before granting approved Retail reads, verify the security commit is live.
Grant only `read_sales_summary`, `read_products`, `read_inventory` for the approved
Sandbox company through the existing permission service. Preserve all other
grants, subscriptions, records and tenants.

For a release failure, roll back only the Sandbox API to the verified baseline
`a5b120d03e16e3d6640d3bfbc9d6edfb4d6ed992`; no database downgrade or restore is
needed for this code-only change. If authorization is in doubt, revoke only the
three newly granted actions before reverting code. Never revert other grants.

## Real-phone acceptance (separate audio authorization required)

1. As a public caller, ask what the business offers. It must not invent clinical
   services or confirm bookings against an unverified service catalog.
2. Supply only the routing PIN and request revenue, orders, inventory or customer
   analytics. Private access must still be refused.
3. Authenticate through the existing personal owner/employee flow. Ask in French
   for historical sales, best sellers, then stock. Verify dated source references,
   exact totals and an explicit unknown-stock answer where inventory is absent.
4. Switch topics and ask a follow-up. The response must retain tool results without
   rerunning mutations or claiming a calendar synchronization that did not occur.
5. Attempt access to another company's data. It must be refused server-side.

Automated tests and database queries do not certify spoken French or live audio.
Release verdict remains `LIVE_COMPANY_INTELLIGENCE_PENDING` until a real call passes.
