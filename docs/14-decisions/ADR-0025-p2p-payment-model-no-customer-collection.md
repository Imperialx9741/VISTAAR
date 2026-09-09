ADR-0025 — Peer-to-Peer Payment Model: VISTAAR Does Not Collect the
Customer's Ride Fare

Status: Accepted (business decision recorded; documentation reconciled;
NO code, schema, or provider integration changed by this ADR)
Date recorded: 2026-08-25
Deciders: Project owner (explicit business decision, communicated
directly, not inferred).

1. Decision

VISTAAR's approved payment model is peer-to-peer for the ride fare:

1. VISTAAR does NOT collect the customer's ride fare.
2. The customer pays the driver directly (cash or UPI, driver-to-customer,
   no VISTAAR intermediation).
3. VISTAAR does NOT insert itself between customer and driver for
   collection of the ride fare.
4. VISTAAR's platform fee is charged ONLY to the driver, through the
   driver's VISTAAR wallet.
5. The applicable platform fee is deducted from the driver's wallet
   during the documented ride-acceptance transaction (technical-
   architecture.md §18, already implemented — ADR-0014).
6. There is no customer ride-fare charge, customer platform fee, or
   customer payment-gateway collection flow of any kind for the ride
   fare.
7. Driver wallet recharge remains a separate financial flow and may
   still require a payment gateway (unchanged, still TBD — ADR-0013
   Item 3).
8. No customer payment/refund gateway flow is invented by this ADR.
9. Every already-approved wallet, debit, credit, refund, penalty, and
   ledger rule not in direct conflict with this decision is preserved
   unchanged.

This is a documentation-only decision record. No runtime code, database
schema, or payment-provider integration changes as a result of this ADR
— per business-rules.md §44's own documented change process ("Business
decision → Update Business Rules → Identify affected domains → Update
architecture → Update API contracts → Update database/events/state
machines → Update tests → Implement"), this ADR completes only the
first four steps for the affected content; "Update tests"/"Implement"
remain future tasks.

2. Context

The canonical documentation set, as written before this ADR, described
TWO incompatible payment models simultaneously, without ever resolving
which one was approved:

