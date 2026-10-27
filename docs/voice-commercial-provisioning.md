# Commercial Voice provisioning — prepared, not activated

Standard CA number add-on: **4.99 CAD/month before taxes, no customer setup fee**.
It supplements the existing subscription: Base 29.99 + 4.99 = 34.98 CAD;
Professional 49.99 + 4.99 = 54.98 CAD, before taxes. Voice usage consumes AI
credits separately; no automatic overage charge is introduced.

## Activation gates

All four settings default to false:
`VOICE_COMMERCIAL_ENABLED`, `VOICE_COMMERCIAL_PAYMENTS_ENABLED`,
`VOICE_TELECOM_PURCHASES_ENABLED`, `VOICE_PROVISIONING_WORKER_ENABLED`.
This change does not enable streaming or create Stripe prices, provider orders,
subscriptions, customer payments, or regulatory registrations.

An administrator must approve each country/type/currency tariff at `/admin`.
Its Stripe price must be monthly, fixed, exclusive of taxes, and tagged
`avenqo_kind=voice_number`. Provider cost limits include monthly AND upfront
costs. The customer sees Stripe's initial invoice preview and full recurring
monthly total, including taxes when the account's tax setup is complete.
Existing active subscriptions are preserved; one add-on item is appended.

Also required: explicitly approved Realtime model and actually certified locale
lists (`VOICE_APPROVED_REALTIME_MODELS`, `VOICE_CERTIFIED_REALTIME_LOCALES`),
a dedicated provider key, streaming approval, verified application/webhook,
an active Voice entitlement, and owner consent. GET model access alone does
not certify audio. Availability must come from the tenant's configured CRM;
Google Calendar is not synchronized without valid OAuth.

## Durable flow and failure behavior

Quote → amount-bound consent → unique tenant/number claim → Stripe pending
update → verified signed invoice payment → bounded worker queue → Telnyx
order → provider verification → tenant agent/number binding.
CRM booking tools are granted only after explicit CRM consent and entitlement.
All other grants remain restricted. A caller-provided company ID is ignored.

Stripe writes use stable idempotency keys. An ambiguous Telnyx write is never
repeated: it is reconciled using the persisted customer reference. If the
result cannot be proved, it requires review. Payment failure suspends the
agent. Cancellation stops active calls before number release and removes only
the Voice billing item. Compensation refunds only Voice invoice lines.
Consent, invoice and provider history remain available.

## Migration and rollback

0054 follows 0053 and adds four tables with tenant RLS for orders, claims and
cost receipts. It does not modify existing data. Rehearse 0048 → 0050 → 0054
and a second upgrade on an isolated PostgreSQL database before deployment.
Do not run a destructive downgrade. Disable the four gates before rolling
back code; preserve the additive tables and reconcile any pending payment or
provider purchase. An already purchased number still incurs provider costs
until explicitly released; switching off the queue does not cancel billing.

## Costs and limits

Readonly Telnyx inventory checks on 2026-10-13 returned CA local offers at
1 USD/month + 1 USD upfront. Bank of Canada's latest available observation
(2026-10-09) was 1.4271 CAD/USD. Stripe's public domestic card rate is
2.9% + 0.30 CAD. Conservatively charging that fee to this add-on alone leaves
about 3.12 CAD/month, or 1.69 CAD initially after the provider setup cost,
BEFORE Billing/Tax/FX fees, overhead, refunds and audio usage. Actual account
fees and all these costs must be verified before approving commercialization.
This is a preliminary contribution estimate, not certified profitability.

Sources: https://stripe.com/en-ca/pricing and
https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json?recent=10

Signed `call.cost` receipts are stored separately from AI usage. They require
Telnyx's cost-in-webhooks setting, currently not activated by this patch.
Costs may arrive late. The backend deadline uses total call duration and
requests hangup; a signed hangup event confirms actual termination. A backend
outage can still defeat its timer. No strict combined 2 CAD cap or independent
provider deadline is claimed. Commercial activation requires validation of
provider-side controls, real audio, costs, renewal and cancellation in TEST.

## Deployment separation

This branch is separate from PR #47 and has Vercel auto-deployment disabled.
It is not a Railway service source. Publishing it is not deployment approval.
The PR #47 Sandbox lot remains exactly its branch and pinned commit 2c75b47;
this new engine and migration require their own subsequent deployment approval.
No main merge, production deployment, key rotation or paid test is performed.
