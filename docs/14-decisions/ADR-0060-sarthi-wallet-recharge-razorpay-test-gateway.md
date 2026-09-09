ADR-0060 — Sarthi Wallet Recharge: Razorpay TEST-Mode Gateway Behind a Provider Abstraction

Status: Accepted — owner decision, delivered as part of "VISTAAR —
Consolidated Decisions, Remaining Implementation & Integration
Instructions," item 4/§15 step 3, 2026-09-02. Implemented the same day.
Date recorded: 2026-09-02
Deciders: Project owner (explicit written instruction, including
providing Razorpay TEST API credentials directly for this integration).

1. Decision

A Sarthi (driver) can top up their own VISTAAR wallet — the same wallet
`PLATFORM_FEE` is debited from at ride acceptance (BR-011) — through a
new three-step recharge flow:

1. `POST /api/v1/drivers/me/wallet/recharge` — creates a pending order
   with the configured gateway.
2. `POST /api/v1/drivers/me/wallet/recharge/confirm` — called by the
   mobile app once Razorpay Checkout reports a completed payment;
   re-verifies server-side before crediting anything.
3. `POST /api/v1/webhooks/wallet-recharge/razorpay` — Razorpay's own
   resilient delivery path, a backup in case step 2 never reaches this
   backend.

For TEST/DEVELOPMENT, the configured gateway is Razorpay
(`WALLET_RECHARGE_PROVIDER=razorpay`, TEST-mode key `rzp_test_...`
provided directly by the project owner for this integration). This is
explicitly NOT a production-provider decision — see §5 below.

This is unrelated to VISTAAR's ride-fare model: VISTAAR still never
collects the ride fare (ADR-0025/ADR-0026, unchanged by this ADR) — a
Sarthi recharging their own wallet is a completely separate "Sarthi →
VISTAAR" flow, not a step in any ride's payment.

2. Why a provider abstraction

The owner's instruction was explicit: Razorpay is temporary (SBI is the
intended production gateway), and the business/wallet logic must not be
written in a way that hard-codes Razorpay. This mirrors two patterns
already established elsewhere in this codebase for exactly the same
reason — `SmsProvider`/`DevConsoleSmsProvider`/`Msg91SmsProvider` and
`PushProvider`/`DevConsolePushProvider`/`FcmPushProvider` — each behind
a Protocol, selected by one env var, with a `get_X_provider()` factory
and a `get_X_provider_dependency()` FastAPI DI wrapper so tests can
swap it via `app.dependency_overrides` without touching real
network/DB wiring.

`modules/wallet/payment_gateway.py`:

```python
class WalletRechargeGateway(Protocol):
    async def create_order(
        self, *, driver_id: uuid.UUID, amount: Decimal
    ) -> RechargeOrder: ...

    async def verify_payment(
        self, *, order_id: str, payment_id: str, signature: str
    ) -> Decimal | None: ...

    def verify_webhook_signature(
        self, *, payload: bytes, signature: str
    ) -> bool: ...

    def parse_captured_payment(
        self, payload: dict[str, object]
    ) -> tuple[uuid.UUID, str, Decimal] | None: ...
```

