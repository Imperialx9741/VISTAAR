VISTAAR — Terms of Service (DRAFT)

Date: 2026-09-02
Status: **DRAFT — NOT LEGAL ADVICE, NOT READY TO PUBLISH.** Grounded in
VISTAAR's actual, already-approved business rules (`business-rules.md`,
the ADRs it cites) — not invented terms. It has not been reviewed by a
lawyer. Placeholders are marked `[NEEDS: ...]`.

Unlike the Privacy Policy, most of this document's substance already
exists as approved business rules — this draft's job is mostly
translating already-decided rules into plain, user-facing legal
language, and flagging the few real gaps where no rule exists yet to
translate.

---

**Terms of Service**

Last updated: [NEEDS: publish date]

**1. Who we are**

VISTAAR is a ride-matching platform connecting Users (riders) with
Sarthis (drivers) in India. [NEEDS: legal entity name, registration
details.]

**2. What VISTAAR does and doesn't do**

VISTAAR matches Users with available Sarthis and calculates ride fares.
**VISTAAR is not a party to the payment for your ride** — you pay the
Sarthi directly, in cash or by UPI, when the ride is complete. VISTAAR
separately charges Sarthis its own platform fee, deducted from the
Sarthi's VISTAAR wallet when a ride is accepted.

**3. Accounts**

You must provide a valid phone number and verify it via OTP to use
VISTAAR. Sarthi accounts additionally require submitting identity,
license, and vehicle documents for review before you can accept rides.
VISTAAR may approve, reject, or request additional documents at its
discretion.

**4. Booking and cancellation**

- A User may cancel a ride. Depending on timing, a cancellation fee may
  apply (currently ₹15 for a first qualifying cancellation is free;
  ₹15 for later ones — [NEEDS: confirm this is the figure you want
  published; `business-rules.md` BR-047/048 documents ₹0 first
  offense/₹15 subsequent]). A cancellation within a short grace period
  after a Sarthi accepts is always free.
- A Sarthi may cancel an accepted ride, subject to a ₹30 penalty and a
  strike against their account, except when declining a pickup-location
  change of more than [NEEDS: confirm published threshold — the app
  currently uses 100m] meters (never penalized).
- Repeated Sarthi cancellations may lead to account suspension.
  [NEEDS: exact strike-to-suspension thresholds — `business-rules.md`
  §43 lists this as still genuinely undecided; cannot be published as a
  firm number until it is.]

**5. Fares and charges**

Fares are calculated by VISTAAR based on distance, time, vehicle type,
and any applicable promotions, and shown to you before you confirm a
ride. If your route changes mid-ride, you'll see and must confirm any
additional charge before it applies.

**6. Outstanding charges**

If you have an unpaid cancellation or no-show charge from a previous
ride, we'll show it to you — combined with your next ride's fare, for
your information — before you book again. **[NEEDS: this policy
currently cannot state how you actually pay that outstanding amount —
that mechanism is still undecided; see
`docs/02-business/known-functional-gaps-2026-09-02.md` §2.3. This
section must be finalized once that decision is made, not published
with a gap in it.]**

**7. Safety**

VISTAAR provides an in-app SOS feature that alerts VISTAAR's own
safety/support team — not emergency services directly. In a genuine
emergency, always contact local emergency services yourself first.
[NEEDS: confirm this is the final, published framing — matches ADR-0050
as implemented.]

**8. Prohibited conduct**

[NEEDS: a standard prohibited-use list — fraud, harassment, unsafe
driving, fake documents, etc. Not drafted here since it isn't derived
from any existing VISTAAR business rule; a lawyer should draft this
section directly rather than have it reverse-engineered from code.]

**9. Disputes**

Fare and ride disputes are handled through VISTAAR's in-app support.
GPS-verification disputes (e.g., a disagreement about whether a Sarthi
actually arrived or completed a ride) are reviewed by VISTAAR's admin
team against recorded location data and any evidence you submit.

**10. Account suspension and termination**

VISTAAR may suspend or terminate accounts for violations of these
terms, fraudulent activity, or safety concerns. [NEEDS: standard
termination/appeal language — a legal drafting task, not one this
document derives from code.]

**11. Limitation of liability**

[NEEDS: standard liability-limitation language appropriate for a ride-
matching platform under Indian law — a lawyer should draft this
directly.]

**12. Governing law**

[NEEDS: confirm governing jurisdiction — presumed India given the
platform's scope, but not this draft's call to make.]

**13. Changes to these terms**

We'll notify you of material changes before they take effect. [NEEDS:
confirm notification method.]

**14. Contact us**

[NEEDS: support contact details.]

---

**Before this can be published**: legal review, every `[NEEDS: ...]`
marker resolved, and — specifically — §6 cannot go live with a real
outstanding-charge payment mechanism referenced until
`known-functional-gaps-2026-09-02.md` §2.3 is decided and built.
