# Google Calendar

- Readiness: `AVAILABLE`; customer status `AVAILABLE` (crm).
- Auth method: `oauth2`.
- Capabilities: `customers, incremental_sync`.
- Environment: `GOOGLE_CALENDAR_CLIENT_ID, GOOGLE_CALENDAR_CLIENT_SECRET, GOOGLE_CALENDAR_REDIRECT_URI`.
- Acceptance: configure tenant-scoped credentials, verify connection health check, execute incremental sync, and confirm strict `company_id` isolation across analytics and Central AI.