`DevWalletRechargeGateway` (the default, `WALLET_RECHARGE_PROVIDER=dev`)
logs and returns syntactically valid but never-verified responses — no
real gateway call, matching `DevConsoleSmsProvider`'s own "usable
without any real credentials" role for local development.
`RazorpayWalletRechargeGateway` implements the same Protocol against
Razorpay's real HTTP API. `get_wallet_recharge_gateway()` selects
between them from `settings.WALLET_RECHARGE_PROVIDER`, raising
`ValueError`/`NotImplementedError` on missing credentials or an unknown
provider value (`core/config.py`'s own startup validation).

Nothing above `WalletRechargeGateway` — the router
(`modules/wallet/router.py`) and `WalletService.credit()` — ever
imports `httpx`, constructs a Razorpay URL, or checks a Razorpay-
specific field. The router only ever calls the four Protocol methods
above.

3. Security requirements (owner-specified) and how each is met

- **Verify payment status server-side; never trust the client alone.**
  `confirm_recharge()` calls `gateway.verify_payment(...)`, which
  itself first checks the HMAC-SHA256 checkout signature
  (`order_id|payment_id` signed with `RAZORPAY_KEY_SECRET`) and then
  makes its own `GET /v1/payments/{payment_id}` call to Razorpay,
  crediting the wallet only if Razorpay's own record says
  `status: "captured"`.
- **Never trust a client-supplied amount.** `verify_payment()`'s
  signature deliberately has no `amount` parameter — the amount
  credited is always `Decimal(razorpay_response["amount"]) / 100`,
  read from Razorpay's own response body, never from the mobile app's
  request. Caught and corrected during implementation review, before
  any test ran, when the first draft's router code had no way to
  answer "how much to credit" from the client-supplied
  `{order_id, payment_id, signature}` alone — the fix was changing
  `verify_payment()`'s return type from a bare `bool` to
  `Decimal | None` (the verified amount, or "not verified").
- **Idempotency — a successful payment cannot credit the wallet
  twice.** Both `confirm_recharge()` and the webhook use the identical
  idempotency key, `f"razorpay:{payment_id}"`, through
  `WalletService.credit()`'s pre-existing idempotency-key guarantee
  (`wallet.transactions.idempotency_key` UNIQUE, checked both before
  and after the row lock — the same mechanism BR-141/ADR-0058 already
  relies on for other wallet writes). Whichever of the two call paths
  reaches the backend first for a given `payment_id` credits the
  wallet; the other is a safe no-op replay returning the same result.
  Also idempotent against a plain retried HTTP request (e.g. a mobile
  client retry after a dropped response) for the same reason.
- **Auditable transaction record.** Every recharge credit is an
  ordinary `wallet.transactions` row like any other
  (`transaction_type: WALLET_RECHARGE`, `direction: CREDIT`), visible
  through the pre-existing Wallet Transactions endpoint
  (api-contracts.md §34) — no separate/shadow ledger.
  `metadata: {"provider": "razorpay", "order_id", "payment_id"}`
  records enough to trace any credit back to the exact gateway payment
  that produced it.
- **Handle failed/cancelled/duplicate/uncertain states safely.** An
  unverified or non-captured payment (`verify_payment()` returns
  `None`) credits nothing and returns `402
  PAYMENT_VERIFICATION_FAILED`. A gateway error while creating an
  order or verifying a payment (network failure, Razorpay outage,
  misconfigured keys) returns `502 PAYMENT_GATEWAY_ERROR` and credits
  nothing. A webhook event that isn't `payment.captured` (e.g.
  `payment.failed`) is acknowledged (`200 {"status": "IGNORED"}`) but
  never acted on. A duplicate delivery of the same captured payment
  (webhook redelivery, a retried confirm call) is the idempotency case
  above.
- **Credentials never committed; read from environment/secure
  configuration.** `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET`/
  `RAZORPAY_WEBHOOK_SECRET` are read via `os.getenv(...)` in
  `core/config.py`, default to empty strings (never a real key baked
  into source), and are validated (non-empty, in combination with
  `WALLET_RECHARGE_PROVIDER=razorpay`) at startup, not hardcoded
  anywhere. `.env.example` documents the variable names with placeholder
  values only. Both the TEST Key ID and Key Secret the project owner
  provided directly are configured into this environment's local `.env`
  (gitignored — not into any file this report reproduces or that gets
  committed), consistent with the owner's own "do not print credentials
  or secrets" instruction elsewhere in this same session.
  `WALLET_RECHARGE_PROVIDER` is now `razorpay`, not `dev` — verified for
  real: with `.env` loaded, `get_wallet_recharge_gateway()` returns a
  `RazorpayWalletRechargeGateway`, and calling its `create_order()`
  against the real Razorpay TEST-mode API (not `httpx.MockTransport`)
  succeeded — a genuine order (`order_TX8...`) was created for real,
  confirming the credentials and the Basic Auth / amount-in-paise /
  response-parsing logic all work against the live API, not only against
  the mocked unit tests. Correction, 2026-09-02: an earlier version of
  this ADR said only the Key ID had been provided and this mode was
  deliberately left on `dev` pending the secret — that was based on the
  Key Secret having been mislabeled as a WhatsApp BSP credential when
  first given; the owner corrected this, and both values are confirmed
  to be the real Razorpay TEST Key ID/Key Secret pair.
  `RAZORPAY_WEBHOOK_SECRET` is still not provided — the webhook route
  will reject every delivery with `401 INVALID_WEBHOOK_SIGNATURE` until
  it is (the mobile confirm-recharge path is unaffected by this, since
  it never touches the webhook).

  One environment-specific note worth recording: this backend's own
  process never reads `.env` automatically (no `python-dotenv` or
  equivalent is wired in — `.env` is a template meant for `docker run
  --env-file`/docker-compose/Kubernetes Secrets, per `README.md`'s own
  documented run command). The verification above required explicitly
  loading `.env` into the shell (`set -a && source .env`) before
  invoking Python — a bare `python -c "..."` without that step silently
  falls back to every default (`WALLET_RECHARGE_PROVIDER=dev`, empty
  keys) with no error, which is exactly what happened during an earlier,
  inconclusive check in this same session. Worth keeping in mind for any
  future manual verification against this repo's `.env`.
