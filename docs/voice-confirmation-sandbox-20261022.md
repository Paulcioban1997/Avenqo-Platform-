# Voice / CRM: explicit confirmation boundary

## Scope and recovered state

PR #63 remains the independent Commerce cron change at
`5a02a807cdf40e12c6daa07b0f02484a6262b712`; its CI run 39618332278 passed.
Do not add this Voice change to its already approved four-field Railway lot.
This branch starts at `promotion/sandbox` / `40af97b63921f7aa4bf8f020d7197fddcc8660ce`.
The last read-only Sandbox API deployment remains `8295dd1`, not `40af97b`.

No telephone provider, tenant record, Google event, secret, migration, volume,
bucket, subscription or running service is changed by this patch.

## Reproduced defect and correction

`CreateAppointmentTool` inferred confirmation from a booking-related phrase
and a date/time. A Voice request such as “Je voudrais un rendez-vous demain
à 14h, mais ne réservez pas encore” therefore entered CRM mutation code with
`confirmed=False`. In the isolated fixture it reached the missing-hours error
instead of requesting confirmation; the equivalent English case also failed.
Romanian already failed closed because the heuristic did not match it.

Voice must now have `confirmed=True` before entering service/client/appointment
processing. This uses the existing confirmation contract; it is not a new
proof-of-consent mechanism. The Central confirmation policy, tenant guard,
canonical service validation and availability checks remain necessary.
Non-Voice Central retains its existing direct-command behavior.

Three regressions use synthetic SQLite tenants and verify that the unconfirmed
French, English and Romanian requests create neither a client nor an appointment.
Existing CRM tests also exercise confirmed creation and the non-Voice shortcut.
The new cases are included in the existing Voice CI suite.

## Delivery gates

- No auto-deploy of this branch to Vercel (all three existing config files).
- No source update of any Railway service by pushing this branch.
- No merge to main, API restart or Sandbox API deploy performed.
- Wait for confirmed Hobby build availability and the required API deployment
  approval. An approved cron deployment does not authorize this API patch.
- Railway security incident QH8L8B3E remains a separate prerequisite: review
  affected credentials and bucket consumer updates without rotating them here.
  The founder's reported S3 replacement is preserved; it is not repeated.
- Production backup execution and restoration have not been retested here.

## Founder acceptance protocol, not a telephone certification

Use only Produits_Ero Sandbox after the API/preview and authorized credentials
are verified. Do not modify its business records just to make this test pass.
Confirm its enabled languages and capabilities before the call. Keep OpenAI as
the telephone provider and HF telephone inference disabled.

1. Products: ask in French which products are available. Compare any names and
   prices with the tenant's selected source. Historical Superstore sales do not
   prove current availability, present-day prices or stock.
2. Inventory: ask for a quantity. Without a connected reliable inventory source,
   the answer must explicitly report unknown inventory. No invented zero.
3. Languages: separate French Canadian, English and Romanian conversations,
   plus explicit topic/language switches only among the tenant's allowed locales.
   Automated text contracts are not ASR/TTS quality certification.
4. Booking: use a configured nonmedical demonstration service, a canonical CRM
   service ID, tenant timezone and a verified free slot. Ask for a booking but
   explicitly withhold confirmation. Check no client/event/appointment is created.
   Then confirm the full proposed details; a separately approved synthetic event
   may be created and checked directly in CRM and Google Calendar. Do not claim
   Google synchronization from an Avenqo HTTP 200 alone.
5. Security: a public caller or routing PIN alone must not disclose private
   analytics. Verify authenticated role and tenant ownership for private tools.
6. Audio: only after separate approval for streaming and paid calling, record
   first-audio latency, interruptions, transcript errors and reconnect behavior.
   Configure a test duration and spend controls; no strict 2 CAD cap is assumed.
   Do not claim a 60-minute call, quality benchmark or LIVE PASS without evidence.

Current verdict: implementation prepared; LIVE_COMPANY_INTELLIGENCE_PENDING.
