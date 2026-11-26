# Outlook Calendar

- Readiness: Catalog entry for calendar integration; availability of the dedicated module must be verified independently.
- Environment: use tenant-scoped Sandbox configuration and server-side credentials; never expose credentials to the browser.
- Acceptance: verify authorization, tenant isolation, provider connectivity and actual module behavior before claiming operational readiness.

- Auth method: `oauth2`.
- Environment: `MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, MICROSOFT_REDIRECT_URI`.