- **Webhook authenticity.** The webhook route
  (`POST /api/v1/webhooks/wallet-recharge/razorpay`) verifies
  `X-Razorpay-Signature` against the *raw* request body (never
  parse-then-verify — the signature covers the unparsed bytes) using a
  separate secret (`RAZORPAY_WEBHOOK_SECRET`, distinct from the
  checkout-flow `RAZORPAY_KEY_SECRET`) before trusting anything in the
  payload. Missing or invalid signature: `401
  INVALID_WEBHOOK_SIGNATURE`.

4. Data model

No schema change was needed. `wallet.transactions.transaction_type`
already had a `WALLET_RECHARGE` enum value and `metadata JSONB` column
reserved (database-design.md §17.2) from the original Wallet Foundation
design — this ADR is the first thing that actually produces rows using
them. Razorpay's own order `notes` field (echoed back on the webhook)
carries `driver_id` for webhook-side reconciliation; no new "orders"
table was created, since `wallet.transactions.metadata` already covers
the audit need and Razorpay's string-typed IDs don't fit the existing
UUID-typed `reference_id` column.

5. What changes when SBI replaces Razorpay

Everything below `WalletRechargeGateway` in the Protocol boundary is
Razorpay-specific and is exactly (and only) what a future SBI
integration replaces:

- **Payment initiation** — `RazorpayWalletRechargeGateway.create_order()`
  (the `POST /v1/orders` call, Basic Auth, amount-in-paise conversion)
  → a new `SbiWalletRechargeGateway.create_order()` implementing
  whatever SBI's own order/session-initiation API requires.
- **Payment verification** — `verify_payment()`'s HMAC-SHA256 checkout-
  signature check and `GET /v1/payments/{payment_id}` call → SBI's own
  signature/verification scheme and status-lookup API.
- **Payment status semantics** — the `status == "captured"` check
  (Razorpay's own vocabulary) → whatever "payment succeeded" looks like
  in SBI's API (a different status string/field entirely, almost
  certainly).
- **Webhook/callback handling** — `verify_webhook_signature()` (raw-body
  HMAC against `RAZORPAY_WEBHOOK_SECRET`) and `parse_captured_payment()`
  (Razorpay's specific webhook JSON shape,
  `payload.payment.entity.{id,amount,notes}`) → SBI's own callback
  authentication scheme and payload shape. The route path itself
  (`/api/v1/webhooks/wallet-recharge/razorpay`) would need an SBI-
  specific sibling (or rename) since it is not provider-generic today —
  worth revisiting when SBI credentials/API docs are actually available,
  not guessed now.
- **Configuration** — `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET`/
  `RAZORPAY_WEBHOOK_SECRET` → SBI's own credential shape (SBI's
  integration model — certificate-based, merchant-ID/API-key, or
  otherwise — is not yet known and must not be guessed; determined once
  the owner provides real SBI documentation/credentials, per the
  consolidated instruction's explicit "do not invent undocumented API
  behavior" directive).

What does **not** change:

- **Wallet crediting** — `WalletService.credit()`, its idempotency-key
  guarantee, the `WALLET_RECHARGE` transaction type, and the
  `wallet.transactions` audit row shape are all provider-agnostic
  already and need no change.
