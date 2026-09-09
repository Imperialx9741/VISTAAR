VISTAAR Mobile App — Gap Report

Date: 2026-09-03
Source: direct inspection of `apps/mobile/lib/` and
`apps/backend/src/modules/*/router.py` on the current repository at the
time of writing, cross-referenced against approved ADRs/
`docs/05-api/api-contracts.md`. No prior session status used.

Mobile app footprint: 17 screens, 8 API client files, ~3,735 lines. No
`customer_api.dart`, `driver_api.dart`, or `vehicle_api.dart` exist at
all — confirmed by grepping every screen file for direct API calls:
zero exist outside `core/api/*.dart`.

1. Missing/incomplete approved functionality — User role

- Profile view/edit — backend `GET/PATCH /api/v1/customers/me` exists;
  no mobile screen or API client calls it at all.
- Ride history — `GET /api/v1/rides` supports listing;
  `UserHomeScreen`'s own docstring states history is "future work." No
  screen for it.
- Promotions (`GET/POST .../promotions`) — no mobile UI, no API client.
- Referrals (`GET .../referral`, `POST .../attach`) — no mobile UI, no
  API client.
- Rating a driver post-ride — not applicable here: confirmed the
  backend itself has no rating endpoint anywhere in `driver/router.py`
  or elsewhere. Not a mobile gap; nothing exists to wire up yet.
- GPS dispute — filing/evidence submission as a customer — backend has
  3 real endpoints (`GET .../gps-disputes/{id}`, `.../evidence/
  upload-url`, `.../evidence`); zero mobile usage.

2. Missing/incomplete approved functionality — Sarthi role

- Driver profile view/edit — `GET/PATCH /api/v1/drivers/me` exists; no
  mobile screen calls it.
- Document (KYC) submission — `POST /api/v1/drivers/me/uploads` and
  `POST /api/v1/drivers/me/documents` both exist; zero mobile usage. A
  Sarthi has no way to submit KYC documents through the app at all.
- Vehicle management (add/list/edit/activate/deactivate) — all 6
  vehicle endpoints exist; zero mobile usage. A Sarthi has no way to
  add or manage a vehicle through the app at all.
- Consequence: since going online requires an approved vehicle +
  approved documents, there is currently no self-service path from
  signup to "able to go online" anywhere in the mobile app — the only
  route that exists today is an admin manually approving records
  (confirmed via this session's own test-setup helpers, which use
  admin endpoints for exactly this).
- Earnings/transaction history detail, strikes/penalty view — wallet
  transactions are listed (`WalletScreen`), but there's no
  strikes/penalty-history view backed by `penalty` data.
- GPS dispute — evidence submission as a driver — same 3 endpoints as
  above, zero mobile usage.

3. Missing screens

| Screen | Backend support exists? |
| :-- | :-- |
| Customer profile view/edit | Yes |
| Driver profile view/edit | Yes |
| Ride history (User) | Yes (`GET /rides`) |
| Add/manage vehicle | Yes |
| Document/KYC upload | Yes |
| Promotions list/redeem | Yes |
| Referral | Yes |
| GPS dispute detail + evidence upload (both roles) | Yes |
| Driver earnings/strikes detail | Partial (transactions yes, strikes no dedicated endpoint) |

4. Existing screens that are incomplete

- `support_case_screen.dart` — explicitly a one-time static view by its
  own doc comment: no refresh, no way to see an admin's later reply
  once it arrives. Self-documented as intentional, but it is an
  incomplete conversation flow.
- `sarthi_home_screen.dart` — location updates and offer polling are
  foreground-only (`Timer.periodic`, own doc comment); no Android
  foreground service or iOS background location mode, so availability
  silently stops the moment the app is backgrounded.
- `user_home_screen.dart` — pure static menu (Book a Ride + 2 icons); no
  dynamic state at all.

5. Incomplete navigation flows

- No route from either home screen into a profile/vehicle/document flow
  — because none exists to route to.
- `RideOfferScreen`'s own comment admits it doesn't know whether the
  backend already excludes a driver with an active ride from new
  offers — a client-side guard exists, but the flow's correctness
  against the backend is explicitly unverified.
- Support: create-case → static confirmation, with no path back into
  that case later (no "my support cases" list screen either — only
  `POST /cases` and `GET /cases/{id}` are wired, no listing endpoint
  call).

6. Missing UI/UX states

- `UserHomeScreen`: no loading, error, or empty state of any kind
  (static content only).
- `SupportCaseScreen`: no loading/error/empty (receives data already
  fetched by the previous screen; no state of its own).
