# Google Calendar Avenqo

Avenqo reuses the existing CRM calendar connection and appointment service. Google OAuth tokens are exchanged and encrypted server-side; access and refresh tokens are never returned to the browser.

## Railway configuration

Set these variables on the production `Avenqo-Platform-` service:

- `GOOGLE_CALENDAR_CLIENT_ID`
- `GOOGLE_CALENDAR_CLIENT_SECRET`
- `GOOGLE_CALENDAR_REDIRECT_URI=https://api.avenqo.ca/api/v1/crm/calendar/google/callback`

The redirect URI must match exactly in Google Cloud. No Google secret belongs in Git, Vercel, chat, or frontend JavaScript. Vercel does not need the Google client secret because the OAuth exchange is performed by the FastAPI backend.

## One-time Google setup

1. Open Google Cloud Console: `https://console.cloud.google.com/`.
2. Select or create the Avenqo Google Cloud project.
3. Enable **Google Calendar API**.
4. Configure the OAuth consent screen. Add the requested Calendar scopes and add the pilot Google account as a test user if the app is still in testing.
5. Create an OAuth client of type **Web application**.
6. Add this exact authorized redirect URI:

   `https://api.avenqo.ca/api/v1/crm/calendar/google/callback`

7. Copy the generated client ID to Railway as `GOOGLE_CALENDAR_CLIENT_ID` and the client secret to Railway as `GOOGLE_CALENDAR_CLIENT_SECRET`.
8. Redeploy the backend and open Avenqo CRM > Connections > Google Calendar > Connect Google.
9. Complete Google consent. Avenqo returns to `/crm?google_calendar=connected`; select the calendar through the existing CRM calendar connection controls.

## Runtime behavior

- `GET /api/v1/crm/calendar/connection` reports the tenant-scoped state.
- `GET /api/v1/crm/calendar/google/auth-url` creates a signed, expiring tenant/user-bound OAuth state.
- `GET /api/v1/crm/calendar/google/calendars` lists calendars visible to the connected account without exposing tokens.
- `POST /api/v1/crm/calendar/google/sync` reconciles timed Google events into tenant CRM appointments.
- `PUT /api/v1/crm/calendar/google/selection` selects the tenant's calendar ID.
- CRM create/update/reschedule/cancel calls reuse the stored external event ID. Google failures do not roll back the internal CRM appointment.
- Inbound reconciliation updates existing external IDs, reflects cancellations, and creates a CRM appointment only when exactly one tenant client matches a non-organizer attendee email.
- The connected Google account, all-day events, unmatched events, ambiguous client matches, and soft-deleted appointments are never imported as new appointments.
- The CRM calendar loads inbound reconciliation before reading appointments; OAuth callback also performs an initial reconciliation.
- Free/busy checks use the selected Google calendar when credentials are connected.

Production verification on 2026-09-27 read the connected tenant calendar, reconciled two existing linked events without creating duplicates, and preserved the three active CRM appointments.