- **Transaction reconciliation** — driven off `wallet.transactions`
  rows and their `metadata`, not off any Razorpay-specific table;
  `metadata`'s `{"provider": ...}` field already anticipates more than
  one provider value coexisting (e.g. during a migration window).
- **The router's control flow** — `create_recharge_order()`/
  `confirm_recharge()`/the webhook handler call only the four
  `WalletRechargeGateway` Protocol methods; switching
  `WALLET_RECHARGE_PROVIDER=sbi` (once an `SbiWalletRechargeGateway` is
  implemented and registered in `get_wallet_recharge_gateway()`) is the
  only change needed to cut over, mirroring exactly how
  `SMS_PROVIDER=msg91` or `PUSH_PROVIDER=fcm` are switched today.
- **Mobile app business logic** — the recharge screen calls VISTAAR's
  own `/recharge` and `/recharge/confirm` endpoints, not Razorpay
  directly, except for the Razorpay Checkout SDK step in between (order
  creation → checkout → confirm). Replacing the checkout SDK itself
  (Razorpay Checkout → whatever SBI's equivalent is) is a mobile-side
  change this ADR does not attempt to predict.

6. What this ADR does not do

- Does not use Razorpay as, or assume it will become, the production
  gateway — explicitly TEST/DEVELOPMENT only, per direct owner
  instruction.
- Does not implement any SBI-specific code — no SBI credentials or API
  documentation has been provided yet; §5 above is preparation/
  documentation only, not a guess at SBI's actual API shape.
- Does not touch the customer-facing ride-fare model in any way
  (ADR-0025/ADR-0026 unchanged) — this is a Sarthi wallet top-up only.
- Does not implement customer outstanding-penalty collection — still
  genuinely undecided (ADR-0026 §5, business-rules.md §17); Razorpay
  being wired up for Sarthi wallet recharge does not imply or solve
  this separate, unrelated open question.
- Does not add a general-purpose "payments" module/table — deliberately
  reuses the existing `wallet.transactions` ledger rather than
  introducing new payment infrastructure.

7. Testing

Backend: 21 new unit tests
(`tests/test_wallet_payment_gateway.py`, `RazorpayWalletRechargeGateway`
exercised entirely against `httpx.MockTransport` — no real network call,
no real Razorpay account needed to run the suite) covering order
creation (amount-in-paise conversion, `driver_id` in `notes`, gateway
error responses), payment verification (captured/not-captured/
signature-mismatch/gateway-error, and explicitly asserting the returned
amount always comes from the gateway's own response, never a caller-
supplied value), webhook signature verification (valid/tampered), and
webhook payload parsing (capture/non-capture/malformed). 14 new real-
HTTP/real-Postgres integration tests (`tests/test_wallet_recharge_api.py`,
gateway swapped for a `FakeGateway` via `app.dependency_overrides`,
matching every other provider-backed integration test's own convention)
covering the full three-endpoint flow end to end: order creation
(success, below-minimum, gateway error, auth/role checks), confirm
(credits on verified payment, never credits an unverified one,
idempotent on a retried same-payment confirm, surfaces gateway errors),
and the webhook (rejects invalid/missing signature, ignores non-capture
events, credits on a captured payment, and — the resilience scenario
this design is built for — confirm and the webhook both arriving for
the same payment credit the wallet exactly once, verified against both
the wallet balance and a `COUNT(*) = 1` check on
`wallet.transactions`). Full backend suite: 1347 passed, 5 skipped, 0
failed (was 1312), ruff/mypy clean.

One real bug was caught and fixed before any test ran (self-caught
during implementation, not test-caught): the original `confirm_recharge()`
draft called an undefined placeholder function to determine the credit
amount, because `verify_payment()` originally returned a bare `bool` —
there was no way for the router to know "how much to credit" from
client-supplied fields alone. Fixed by changing `verify_payment()`'s
return type to `Decimal | None` (the gateway-verified amount) across
the Protocol and both implementations — see §3 above.

A second, genuine bug was caught by `tests/test_wallet_recharge_api.py`
itself failing non-deterministically depending on run history: this
test file was initially written without the
`_clean_integration_tables`/`truncate_integration_tables(engine)`
autouse fixture every other real-Postgres integration test file in this
codebase already has. Without it, this file's hardcoded literal
`payment_id`s (`"pay_fake_1"`, `"pay_webhook_1"`, `"pay_shared_1"`)
collided across separate test runs against the persistent local test
database on `wallet.transactions.idempotency_key`'s UNIQUE constraint
(global, not per-driver) — a previous run's already-committed
`"razorpay:pay_fake_1"` row (for some earlier, unrelated driver) made
`WalletService.credit()` treat a later run's confirm/webhook call as a
replay of that *old* payment: it returned the old transaction (a real
`balance_after`, so the HTTP response looked entirely correct) without
ever crediting the new test's actual driver, who therefore showed a
wallet balance of `0` instead of the expected credited amount. Fixed by
adding the same autouse fixture, matching the established convention.

Mobile: new `RechargeWalletScreen` (amount entry → `POST /recharge` →
`RazorpayCheckout.open()` → `POST /recharge/confirm`), reachable from a
new "Recharge Wallet" button on `WalletScreen` and from
`RideOfferScreen`'s low-balance SnackBar/`WALLET_RECHARGE_REQUIRED`
error state (ADR-0058 §6's deferred action, wired up here). Uses the
official `razorpay_flutter` package (`RealRazorpayCheckout`) behind a
small `RazorpayCheckout` interface — deliberately mirroring the
backend's own provider-abstraction pattern one layer up, so the screen
itself never mentions "Razorpay" and a future different checkout SDK
would only need a second implementation of the same interface, not a
screen rewrite. 9 new widget tests
(`test/features/wallet/recharge_wallet_screen_test.dart`,
`test/features/wallet/wallet_screen_test.dart`,
`test/features/rides/ride_offer_screen_test.dart`) exercised entirely
against a `FakeRazorpayCheckout` test double injected via
`RechargeWalletScreen(checkout: ...)` — covering the below-minimum
local validation, order creation and the correct amount-in-paise
conversion passed to checkout, a gateway error while creating the
order, a full success path (order → checkout success → confirm →
`Navigator.pop` with the new balance), a checkout-reported payment
failure, and confirm-side verification failure, plus that disposing the
screen releases the checkout's native listeners. Full suite: 140/140
passed (was 131), `flutter analyze` clean.

`RealRazorpayCheckout`/the real `razorpay_flutter` native plugin itself
is not, and cannot be, exercised by these tests — it needs a real
Android/iOS device or emulator's platform channel, which this
environment has none of (the same limitation this session's earlier
Contacts-picker work already documented for `flutter_contacts`).
Confirmed the plugin's Dart-level constructor (`Razorpay()`/`.clear()`)
does not itself throw outside a device (verified directly, so tests
could safely navigate to `RechargeWalletScreen` in its real,
non-overridden form without crashing) — but the actual checkout UI,
Android/iOS platform-channel wiring, and a real payment attempt end to
end have not been run on a device in this environment and remain
untested beyond this Dart-level check.

8. Remaining work (not yet done)

- `RAZORPAY_WEBHOOK_SECRET` has not been provided — the resilience
  webhook path (§1 step 3) will reject every real delivery until it is
  set. Get this from the Razorpay dashboard (Settings → Webhooks →
  create/select the webhook → its own secret, separate from the Key
  Secret) once a real webhook URL exists to register there.
- Real-device verification of the `razorpay_flutter` native plugin end
  to end (launching the actual Razorpay Checkout UI, completing a real
  TEST-mode payment with a Razorpay test card, confirming the full
  round trip through `confirm_recharge`) — not possible in this
  environment; see §7 above. The backend half of this (`create_order`
  against the real API) has now been verified for real — see §3's
  "Credentials" bullet — only the mobile Checkout UI leg remains
  unverified.
- iOS: `ios/Podfile`/CocoaPods integration for `razorpay_flutter` has
  not been generated (no `pod install` was run — this environment has
  no CocoaPods/Mac toolchain, and iOS production work is separately on
  hold per the owner's own instruction). `flutter pub get` resolved the
  package cleanly, and `flutter analyze` is clean, but an actual iOS
  build has not been attempted.