- Across the whole app: no screen has a disabled state pattern beyond
  basic button-disable-while-busy; no dedicated confirmation-dialog
  pattern for destructive actions (e.g., cancelling a ride goes
  straight through, no "are you sure?" step anywhere).
- No profile/vehicle/document screens exist, so their loading/error/
  empty states don't exist either (compounding item 3).

7. Backend APIs — integrated into mobile vs. not

Integrated (confirmed via direct URL-string grep in `core/api/*.dart`):
OTP request/verify, driver online/offline/location, ride create/list/
get/cancel/driver-cancel/arrived/otp-refresh/start/complete/
pickup-change/destination-change(+confirm), ride-offers list/accept/
reject, wallet balance/transactions/recharge/recharge-confirm, device
token register/unregister, SOS, support case create/get.

Not integrated (endpoint exists, zero mobile calls): customer profile
GET/PATCH, driver profile GET/PATCH, driver document upload/submit, all
6 vehicle endpoints, promotions list/redeem, referral get/attach, all 3
GPS-dispute endpoints, `POST /refresh` (token refresh) and `POST
/logout` (identity module).

8. Implemented at code/API level, no usable mobile UI

Exactly the "not integrated" list in §7 — every one of those backend
endpoints is real, tested, documented code with zero corresponding
mobile screen or API client call.

9. Correctly postponed per approved decisions — NOT counted as gaps
   above

- Everything iOS/Mac/APNs (standing instruction — Android is the only
  production target).
- WhatsApp notifications (BSP not yet selected).
- VAHAN/SARATHI integration (official API docs pending).
- SBI payment gateway (Razorpay test-only is the approved current
  state).
- Background/foreground-service location tracking implementation
  itself is flagged as future native work in the code's own comment,
  distinct from it being "missing" — explicitly scoped out for this
  increment, not silently dropped.
- Admin-side functionality (admin-web is a separate app; not in
  `apps/mobile` scope).

10. Final table

| Item | Role | Status | File/Screen | What remains |
| :-- | :-- | :-- | :-- | :-- |
| OTP login | Both | COMPLETE | `auth/phone_entry_screen.dart`, `auth/otp_verify_screen.dart` | — |
| Role selection | Both | COMPLETE | `auth/role_selection_screen.dart` | — |
| Book a ride | User | COMPLETE | `rides/book_ride_screen.dart` | — |
| Scheduled rides | User | COMPLETE | `rides/scheduled_rides_screen.dart` | — |
| Ride status/tracking | User | COMPLETE | `rides/ride_status_screen.dart` | — |
| Go online/offline + location | Sarthi | COMPLETE | `home/sarthi_home_screen.dart` | Background/foreground-service location (postponed, see §9) |
| Ride offer accept/reject | Sarthi | COMPLETE | `rides/ride_offer_screen.dart` | — |
| Ride execution (arrive/OTP/start/complete) | Sarthi | COMPLETE | `rides/ride_execution_screen.dart` | — |
| Wallet balance/transactions/recharge | Sarthi | COMPLETE | `wallet/wallet_screen.dart`, `wallet/recharge_wallet_screen.dart` | — |
| Push notification registration | Both | COMPLETE | `core/notifications/push_notification_manager.dart` | Real-device delivery test (separately tracked, ADR-0052 §9) |
| SOS | User | COMPLETE | `core/api/safety_api.dart` (no dedicated screen — triggered inline) | — |
| Contact support (create case) | Both | PARTIAL | `support/contact_support_screen.dart`, `support/support_case_screen.dart` | No case list, no way to see a later admin reply |
| Customer profile | User | MISSING | — | Whole screen + API client |
| Ride history | User | MISSING | — | Whole screen |
| Promotions | User | MISSING | — | Whole screen + API client |
| Referral | User | MISSING | — | Whole screen + API client |
| Driver profile | Sarthi | MISSING | — | Whole screen + API client |
| Document/KYC upload | Sarthi | MISSING | — | Whole screen + API client (blocks self-service onboarding) |
| Vehicle management | Sarthi | MISSING | — | Whole screen + API client (blocks self-service onboarding) |
| Strikes/penalty history | Sarthi | MISSING | — | Whole screen (no dedicated backend list endpoint either) |
| GPS dispute + evidence upload | Both | MISSING | — | Whole screen + API client |
| Rating | User | N/A (not backend scope) | — | Not yet built server-side either |
| Lost & Found | User | N/A (not backend scope) | — | Not yet built server-side either |
| iOS/Mac/APNs | Both | POSTPONED | — | On hold per standing instruction |
| WhatsApp notifications | Both | POSTPONED | — | BSP not selected |

No code was changed in producing this report.
