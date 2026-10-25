# GitGuardian #38085296 — synthetic test credential

On 2026-10-10, the authenticated GitGuardian workspace showed nine grouped
occurrences in authentication, billing, workspace and Flutter tests. The
registration helpers create synthetic users in temporary test databases;
the Flutter helper supplies a mocked API request. The historical candidate
had already been compared privately with readable production and sandbox
API/PostgreSQL variables, with no matching deployed credential found.

GitGuardian now records this incident as **Ignored — Test credential**.
This is a scoped classification, not a revocation, a detector exclusion,
or a claim that PostgreSQL, WooCommerce or encryption incidents are resolved.
Monitoring remains enabled.

The workspace test fixture was replaced in ccfa173. The remaining five
authentication-test references, one billing-test reference and one Flutter
test reference now use explicitly named ephemeral synthetic credentials.
No historical value is reproduced here and no history was rewritten.

Validation of the follow-up correction: 11 targeted authentication/billing
tests passed, and all three Flutter API-client tests passed. The credential
guard and whitespace check passed. The preceding MFA/rotation revision
d784211 passed all four GitHub Actions jobs (run 38103404368).

This correction does not modify main or deploy any service. The production
credential incidents remain open until their replacements are validated
and the old credentials are effectively revoked.