- **Model A (already implemented, in code)**: the driver's platform fee
  is debited from the driver's own wallet balance, synchronously, at
  ride acceptance (technical-architecture.md §18's Accept-Ride
  Transaction; `WalletService.debit()`, composed at
  `modules/matching/router.py`'s accept-offer endpoint — ADR-0014). This
  requires no customer-facing payment step at all; the wallet must
  simply hold a sufficient balance (funded by driver wallet recharge,
  ADR-0013 Item 3, `wallet.recharges`) before the driver can accept a
  ride.
- **Model B (extensively documented, never implemented)**: VISTAAR
  collects the full ride fare (plus its own charge) from the customer —
  either via an "Online" flow (Customer → Payment Intent → VISTAAR
  Payment Gateway → Payment Ledger → Settlement, splitting the amount
  between the driver and VISTAAR) or an "Offline" flow (customer pays
  the driver cash covering BOTH the ride fare AND VISTAAR's charge,
  the driver confirms the total, and VISTAAR then settles its portion
  out of the driver's wallet after the fact). This second model appears
  throughout business-rules.md §11-14/§41, technical-architecture.md
  §20-23, domain-design.md §13-14, database-design.md §18/§20-23,
  state-machines.md §29-32, and api-contracts.md §29-33/§36/§60-61/§69.

These two models cannot both be true. Model A requires nothing from the
customer beyond paying the driver whatever the driver is owed — the
platform fee is already settled before the ride even starts. Model B
requires the customer to pay VISTAAR (directly online, or indirectly by
overpaying the driver in cash and having VISTAAR claw its share back via
the driver's wallet) — a flow with no reason to exist once Model A
already settles the fee upfront. business-rules.md §11 itself already
carried a tell: "This supersedes the earlier assumption that VISTAAR
would never process ride-fare payments" (BR-036) — meaning even the
documentation set's own history shows a prior back-and-forth on exactly
this question, never conclusively settled before now.

This ADR settles it: **Model A is the approved model.** Model B's
customer-facing collection/settlement machinery is superseded wherever
it appears.

3. What is genuinely unaffected

- The Accept-Ride Transaction (technical-architecture.md §18), the
  platform-fee debit at acceptance (ADR-0014), and its cancellation-time
  reversal (BR-046-049, ADR-0015, `FEE_REVERSAL` transaction type) — all
  already exactly match this decision. Nothing here changes.
- Driver wallet recharge (`wallet.recharges`, api-contracts.md §35,
  ADR-0013 Item 3) — still a real, still-TBD, gateway-dependent flow.
  Rule 7 explicitly preserves it; this ADR does not resolve the
  provider/credential decision.
- BR-121 (Ride Fare Disputes): "Because ride fares may be paid directly
  to drivers, ride-fare disputes require a support/admin process" — this
  was already written assuming direct customer→driver payment, and is
  fully consistent with this ADR. No change needed.
- §40 Driver Earnings Transparency's own worked example
  (business-rules.md) already shows the platform fee subtracted from the
  driver's earnings, not added to the customer's total — also already
  consistent. No change needed.
- Every wallet/debit/credit/penalty/ledger rule not named in §4 below.

4. What changes, and why

Every affected document gets an inline "SUPERSEDED (ADR-0025)"
annotation at the specific rule/section, not a deletion — preserving the
audit trail, the same "supersedes" idiom business-rules.md §11 (BR-036)
already established for its own prior correction, and the same
"(Corrected YYYY-MM-DD — this previously said X)" idiom this project's
own roadmap documents use throughout.

- **business-rules.md**: §11's "Online" flow (BR-036) superseded — no
  VISTAAR Payment Gateway collects the fare. §12 "Online Payment"
  (BR-037/038) superseded — no combined online payment to VISTAAR
  bundling the ride fare. §13 "Offline Payment" (BR-039/040) corrected —
  the customer pays the driver the ride fare only, not "ride fare +
  VISTAAR charges"; BR-041/042 stay (general confirmation-integrity
  rules, now scoped to fare-only). §14 "Cash Collection for VISTAAR"
  (BR-043-045) superseded in full — there is no "driver collects
  VISTAAR's charge in cash" scenario once the fee is already collected
  from the wallet before the ride starts. §41 "Cash Collection
  Transparency" superseded — same reason. §43's "Payments" TBD list
  reconciled: "Driver settlement mechanism" and "Payment settlement
  timing" are now RESOLVED (BR-011/ADR-0014 — settled at acceptance);
  "Final payment gateway" narrows to the wallet-recharge gateway only
  (rule 7); "Refund settlement process" is N/A for the customer (nothing
  is ever collected from them to refund) — the driver-side platform-fee
  reversal on cancellation was already resolved separately (ADR-0015,
  `FEE_REVERSAL`).

  NOT touched: BR-054-057 (customer outstanding penalty/no-show charges,
  including BR-055's "customers can pay outstanding VISTAAR charges
  directly through the VISTAAR app"). These are about PENALTY collection
  (₹15 cancellation / ₹30 no-show), not ride-fare collection or the
  platform fee — outside this decision's stated scope (rules 1-6 all
  name "ride fare" or "platform fee" specifically) and protected by rule
  9's "preserve... penalty... rules unless they directly conflict."
  Whether BR-055's customer-facing payment affordance for penalties is
  still intended is a genuine open question this ADR does not resolve —
  flagged for the project owner, not guessed at.

- **api-contracts.md**: §12 (Ride Creation) — `payment_method`
  re-scoped: it records how the customer intends to pay the DRIVER
  (e.g. `"UPI"`/`"CASH"`), never a VISTAAR gateway selection; example
  value corrected from `"ONLINE"`.
  **Addendum, 2026-09-03 (owner decision, "FINAL BUSINESS DECISIONS"):
  removed from the request entirely, not just re-scoped.** "Do NOT
  display or ask the User to select UPI or CASH in the VISTAAR app...
  the User has freedom to choose how they settle the ride amount
  directly with the Sarthi." This ADR's own re-scoping above (display/
  preference field, never built out) is superseded — the field carries
  no product value once the app itself never asks the question, so it
  was deleted rather than kept unused. See ADR-0010 Decision 2's own
  status annotation and modules/ride/domain/entities.py's docstring.
  §29 (Customer Payment/Create
  Payment), §30 (Payment Breakdown), §31 (Payment Gateway Webhook — for
  ride fare), §32 (Offline Payment/Get Cash Requirement), §36
  (Outstanding Cash Settlement) all superseded. §33 (Driver Confirms
  Cash Payment) corrected — no "Create VISTAAR settlement" step; this
  becomes a pure fare-received confirmation with no wallet-side effect
  (the wallet was already debited at acceptance). §34 (Get Wallet) —
  `outstanding_settlement`'s "always 0, not yet built" note extended:
  it is `0` because the concept it modeled no longer applies, not
  because it is merely unbuilt. §60 (Payment State Rules) superseded.
  §61 (Offline Payment State Rules) simplified — no
  `SETTLEMENT_PENDING`/`SETTLED` steps. §69 (Critical Payment Flow)'s
  Online sub-flow superseded; Offline sub-flow loses its
  settlement/wallet-debit steps.

- **technical-architecture.md** (added to the file list per
  business-rules.md §44's own change process, which names "Update
  architecture" as a required step — this document's §20-23 in
  particular describe Model B in the most operational detail of any
  single file, so leaving it untouched would have left the most
  detailed contradiction unreconciled): §5.9 Payment Domain's "Owns"
  list narrows to driver wallet-recharge gateway integration only — no
  customer online payments/intents/refunds. §20 (Customer Payment
  Architecture) — Online flow superseded; Offline flow simplified to
  direct customer→driver payment with no VISTAAR settlement step. §21
  (Payment Tables), §22 (Offline Cash Confirmation — drops "Create
  VISTAAR settlement liability"), §23 (Cash Settlement) all superseded.

- **database-design.md**: §18 (`wallet.outstanding_settlements`), §20
  (`payment.payments`/`payment.allocations`), §21
  (`payment.webhooks` — annotated as potentially repurposable for the
  wallet-recharge gateway, not deleted), §22
  (`payment.cash_confirmations`), §23 (`payment.settlements`) all
  annotated superseded/inapplicable to ride-fare collection. No DDL is
  changed — schema changes are explicitly out of scope for this ADR.

- **domain-design.md**: §13 (Payment Domain) — Responsibility/Owns/
  Commands/Events narrowed to wallet-recharge gateway integration only;
  `CreatePaymentIntent`/`ConfirmOnlinePayment`/`ProcessGatewayWebhook`/
  `CreateSettlement`/`RequestRefund`/`ReconcilePayment` (for ride fare)
  superseded. §14 (Cash Settlement Boundary) superseded in full.

- **state-machines.md**: §29 (Payment State Machine), §30 (Payment
  State Rules) superseded. §31 (Offline Payment State Machine) loses its
  `SETTLEMENT_PENDING`/`SETTLED` steps. §32 (Offline Payment
  Confirmation) corrected — expected amount is the ride fare only.

- **implementation-readiness.md**: §66 (Phase 5 — Definition of Done)
  — "Online payment" struck (N/A); "Offline payment" reworded to a
  fare-received confirmation with no settlement component; "Outstanding
  settlement" struck (N/A).

- **VISTAAR_IMPLEMENTATION_ROADMAP.md / VISTAAR_AUTONOMOUS_EXECUTION_
  PLAN.md**: Phase 10 (Payments)'s blocker status changes from "blocked
  pending customer payment-gateway selection" to "largely N/A per this
  ADR — no customer-facing gateway is needed for the ride fare; the one
  remaining project-wide payment-gateway need is driver wallet recharge,
  already tracked under Phase 11 and still genuinely blocked on provider
  selection." Master Phase List row 10 and the execution plan's
  project-owner-blocked list are updated to match.

5. What this ADR explicitly does NOT do

- Does not implement any runtime code, migration, or schema change.
- Does not select, integrate, or credential any payment provider —
  neither for the (now-eliminated) customer ride-fare flow nor for
  driver wallet recharge, which stays exactly as blocked as before.
- Does not invent a customer payment or refund gateway flow of any
  kind.
- Does not invent cash/UPI implementation details beyond what
  business-rules.md BR-035 already documented (customers may pay via
  UPI or cash).
- Does not change BR-011's platform fee amounts, BR-046-049's
  cancellation-penalty rules, or any other pricing/penalty value.
- Does not resolve BR-055's customer-facing outstanding-penalty-payment
  question — flagged, not decided.
- Does not touch event-contracts.md's `payment.*` event family
  (`payment.initiated`/`succeeded`/`failed`/`cash_confirmed`/
  `settlement_created`/`refund_completed`) or security.md's "Payment
  Gateway Security" section (§27) — both describe Model B in similar
  detail and are not in this ADR's affected-file list; flagged as
  remaining contradictions for a follow-up task, not silently left
  inconsistent by omission.

6. Consequences

The Phase 10 (Payments) roadmap phase, as originally scoped around
customer-facing gateway collection, is largely moot — most of its 17
tasks describe a flow that no longer exists in the approved business
model. The project's only remaining payment-gateway integration need,
project-wide, is driver wallet recharge (Phase 11), unchanged and still
blocked on a provider/credential decision. This is a real simplification
of the project's remaining external-dependency surface, not merely a
documentation cleanup — one fewer payment integration, one fewer PCI-
adjacent security surface, and one fewer reconciliation workflow to
build.
