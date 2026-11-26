# Google Calendar

- Readiness: Dedicated CRM calendar integration; the commerce registry does not register a calendar adapter.
- Environment: use tenant-scoped Sandbox configuration and server-side credentials; never expose credentials to the browser.
- Acceptance: verify authorization, tenant isolation, provider connectivity and actual module behavior before claiming operational readiness.

- Auth method: `oauth2`.
- Environment: `GOOGLE_CALENDAR_CLIENT_ID, GOOGLE_CALENDAR_CLIENT_SECRET, GOOGLE_CALENDAR_REDIRECT_URI`.

