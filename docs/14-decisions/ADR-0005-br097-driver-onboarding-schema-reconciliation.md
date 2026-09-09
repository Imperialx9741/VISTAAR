ADR-0005 — BR-097 Driver Onboarding Requirements vs. Driver Database Schema

Status: Decision required for items D — NOT decided by this record for
those items. Items classified A/B are settled by cross-referencing
already-approved documents; item classified C is flagged, not resolved.
Date recorded: 2026-08-21
Deciders: Recorded from repository evidence during the Phase 2 / Task 2.3
follow-up (Driver Profile Design Clarification). Does not invent any new
business requirement, database field, or module — see business-rules.md
§44/§45's change-policy and source-of-truth rules, which this record
follows rather than bypasses.

1. Problem

[business-rules.md BR-097](../02-business/business-rules.md) and
[PRD.md §9](../01-product/PRD.md) (near-identical text) describe driver
onboarding as needing:

    Personal:  Full name, Mobile number, Date of birth, Address, Profile photo
    Identity:  Government identification, Driving licence
    Vehicle:   RC, Insurance, Vehicle registration number, Vehicle photo, Vehicle category
    Payment:   UPI/payment details where required

[database-design.md §7.1](../04-database/database-design.md)
(`driver.drivers`, built in Task 2.3) only has: `full_name`,
`profile_photo_uri`, `verification_status`, `operational_status`,
`strikes`. Several BR-097 items have no column anywhere in the
documented schema. Task 2.3 correctly did not invent columns to close
this gap; this ADR classifies each item instead.

2. Source documents reviewed

business-rules.md BR-097, database-design.md §7 (Driver Tables) and §8
(Vehicle Tables), domain-design.md §7 (Driver Domain) and §8 (Vehicle
Domain), api-contracts.md §9 (Driver Profile APIs, including the "Submit
Driver Document" example), implementation-readiness.md (no dedicated
Driver Module architecture section exists there to consult).

3. Classification

| BR-097 item | Class | Reasoning |
|---|---|---|
| Full name | **A** | `driver.drivers.full_name` — implemented, Task 2.3. |
| Mobile number | **A** | `identity.accounts.phone` — implemented, Task 2.1. Owned by the Identity domain, not Driver, per domain-design.md §7.6 ("Driver does not directly own... "); correctly not duplicated onto `driver.drivers`, consistent with Task 2.3's explicit instruction not to duplicate the identity table. |
| Profile photo | **A** | `driver.drivers.profile_photo_uri` — implemented, Task 2.3. |
| Government identification | **B** | Matches `driver.documents.document_type` (database-design.md §7.2) exactly — a document-verification-task concern, not a `driver.drivers` profile field. Confirmed by api-contracts.md §9's own "Submit Driver Document" example already using `document_type` for this kind of record. |
| Driving licence | **B** | Same as above — api-contracts.md §9's example payload literally uses `"document_type": "DRIVING_LICENSE"`. |
| RC | **B** | Vehicle domain (domain-design.md §8 "vehicle documents"), Task 2.4 / a later document-verification task. Not Driver domain's concern per domain-design.md §7.6. |
| Insurance | **B** | Same as RC — vehicle document, Task 2.4 / later. |
| Vehicle registration number | **B** | `vehicle.vehicles.registration_number` (database-design.md §8.1) — Task 2.4, already has a named column waiting for it. |
| Vehicle photo | **B** | Vehicle document, Task 2.4 / later. |
| Vehicle category | **B** | `vehicle.vehicles.category` (database-design.md §8.1) — Task 2.4, already has a named column waiting for it. |
| Date of birth | **C** | No column in `driver.drivers`, `driver.documents`, or anywhere else in database-design.md. Not clearly a "document" the way government ID/driving licence are (BR-097 lists it under "Personal", not "Identity"), so it does not cleanly fall into the same bucket as the B items above. Simplest resolution would likely be adding it to `driver.drivers` (matching where `full_name`/`profile_photo_uri` already live), but that is a database-design.md change this ADR does not make. |
| Address | **D** | No column anywhere, and — unlike DOB — genuinely ambiguous whether it should be a direct profile field (like full_name) or something captured only as evidence within a submitted KYC document (many onboarding flows never store a free-text address at all, relying on the uploaded ID document instead). Neither database-design.md nor domain-design.md states which. |
| Payment/payout (UPI) details | **D** | Real, documented tension rather than a simple gap: BR-097/PRD §9 describe collecting payout details at onboarding, but [business-rules.md BR-017](../02-business/business-rules.md) states "Drivers cannot withdraw VISTAAR wallet funds to a bank account or UPI during MVP", and domain-design.md §22 confirms advertisement payouts "enter Wallet as a credit" (not a bank/UPI payout) with "Exact payout/settlement provider" explicitly still TBD. It is unclear whether BR-097's "payment details" onboarding field is: (a) dead/future-scoped and not needed for MVP at all, (b) referring to something else (e.g. a UPI source for wallet recharge, which would then duplicate BR-016's already-documented recharge flow rather than being a distinct driver-profile field), or (c) intentionally collected early in anticipation of a post-MVP payout mechanism. No document resolves this. |
| "Exact KYC requirements ... final compliance review" | — | Not classified — PRD.md §9 and BR-097 both already explicitly mark the *entire* KYC requirement list as provisional pending "applicable Indian requirements and final compliance review." This is independent confirmation that BR-097's list was never intended as a final, implementable field spec — supporting evidence for why Task 2.3 was correct not to encode it into the schema. |

4. Decision

**No schema, code, or business-rule change is made by this ADR.** Items
classified A are already correctly implemented. Items classified B are
correctly deferred to Task 2.4 (vehicle) and the not-yet-scheduled
document-verification task — this ADR records that mapping so it does
not need to be re-derived later, but does not itself schedule or
implement those tasks.

Items classified **C** (Date of birth) and **D** (Address; Payment/payout
details) remain **explicitly unresolved**. Per business-rules.md §44's
change policy, closing them requires:

1. An explicit business decision recorded in business-rules.md (whether
   these are required at MVP onboarding at all, and for Payment/payout
   specifically, reconciling the tension with BR-017 described above).
2. A corresponding database-design.md schema addition (most likely new
   columns on `driver.drivers` for DOB/address if they are confirmed as
   direct profile fields, or explicit confirmation they belong to
   `driver.documents` instead).
3. An api-contracts.md update to whichever endpoint(s) end up owning
   them.

This ADR does not perform any of those three steps — it only establishes
that they are needed and exactly what question each one must answer.

5. Consequences

- `apps/backend/src/modules/driver/` is unchanged by this ADR — it
  remains correctly scoped to the fields it already implements (class A).
- Vehicle-related items (class B) should be re-verified against this
  table when Task 2.4 (Vehicle) is scoped, so nothing here is silently
  dropped.
- Document-related items (class B) should be re-verified against this
  table when a document-verification task is scoped.
- Class C/D items must not be implemented by inventing a value or schema
  — any future task touching driver onboarding fields should link back
  to this ADR rather than re-deciding ad hoc.
