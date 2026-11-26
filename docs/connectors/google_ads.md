# Google Ads

- Readiness: Configuration and a separately verified marketing integration are required.
- Environment: use tenant-scoped Sandbox configuration and server-side credentials; never expose credentials to the browser.
- Acceptance: verify authorization, tenant isolation, provider connectivity and actual module behavior before claiming operational readiness.

- Auth method: `oauth2`.
- Environment: `GOOGLE_ADS_DEVELOPER_TOKEN, GOOGLE_ADS_CLIENT_ID, GOOGLE_ADS_CLIENT_SECRET`.

