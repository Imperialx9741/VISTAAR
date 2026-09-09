VISTAAR — Mobile Completion Plan

Date: 2026-09-03
Status: Planning only. No code changed in producing this document.
Source of truth: direct inspection of `apps/mobile/lib/` and
`apps/backend/src/modules/*/router.py` on the current repository,
cross-referenced against `docs/05-api/api-contracts.md` and approved
ADRs — same verification basis as
`docs/16-mobile/mobile-gap-report-2026-09-03.md` (the immediately
preceding gap report this plan is built from; not re-derived, reused).

iOS/Mac/APNs are excluded from every item below — postponed per
standing project scope, not a gap.

1. Sarthi onboarding

1.1 Profile (view/edit)

| Field | Value |
| :-- | :-- |
| Screen | `SarthiProfileScreen` (new) |
| Role | Sarthi |
| Backend API | `GET /api/v1/drivers/me`, `PATCH /api/v1/drivers/me` (both exist, unused by mobile) |
| Mobile API client | New `driver_api.dart` — no such file exists today |
| Navigation entry | New profile icon in `SarthiHomeScreen`'s `AppBar.actions` |
| UI states | Loading (initial fetch), error (fetch/save failure), form validation (required fields per `UpdateDriverProfileBody`'s actual schema — check that schema before building the form, not guessed here), success confirmation (save), disabled (save button while in-flight) |
| Tests required | Widget test (load → edit → save happy path; validation errors; save failure); `driver_api.dart` unit test (mocked HTTP) |
| Status | **MISSING** |

1.2 KYC / document submission

| Field | Value |
| :-- | :-- |
| Screen | `DriverDocumentUploadScreen` (new) — one entry per required document type, each showing its own status |
| Role | Sarthi |
| Backend API | `POST /api/v1/drivers/me/uploads` (presigned S3 POST, ADR-0065), `POST /api/v1/drivers/me/documents` (submit metadata) |
| Mobile API client | New methods on `driver_api.dart`, plus a **shared** presigned-POST-upload helper (multipart form upload to S3, file as the last field per ADR-0065) — this exact upload mechanic is also needed by §5 (GPS dispute evidence); build it once, shared, not duplicated |
| Navigation entry | From `SarthiProfileScreen` (§1.1) and from the onboarding/readiness flow (§1.4) when a document is missing/rejected |
| UI states | Loading (upload in progress, ideally with progress feedback), empty (no documents submitted yet), error (upload failure, rejected document with the admin's reason if the API returns one — confirm exact response shape before building), success (submitted, pending review), disabled (submit while uploading) |
| Tests required | Widget test per document-status variant (none/pending/approved/rejected); API client test for both the upload-URL request and the metadata submission, mocked |
| Status | **MISSING** — a Sarthi currently has no way to submit KYC documents through the app at all |

1.3 Vehicle management

| Field | Value |
| :-- | :-- |
| Screen | `VehicleListScreen` + `AddEditVehicleScreen` (new) |
| Role | Sarthi |
| Backend API | `GET/POST /api/v1/drivers/me/vehicles`, `GET/PATCH /{vehicle_id}`, `POST /{vehicle_id}/activate`, `POST /{vehicle_id}/deactivate` (all exist, unused by mobile) |
| Mobile API client | New `vehicle_api.dart` |
| Navigation entry | From `SarthiProfileScreen` (§1.1) |
| UI states | Loading, empty (no vehicles yet), error, **confirmation dialog** on activate (BR-122: at most one ACTIVE vehicle — activating a second one changes which vehicle is active; the exact resulting behavior — auto-deactivate the previous one vs. reject — must be confirmed against `VehicleService`'s real code before the dialog's copy is written, not assumed), form validation (registration number format — confirm the real validation rule from `validate_registration_number`/schema, not guessed) |
| Tests required | Widget test (list, add, edit, activate/deactivate incl. the confirmation path); API client test |
| Status | **MISSING** — a Sarthi currently has no way to add or manage a vehicle through the app at all |

1.4 Approval/eligibility journey

| Field | Value |
| :-- | :-- |
| Screen | A readiness/status view — either a dedicated `OnboardingStatusScreen` or a banner/checklist embedded in `SarthiHomeScreen` (implementation-time UX call, not fixed here) |
| Role | Sarthi |
| Backend API | No new endpoint — composes existing `GET /me` (driver + document status) and `GET /vehicles` (vehicle + document status) |
| Mobile API client | Reuses `driver_api.dart` (§1.1) and `vehicle_api.dart` (§1.3) |
| Navigation entry | Shown automatically in place of (or gating) the "Go Online" button whenever the driver isn't yet eligible |
| UI states | Loading, and one state per real readiness condition — documents pending / documents rejected (needs resubmission, links to §1.2) / no active vehicle / vehicle documents pending or rejected (links to §1.3) / fully ready — plus error (fetch failure) |
| Tests required | Widget test per readiness state |
| Status | **MISSING** |

1.5 Go-online readiness (gating)

| Field | Value |
| :-- | :-- |
| Screen | Not a new screen — a change to `SarthiHomeScreen`'s existing Go Online button |
| Role | Sarthi |
| Backend API | `POST /api/v1/drivers/me/online` — **verified directly in `driver/router.py`**: already real, thorough server-side enforcement today (checks required driver-document validity, an active vehicle's existence, its verification status, its operational status, and its own document validity, in that order, raising a specific domain error for whichever condition fails first). No backend change needed. |
| Mobile API client | `driver_availability_api.dart` (existing, unchanged) |
| Navigation entry | n/a — modifies existing flow |
| UI states | The existing error-message display already surfaces whatever the backend rejects with (`_errorMessage` in `SarthiHomeScreen`) — but currently the driver only discovers this by *trying* to go online and reading a raw error string. The improvement: proactively show §1.4's readiness state *before* the driver taps Go Online, so the error becomes a confirmation of what they already knew, not a surprise. |
| Tests required | Widget test: attempting Go Online while ineligible surfaces the specific reason and a way to act on it (e.g. a link to §1.2/§1.3) |
| Status | **PARTIAL** — backend gating is complete and correct; only the proactive mobile-side surfacing is missing |

2. User: Profile + Ride History

2.1 Profile (view/edit)

| Field | Value |
| :-- | :-- |
| Screen | `CustomerProfileScreen` (new) |
| Role | User |
| Backend API | `GET/PATCH /api/v1/customers/me` (exist, unused by mobile) |
| Mobile API client | New `customer_api.dart` — no such file exists today |
| Navigation entry | New profile icon in `UserHomeScreen`'s `AppBar.actions` |
| UI states | Loading, error, form validation, success confirmation, disabled (save while in-flight) |
| Tests required | Widget test; API client test |
| Status | **MISSING** |

2.2 Ride history

| Field | Value |
| :-- | :-- |
| Screen | `RideHistoryScreen` (new) |
| Role | User |
| Backend API | `GET /api/v1/rides` (already integrated — `ScheduledRidesScreen` already calls it with a status filter; history needs the same call with a different filter, e.g. `COMPLETED`/`CANCELLED` — confirm the exact accepted status values against the real endpoint before building, not guessed here) |
| Mobile API client | `ride_api.dart` (existing) — likely no new method needed, reuse the existing list call with a different filter argument |
| Navigation entry | Icon in `UserHomeScreen`, alongside the existing Scheduled Rides entry point |
| UI states | Loading, empty (no past rides), error, pagination/"load more" (the underlying endpoint already supports pagination per api-contracts.md §50 — confirm before assuming infinite-scroll is warranted at typical ride-history volumes) |
| Tests required | Widget test |
| Status | **MISSING** (screen only — backend and API client are already there) |

3. Sarthi: Earnings/transaction details + Penalty/strike history

3.1 Earnings/transaction details

| Field | Value |
| :-- | :-- |
| Screen | `WalletScreen` (existing) |
| Role | Sarthi |
| Backend API | `GET /api/v1/drivers/me/wallet/transactions` — already integrated |
| Mobile API client | `wallet_api.dart` — already exists |
| Navigation entry | Already wired from `SarthiHomeScreen` |
| UI states | Already has loading/error/empty (confirmed in the gap report) |
| Tests required | None required beyond what exists, unless a dedicated earnings *summary* (totals by day/week, distinct from the raw transaction ledger `WalletScreen` already shows) is separately wanted — that would be a new, additive feature, not a gap fix, and is not assumed here (no business rule for it exists to build against) |
| Status | **COMPLETE** — already built; listed here per the owner's own instruction to cover it, not because a gap was found |

3.2 Penalty/strike history

| Field | Value |
| :-- | :-- |
| Screen | `StrikeHistoryScreen` (new) |
| Role | Sarthi |
| Backend API | **Does not exist for a driver's own use.** `list_strikes_for_driver` is composed only in the admin router (api-contracts.md §46.18, Admin Web §4.9) — verified directly: `penalty/router.py` (the module that would own a customer/driver-facing endpoint) has no router at all. **This is a backend gap, not just a mobile one — see §D.** |
| Mobile API client | Cannot be built until the backend endpoint exists |
| Navigation entry | From `SarthiProfileScreen` (§1.1) or `WalletScreen`, once buildable |
| UI states | Loading, empty (no strikes — the common case), error |
| Tests required | Once the backend endpoint exists: widget test + API client test |
| Status | **MISSING**, blocked on a backend gap (§D) |

4. User features: Promotions + Referrals

4.1 Promotions

| Field | Value |
| :-- | :-- |
| Screen | `PromotionsScreen` (new) |
| Role | User |
| Backend API | `GET /api/v1/promotions`, `POST /api/v1/promotions/redeem` (exist, unused by mobile) |
| Mobile API client | New `promotion_api.dart` |
| Navigation entry | Icon/menu item in `UserHomeScreen` |
| UI states | Loading, empty (no active promotions), error, **confirmation dialog** before redeeming, success/failure feedback on redeem |
| Tests required | Widget test; API client test |
| Status | **MISSING** |

4.2 Referrals

| Field | Value |
| :-- | :-- |
| Screen | `ReferralScreen` (new) — show the user's own referral code/link + a share action; a separate "enter a referral code" entry point for a *new* user attaching someone else's code |
| Role | User |
| Backend API | `GET /api/v1/customers/me/referral` (own code), `POST /api/v1/referrals/attach` (exist, unused by mobile) |
| Mobile API client | New `referral_api.dart` |
| Navigation entry | `ReferralScreen` itself: icon/menu item in `UserHomeScreen`. The "attach a code" entry point's exact trigger (during signup vs. a settings action after the fact) is a real product decision that should be confirmed against ADR-0057-adjacent referral rules before building — not assumed here, since inventing the trigger point would risk inventing a business rule. |
| UI states | Loading, error, success (code copied/shared), success/failure on attaching a code (self-referral rejection, already-referred rejection — BR-025 and the unique-constraint behavior already exist server-side and just need surfacing) |
| Tests required | Widget test; API client test |
| Status | **MISSING** |

5. User + Sarthi: GPS dispute + Evidence submission

| Field | Value |
| :-- | :-- |
| Screen | `GpsDisputeScreen` (dispute status + evidence list) + an evidence-submission flow (photo upload or text explanation) — new |
| Role | Both |
| Backend API | `GET /api/v1/rides/{ride_id}/gps-disputes/{dispute_id}`, `POST .../evidence/upload-url` (presigned S3 POST, ADR-0065), `POST .../evidence` (exist, unused by mobile) |
| Mobile API client | New `gps_dispute_api.dart`, reusing the shared presigned-POST-upload helper built for §1.2 |
| Navigation entry | **Needs a real trigger, not assumed here.** A dispute is opened server-side (e.g. after a GPS-verification failure at arrival/completion) — the mobile app currently has no push-notification payload wired to deep-link into a dispute screen, and no "my past rides with an open dispute" indicator anywhere (ties into §2.2's ride history, once built). This entry-point design is real, non-trivial work in its own right, not just "add a screen." |
| UI states | Loading, empty (no evidence submitted yet), error, upload-progress, confirmation before submitting evidence, a visible countdown/deadline for the evidence window (BR/ADR-0032's evidence-submission window — confirm the real configured value before displaying it, not the illustrative placeholder some docs use) |
| Tests required | Widget test per dispute state (open/awaiting evidence/resolved); upload flow test; API client test |
| Status | **MISSING** |

6. Support: case list, detail, later admin replies, proper conversation flow

6.1 Support case list

| Field | Value |
| :-- | :-- |
| Screen | `SupportCaseListScreen` (new) |
| Role | Both |
| Backend API | **Does not exist.** Only `POST /support/cases` (create) and `GET /support/cases/{case_id}` (get one, by id) exist — verified directly in `support/router.py`. There is no list-my-cases endpoint. **Backend gap — see §D.** |
| Mobile API client | Cannot be built until the backend endpoint exists |
| Navigation entry | Icon/menu item in both home screens, replacing the current pattern where a case is only ever reachable immediately after creating it |
| UI states | Loading, empty (no cases yet), error |
| Tests required | Once the backend endpoint exists: widget + API client tests |
| Status | **MISSING**, blocked on a backend gap (§D) |

6.2 Case detail with visible later replies

| Field | Value |
| :-- | :-- |
| Screen | `SupportCaseScreen` (existing, needs real change) |
| Role | Both |
| Backend API | `GET /support/cases/{case_id}` — **already exists and, being a plain GET, already returns whatever the current message thread is on each call.** The gap is not the backend; it's that `SupportCaseScreen` is currently a `StatelessWidget` rendering a single snapshot passed in at navigation time (its own doc comment states this is deliberate today) and never re-fetches. |
| Mobile API client | `support_api.dart` (existing) — its `getCase` method already exists; the screen just needs to actually call it again |
| Navigation entry | From §6.1's list, and still from the post-creation flow |
| UI states | Loading (on refresh), error, and the existing message-thread rendering — converting from `StatelessWidget` to `StatefulWidget` with a manual refresh action (pull-to-refresh or a button) is the concrete change; a polling timer is a further option but adds complexity for a channel that isn't real-time by design |
| Tests required | Widget test: refreshing after construction shows a newly-added message |
| Status | **PARTIAL** — the data already exists and is reachable; only the screen's own refresh behavior needs to change |

6.3 Proper conversation flow (customer sends a follow-up message)

| Field | Value |
| :-- | :-- |
| Screen | Extension of `SupportCaseScreen` (§6.2) — a message-compose field |
| Role | Both |
| Backend API | **Does not exist.** No endpoint anywhere accepts a customer follow-up message on an existing case — confirmed directly, and `support_api.dart`'s own doc comment already states this. **This may be a backend gap, or it may be an intentional product decision that this channel is one-shot and any follow-up happens through a different channel (phone, etc.) — genuinely unclear from the current documentation, and this plan does not guess which. Needs an explicit owner decision before scoping the backend work — see §D.** |
| Mobile API client | Cannot be built until the backend question above is resolved |
| UI states | n/a until scoped |
| Tests required | n/a until scoped |
| Status | **MISSING**, blocked on an open product question (§D) |

7. UI/UX — cross-cutting standards

Applies to every screen above (new and existing) rather than one row per screen. Current state, verified directly by grepping every screen file for the relevant pattern (loading indicators, `_errorMessage`/`errorMessage` fields, empty-state text):

| Standard | Screens that already meet it | Screens that don't (existing) | Applies to all new screens in §1-6 |
| :-- | :-- | :-- | :-- |
| Navigation | All 17 existing screens have a real entry point | — | Every new screen needs one explicitly designed, not assumed (flagged per-item above where it's non-trivial) |
| Loading states | `book_ride_screen`, `ride_execution_screen`, `ride_status_screen`, `scheduled_rides_screen`, `wallet_screen`, `location_permission_screen` | `user_home_screen` (static, doesn't need one), `support_case_screen` (needs one once §6.2 adds refresh) | Required |
| Empty states | `sarthi_home_screen`, `book_ride_screen`, `ride_execution_screen`, `ride_status_screen`, `scheduled_rides_screen`, `support/contact_support_screen`, `wallet_screen` | — (no existing screen both needs one and lacks it) | Required for every list-rendering screen (§1.3, §1.4, §2.2, §3.2, §4.1, §5, §6.1) |
| Error states | `otp_verify_screen`, `phone_entry_screen`, `sarthi_home_screen`, `book_ride_screen`, `ride_offer_screen`, `scheduled_rides_screen`, `contact_support_screen`, `recharge_wallet_screen`, `wallet_screen` | `user_home_screen` (static), `support_case_screen` (needs one once §6.2 adds refresh) | Required |
| Disabled states | Present on most action buttons (`PrimaryButton.isLoading` pattern) | Not audited screen-by-screen at this level of granularity in this pass | Required on every submit/save/redeem/activate action across §1-6 |
| Confirmation dialogs | **None found anywhere in the app** — e.g. cancelling a ride currently proceeds with no "are you sure?" step | Every existing destructive action | Required specifically for: vehicle activate/deactivate (§1.3), promotion redeem (§4.1), evidence submission (§5) — and worth adding retroactively to ride cancel/driver-cancel, which currently have none |
| Form validation | Present in `book_ride_screen`, `otp_verify_screen`, `phone_entry_screen` (coordinate/OTP/phone format checks) | n/a — no other existing screen has a form | Required for every new form: profile edit (§1.1, §2.1), vehicle add/edit (§1.3), document metadata (§1.2) |
| Consistency/polish | Shared `PrimaryButton` widget already used everywhere — a real, existing consistency mechanism | No shared empty-state, error-banner, or confirmation-dialog widget exists yet — each screen re-implements its own error `Text` styling inline | Build shared `EmptyStateWidget`/`ErrorBanner`/`ConfirmationDialog` widgets once, use them everywhere in §1-6, rather than each new screen re-inventing its own |
| Accessibility | Not audited in this pass — no existing test asserts on semantics/contrast/screen-reader labels anywhere in the current test suite | Same | A real, separate audit pass is needed before this can be scored per-screen; not assumed complete or incomplete without checking, and not checked in this planning pass |
| Android production readiness | Release signing is done (ADR-0064); Play Store publishing entity decided (item 15, 2026-09-03) | Real-device FCM delivery still unverified (tracked separately, ADR-0052 §9 / testing-strategy.md §105); store listing assets/screenshots not yet produced (`app-store-submission-checklist.md` still has open `[NEED]` items) | n/a — tracked in the existing submission checklist, not duplicated here |

A. Final list of missing mobile functionality

- Sarthi profile (§1.1)
- KYC/document submission (§1.2)
- Vehicle management (§1.3)
- Onboarding/approval readiness view (§1.4)
- User profile (§2.1)
- Ride history (§2.2)
- Sarthi strike/penalty history (§3.2 — blocked on a backend gap)
- Promotions (§4.1)
- Referrals (§4.2)
- GPS dispute + evidence submission (§5)
- Support case list (§6.1 — blocked on a backend gap)
- Support follow-up messaging (§6.3 — blocked on an open product question)

B. Final list of missing UI/UX work

- Go-online proactive readiness surfacing (§1.5)
- Support case screen refresh/live-reply behavior (§6.2)
- Confirmation dialogs — none exist anywhere today; needed for vehicle activate/deactivate, promotion redeem, evidence submission, and retroactively for ride cancellation
- Shared `EmptyStateWidget`/`ErrorBanner`/`ConfirmationDialog` widgets — don't exist yet, every new screen in this plan should use them instead of re-implementing inline styling
- A full accessibility audit — not yet done at all, separate from this plan's own scope
- Store-listing assets/screenshots and remaining `app-store-submission-checklist.md` `[NEED]` items — tracked there, not duplicated here

C. Recommended implementation order

1. **Sarthi onboarding (§1.1-1.5)** — highest priority. Without it, no Sarthi can become eligible to drive without manual admin intervention per driver; this is the single largest block on the platform actually functioning at any real scale.
2. **Shared UI primitives** (`EmptyStateWidget`/`ErrorBanner`/`ConfirmationDialog`, part of §7) — build alongside step 1, since §1's new screens are the first real consumers and building the primitives first avoids rebuilding §1's screens later.
3. **User profile + ride history (§2)** — core completeness for the paying role.
4. **Support case list + conversation flow (§6)** — meaningfully improves support quality; §6.3's backend/product question should be raised with the owner early in this phase so it doesn't block the rest of §6.
5. **Sarthi strike/penalty history (§3.2)** — raise the backend gap (§D) early enough that it isn't a late surprise, but the mobile screen itself is low-complexity once unblocked.
6. **GPS dispute + evidence submission (§5)** — important safety-net feature; lower frequency of use than the above, but real disputes will happen before a full production launch, so this should ship before that, not after.
7. **Promotions + Referrals (§4)** — growth/marketing features; reasonable to sequence last among the *missing functionality* items unless the business specifically wants a referral or promotion campaign at launch, which is not indicated anywhere in current scope.
8. **Accessibility audit + Android production-readiness remainder** — can run in parallel with steps 3-7 rather than blocking them, since neither depends on the other screens existing first.

D. Backend API gaps that must be completed before the mobile feature can be built

- **`GET /api/v1/support/cases`** (list the current account's own cases) — does not exist. Blocks §6.1.
- **A driver-facing strikes/penalty-history endpoint** — does not exist (`list_strikes_for_driver` is admin-only today). Blocks §3.2.
- **A customer/driver follow-up-message endpoint on an existing support case** — does not exist. Blocks §6.3, but first needs an owner decision on whether this channel should support follow-ups at all, or whether a real reply happens through a different channel — not assumed either way in this plan.
- Not a missing endpoint, but a fact to confirm before building, not assume: the exact accepted `status` filter values for `GET /api/v1/rides` (§2.2 needs this to distinguish "history" from "scheduled"), the real `UpdateDriverProfileBody`/`UpdateCustomerProfileBody` field lists (§1.1/§2.1's form fields), the real vehicle-activation behavior when a second vehicle is activated (§1.3's confirmation-dialog copy), and the real configured evidence-submission-window value (§5) — all exist in the codebase already and just need to be read at implementation time, not guessed at in this planning pass.
