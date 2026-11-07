# Avenqo P0 founder action checklist — 2026-11-05

## Updated after branch publication

- [x] Implementation owner published `feat/p0-enterprise-contracts-ceo-command-center` at `4e4e213`; original PR #87 remains unchanged.
- [ ] Review the separate remediation PR after its CI is available; keep it unmerged while the NO-GO gates remain.
- [ ] Confirm a disposable PostgreSQL environment for migration and concurrency tests without touching active databases.
- [ ] Approve legal templates, provider identity and commercial catalog only through the normal independent review; no code flag has been activated in Production.

- [ ] Ask the implementation owner to publish the reviewed feature branch and confirm its SHA; PR #87 currently ends at `ed07cf3`, before the local `4e4e213`. The audit remains local because its base commit is not on GitHub; no audit PR was opened.
- [ ] Ask implementation owner to resolve the P0 signing, wet-ink, legal-gate and existing-customer access findings before requesting a new release review.
- [ ] Confirm canonical Stripe prices, module entitlements, included credits and optional credit packs. Current reconciler text does not match the approved extra-credit packs.
- [ ] Arrange qualified review of FR/EN templates, Quebec/Canadian privacy and electronic-signature evidence. Keep templates unpublished and incorporation unverified until independently established.
- [ ] Require a disposable PostgreSQL migration rehearsal with historical records, evidence retention and rollback checks.
- [ ] Accept the full Sandbox workflow only after tenant attack tests, Stripe TEST cases, PDF byte validation, dashboard reconciliation and owner sign-off pass.
- [ ] Grant separate, explicit authorization for any eventual Production merge, deployment, commercial activation or real customer signing.

Current founder decision: **do not activate or promote this implementation**. A review of the focused audit fix is the next safe action.
