# Calendar cross-origin OAuth repair

Google Cloud retains one stable authorized callback per environment:
`https://avenqo-platform-sandbox.up.railway.app/api/v1/crm/calendar/google/callback`.
Production client, redirect and secrets are unchanged.

The authenticated auth-url request supplies its web origin. The API checks an exact
operator-managed `GOOGLE_CALENDAR_RETURN_ORIGINS` allowlist (plus existing CORS and
frontend origins), includes that origin in signed ten-minute tenant/user state,
and persists only the state hash. It sets the original HttpOnly, Secure, Lax
browser binding cookie on the web origin through the existing proxy.

Google redirects to the stable API. It verifies the signature, expiration and
unconsumed tenant/user row under RLS. Without the browser cookie it redirects the
single-use authorization code to the signed/allowlisted initiating web origin's
`/api/v1/crm/calendar/google/relay`. The Next server route forwards only the binding
cookie and code/state to the same API callback. The API requires matching binding,
consumes the row under lock, exchanges the code, verifies real Calendar read
access and stores encrypted provider credentials for the state-bound company.
A replay, different browser, altered state or unlisted return origin fails closed.
The relay never follows upstream redirects or returns provider credentials.
All redirects use no-store and no-referrer. Never log OAuth query strings.
No access/refresh token is included in a browser URL.

Successful return goes to the initiating origin's CRM connections tab, rather
than a global stale Preview URL. The web deployment address is not a Google
registered callback. Deploy a stable branch alias and add only that exact alias
to the Sandbox return allowlist. Start a fresh transaction after deploying;
previous states cannot be reused.

CONNECTED is recorded after a successful Calendar API read; rejected grants stay
RECONNECT_REQUIRED. Decryptable ciphertext alone never restores CONNECTED.
Transient provider errors remain ERROR. All existing appointments are preserved.

Credit ledger reads now use a local BillingService dependency without Stripe.
Payment endpoints retain their mandatory Stripe gateway. Quotas, ledger entries,
existing balances and commercial prices are not changed by this fix.
