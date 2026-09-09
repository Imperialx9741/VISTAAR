VISTAAR — Known Functional Blockers and Gaps

Date: 2026-09-02
Purpose: a clear, non-technical-first account of what's actually broken
or missing in the running system, for decision-making — not a duplicate
of the detailed technical write-ups this links to
(`docs/10-testing/e2e-findings-2026-09-02.md`,
`docs/08-security/security-review-2026-09-02.md`). Everything here is
checked against the real code and the real, already-approved business
rules (ADR-0025, ADR-0026, BR-011/046-049) — nothing here is a new
business rule or architecture decision.

1. **RESOLVED 2026-09-03 (ADR-0062)** — was: a driver with an
   insufficient wallet balance cannot cancel a ride at all

Implemented the "debit what's available, track the rest, recover it
automatically at next recharge" option — with the correction that
*nothing* is debited when the balance is insufficient (not "whatever is
available"), the full unpaid penalty becomes a tracked
`wallet.outstanding_debt`, and it's recovered only from a future
**WALLET_RECHARGE** credit specifically, not any credit. Confirmed with
you directly before building it, since your own "keep unchanged"
description didn't match what the running code actually did (verified
against real Postgres) — see ADR-0062 §2 for the full account.

The cancellation itself is never blocked now, regardless of balance;
the ride-status transition and driver strike happen exactly as they
would with a sufficient balance. An outstanding debt does not, by
itself, affect ride-acceptance eligibility — that remains governed
solely by the existing ₹20 low-balance rule (ADR-0058), confirmed
independent of this.

2. Payment — corrected scope (this was previously mis-stated)

I originally flagged "no payment gate before a ride closes" as a gap. On
closer inspection, that was wrong, and I want to correct it plainly:
VISTAAR's already-approved payment model (ADR-0025, ADR-0026 — real
decisions you made in an earlier session, not something I'm
re-litigating) is that the customer pays the driver directly, in cash or
by UPI, with VISTAAR never involved in that transaction at all. Under
that model, a ride correctly closes the moment it's GPS-verified as
complete, with no payment step in between — because there's nothing for
VISTAAR to check. That's the system working as designed, not a gap.

What the "SBI gateway decision" actually still blocks is narrower and
more specific than "payment gate" implied. There are three separate real
items:

2.1 **RESOLVED 2026-09-02 (ADR-0059)** — was: showing a customer what
they owe before their next ride

When a customer has an unpaid cancellation/no-show penalty from a
previous ride, the app now shows them, at their next booking: ride fare
+ outstanding penalty = total they'll owe that trip (this figure is
informational only — the ride fare still goes straight to the driver;
only the penalty portion is ever owed to VISTAAR). Implemented exactly
per the already-documented shape (`api-contracts.md` §12,
`outstanding_penalty`/`total_payable`) — no new business rule. Needed no
payment gateway, none was added.

2.2 **RESOLVED for TEST/DEVELOPMENT 2026-09-02 (ADR-0060)** — was:
needs a gateway decision — driver wallet recharge

A driver tops up their own VISTAAR wallet with real money (so they have
balance to spend on future ride-acceptance fees). You provided a
Razorpay TEST-mode Key ID and Key Secret directly and instructed using
Razorpay for TESTING/DEVELOPMENT only, behind a provider abstraction,
with the production gateway remaining a separate, still-pending SBI
decision (ADR-0060 documents exactly what changes when that happens).

**Current state**: fully built, tested, and now confirmed working
end-to-end for TEST-mode Razorpay — `POST /api/v1/drivers/me/wallet/
recharge`, `POST /api/v1/drivers/me/wallet/recharge/confirm`, the
`POST /api/v1/webhooks/wallet-recharge/razorpay` resilience webhook, and
a mobile "Recharge Wallet" screen (`lib/features/wallet/
recharge_wallet_screen.dart`), reachable from the wallet screen and from
the low-balance/`WALLET_RECHARGE_REQUIRED` states ADR-0058 introduced.
Server-side payment verification, idempotent crediting, and an auditable
transaction record are all in place — see ADR-0060 §3 for exactly how
each of your stated security requirements is met. `WALLET_RECHARGE_
PROVIDER=razorpay` in this environment's local `.env` now, and a real
order was created against Razorpay's live TEST API with these
credentials to confirm they actually work, not just that the code looks
right.

**What remains, still genuinely blocked on you**: `RAZORPAY_WEBHOOK_
SECRET` — a separate value from the Key Secret (Razorpay dashboard →
Webhooks) — has not been provided, so the resilience webhook path will
reject real deliveries until it is; the primary mobile confirm-recharge
path is unaffected. Separately, real production use needs actual SBI
credentials/API documentation — none provided yet, and none guessed at.
Razorpay stays TEST/DEVELOPMENT-only regardless; nothing in this build
assumes it becomes the production gateway.

2.3 **RESOLVED 2026-09-03 (ADR-0066) — collecting a customer's
outstanding penalty**

Was: a still-undecided question (ADR-0026 §5) — *whether* customers get
an in-app way to pay off an outstanding penalty at all, and through
what mechanism. Now resolved: no in-app payment flow is needed at all.
The customer pays the combined fare-plus-penalty amount to the Sarthi
directly (physically/UPI/cash between the two of them, same as the ride
fare always was), and VISTAAR recovers its own share automatically by
debiting the driver's wallet the moment the ride completes — no
backend payment endpoint, no provider selection, no mobile payment
screen, none needed. See ADR-0066 for the full mechanism.

**What I need from you**, once you're ready: real SBI credentials/API
documentation, whenever you want to move 2.2 from TEST-mode to
production — none provided yet, none assumed. Separately, whether and
how 2.3 should work at all remains entirely open; that can use the same
underlying provider as 2.2's eventual production gateway or a different
one — your call, not something I should assume either way.

3. A small, separate observation (not a blocker)

The mobile booking screen asks the customer to choose "UPI" or "Cash"
before booking — but nothing anywhere actually uses that answer. The
backend accepts it, validates its shape, and then discards it entirely
(it isn't even stored). The driver is never shown which one the
customer picked, in the app or otherwise. Whether that field is meant to
inform the driver ahead of time, or is just vestigial at this point,
isn't resolved anywhere — flagging it rather than guessing.

4. Where the full technical detail lives

- `docs/10-testing/e2e-findings-2026-09-02.md` — how each of these was
  found, with the exact test code and real database queries that proved
  it.
- `docs/08-security/security-review-2026-09-02.md` §8 — the security
  angle on the payment-model correction.
- `docs/08-security/security.md` §27-32 and
  `docs/06-events/event-contracts.md` §14 — both now carry inline
  corrections pointing back to ADR-0025/ADR-0026, closing a
  documentation gap ADR-0025 itself had flagged as an unfinished
  follow-up since 2026-08-25.
