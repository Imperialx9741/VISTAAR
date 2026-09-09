ADR-0026 — Customer Outstanding Penalty Collection: Split Settlement at
Next Booking (Option A)

Status: Accepted (business decision recorded; documentation reconciled;
NO code, schema, or provider integration changed by this ADR). **Rules
2, 5, 8 (the settlement mechanism — "Customer → VISTAAR" as a separate
charge, no gateway) superseded 2026-09-03 by
[ADR-0066](ADR-0066-customer-penalty-settlement-via-driver-wallet.md)**:
the customer now pays the combined fare-plus-penalty amount to the
Sarthi directly, and VISTAAR recovers its own share via the driver's
wallet at ride completion — closing this ADR's own §5 "genuinely open"
collection-mechanism question, not by picking a provider but by
determining none is needed. Rules 1, 3, 4, 6, 7, 9 (the penalty is
still OUTSTANDING until settled, still shown at the next booking, the
ride fare stays P2P, the driver's wallet is never debited for the
customer's *fare*, every other approved penalty rule is preserved) are
unchanged — see ADR-0066 §4 for the exact split.
Date recorded: 2026-08-26
Deciders: Project owner (explicit business decision, communicated
directly, not inferred).
Supersedes: nothing outright — complements ADR-0025, resolving the exact
question ADR-0025 §4 explicitly flagged as unresolved ("whether
customers can still pay outstanding penalty/no-show charges via a
VISTAAR-facing flow (BR-055)").

1. Decision

1. A valid customer cancellation/no-show penalty creates an OUTSTANDING
   penalty liability for that customer (already exactly how
   `penalty.penalties`/`PenaltyStatus.OUTSTANDING` work today — BR-047/
   048/052, ADR-0015 — no change needed here).
2. VISTAAR does not immediately collect that penalty through a separate
   customer payment gateway at the moment the penalty is created.
3. On the customer's next eligible ride booking, the UI/API must expose:
   ride fare + outstanding customer penalty = total amount the customer
   must pay.
4. The ride fare remains P2P: Customer → Driver (ADR-0025, unchanged).
5. The outstanding penalty is a separate VISTAAR charge: Customer →
   VISTAAR.
6. The driver's wallet MUST NOT be debited for the customer's penalty.
7. The driver's wallet remains used only for VISTAAR's own driver-side
   financial operations, including the applicable platform fee
   (unchanged from ADR-0025/BR-011).
8. No new payment gateway is implemented for the customer ride fare.
9. Driver wallet recharge remains a separate, still-TBD, future
   payment-provider flow (ADR-0013 Item 3, unaffected).

This is a documentation-only decision record, per the same
business-rules.md §44 change process ADR-0025 followed. No runtime
code, schema, or payment-provider integration changes as a result of
this ADR.

2. Context

ADR-0025 (2026-08-25) established that VISTAAR never collects the ride
fare from the customer, but explicitly declined to resolve a related,
narrower question: BR-055 ("Customers can pay outstanding VISTAAR
charges directly through the VISTAAR app") describes a *different*
customer-facing VISTAAR payment relationship — for cancellation/no-show
penalties, not the ride fare — that ADR-0025 flagged as out of its own
scope (rules 1-6 there all name "ride fare" or "platform fee"
specifically) and left for the project owner. This ADR is that answer:
**Option A** — a split-settlement model where the ride fare and the
outstanding penalty are structurally two separate flows to two separate
recipients, surfaced together for the customer's transparency but never
merged into one payment.

This corrects a subtlety in how ADR-0025 was applied to business-rules.md
§12 (BR-037/038, "Online Payment"): those rules were marked fully
superseded on the reasoning that any combined "ride fare + outstanding
charges" collection is impossible once VISTAAR can't collect the fare.
That reasoning was too broad — the *display* concept (a combined total,
BR-038) survives; only the *settlement* mechanic (BR-037's "customer
pays ₹130 through VISTAAR, VISTAAR separates ₹100 → driver / ₹30 →
VISTAAR") was wrong, and only in *how* the split happens, not *that* a
split total is shown. Corrected: the split happens before payment, not
after — the customer pays the driver directly for the fare and pays
VISTAAR directly (separately) for the penalty; nothing about the ₹100
ride-fare portion ever touches VISTAAR.

3. What changes, and why

- **business-rules.md** §12 (BR-037/038): re-corrected from
  "SUPERSEDED IN FULL" to "partly revived" — the combined display
  concept is restored (with the settlement-mechanics explanation
  corrected inline); §17 (BR-054-057): resolved — BR-055/056 are now
  confirmed accurate, not merely aspirational; BR-057 (booking is never
  blocked by an unpaid outstanding charge) is explicitly unaffected —
  rule 3 requires *exposing* the total, not *blocking* booking on it.
- **api-contracts.md** §12 (Ride Creation): gains a documented
  `outstanding_penalty`/`total_payable` shape in the response — filled
  in, since this is the concrete "next eligible ride booking" moment
  rule 3 refers to. §29-30 (Customer Payment / Payment Breakdown):
  partially un-superseded — a `payment.*`-style flow specifically for
  collecting the *outstanding penalty component* (never the ride fare)
  is a legitimate future endpoint; the exact route/payload is NOT
  designed here (no runtime code), only the business shape.
- **database-design.md** §20 (`payment.payments`/`payment.allocations`):
  re-annotated — this schema, previously superseded in full by
  ADR-0025 for modeling ride-fare collection, may still be
  substantially the right shape for penalty-only collection: its
  existing `VISTAAR_PENALTY` allocation type (already documented) was
  apparently anticipating exactly this. `DRIVER_RIDE_FARE`,
  `VISTAAR_PARKING`, `VISTAAR_OTHER`, and `TAX` allocation types stay
  superseded/out of this decision's scope — parking/pickup-change/
  destination-change charges are still owed to the driver as part of
  the fare (business-rules.md §40's own worked example), not VISTAAR.
  No DDL is changed — this is a documentation annotation only.
- **domain-design.md** §13 (Payment Domain): the "wallet-recharge-gateway-
  only" scope ADR-0025 narrowed this to gains a second legitimate
  purpose — customer outstanding-penalty collection.
- **state-machines.md**: no change needed — the online Payment State
  Machine (§29-30) stays superseded for the ride fare specifically; a
  future penalty-payment flow, if built, would need its own (much
  simpler — no allocation/split step) state machine, not designed here.
- **VISTAAR_IMPLEMENTATION_ROADMAP.md / VISTAAR_AUTONOMOUS_EXECUTION_
  PLAN.md**: Phase 10 (Payments)'s status is corrected again — ADR-0025
  called it "largely N/A"; that was too strong. It regains one real,
  still-blocked task: a customer-facing payment mechanism/provider for
  outstanding penalty collection. Distinct from, and smaller than, the
  original 17-task scope (still no ride-fare gateway), but not zero.

4. What this ADR explicitly does NOT do

- Does not implement any runtime code, migration, or schema change.
- Does not select, integrate, or credential any payment provider for
  penalty collection — this remains genuinely open, the same class of
  gap as driver wallet recharge (rule 9).
- Does not implement a new payment gateway for the customer ride fare
  (rule 8) — the ride fare stays exactly as ADR-0025 established.
- Does not change BR-047/048/052's penalty amounts (₹15/₹30) or
  BR-049/053's 30-day expiry.
- Does not block ride booking on an unpaid outstanding charge — BR-057
  is unchanged.
- Does not resolve how parking, pickup-change, or destination-change
  charges are collected — those stay owed to the driver, unaffected,
  outside this ADR's scope (it is about customer *penalties*
  specifically).

5. Remaining open items (flagged, not decided)

- The actual payment mechanism/provider for "Customer → VISTAAR"
  penalty collection (UPI deep-link, a card/wallet-style gateway
  checkout, something else) is undocumented and unbuilt — the same
  category of gap as driver wallet recharge (ADR-0013 Item 3), just for
  a different party. A future ADR must select it before implementation.
- Whether `payment.payments`/`payment.allocations` (database-design.md
  §20) is reused for this, redesigned, or replaced with a narrower
  penalty-specific table is an implementation-time decision, not made
  here.
- Whether BR-055's "directly through the VISTAAR app" describes a
  standalone anytime-settlement path (independent of booking a ride) in
  addition to the at-next-booking trigger rule 3 mandates, or is fully
  subsumed by it, is not precisely disambiguated by the rules as given
  — both readings are consistent with what was approved; a future task
  building the actual payment surface should confirm which (or both)
  with the project owner before implementing.

6. Consequences

The customer-penalty lifecycle is now fully specified end-to-end at the
business-rules level: created OUTSTANDING at a qualifying cancellation/
no-show, surfaced (not collected) immediately, and settled — as a
VISTAAR-only charge, never touching the driver's wallet or the ride
fare — no later than the customer's next ride booking. Phase 10
(Payments) is not fully closed by ADR-0025 after all; it retains one
real, narrower, still-provider-blocked task.
