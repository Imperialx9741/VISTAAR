ADR-0048 — Admin Settings (MVP)

Status: Accepted and implemented (2026-08-28) — owner decision #6 of the
2026-08-26 "approved product decisions" batch, recorded design-only per
the owner's "DO NOT IMPLEMENT RUNTIME CODE YET" instruction on that
batch, then implemented under the owner's subsequent broader
authorization to build everything not blocked on an external
credential.

Date recorded: 2026-08-26.
Deciders: Project owner (explicit written decision, 2026-08-26).

1. Context

The Admin Web plan's §4.19 previously said Settings was "NEEDS SCOPING
entirely... the original spec names this module but gives no content
for it." The owner's decision supplies the category list: fare
settings; platform fees; referral settings; notification settings;
promotion defaults; operational thresholds; feature flags; general
platform settings — with a hard boundary ("business/operational
configuration only... never expose API keys, passwords, cloud
secrets, DB credentials, or private keys").

2. Decision 1 — Settings is a navigation surface over four already-
   dedicated screens, plus one new table for what nothing else owns

Four of the eight named categories already have (or, per this same
decision batch, are about to have) their own dedicated, versioned admin
screen: fare settings (`FARE_MANAGEMENT`, ADR-0042), platform fees
(ADR-0045), referral settings (ADR-0043), notification settings
(ADR-0044). Building a second, parallel place to edit the same data
would create two sources of truth for one number — exactly the
"conflate two concepts" mistake this codebase has deliberately avoided
throughout (ADR-0041 §7, ADR-0043 §2, ADR-0045 §2). Settings therefore
*links to* those four screens (an Admin Web navigation/UX concern, not
a backend one) rather than duplicating their data or endpoints.

The remaining four categories — promotion defaults, operational
thresholds, feature flags, general platform settings — have no home
anywhere yet. These get one new, generic table:

```
CREATE TABLE admin.settings (
    key VARCHAR(100) PRIMARY KEY,
    value JSONB NOT NULL,
    category VARCHAR(30) NOT NULL,  -- 'PROMOTION_DEFAULT' | 'OPERATIONAL_THRESHOLD'
                                     -- | 'FEATURE_FLAG' | 'GENERAL'
    description TEXT NOT NULL,      -- shown in the Admin UI so a value's meaning
                                     -- is never a mystery key name alone
    updated_by UUID NOT NULL REFERENCES admin.users(id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

A flat key-value store, not a bespoke table per setting — these four
categories are small, heterogeneous, and don't share fare/fee/reward's
"future value applies going forward, history frozen" shape (nothing
here is read at the moment of a financial transaction the way a fare
or fee is), so the added complexity of a DRAFT/PUBLISHED workflow
buys nothing; a plain audited overwrite (old value visible in
`admin.audit_logs.before_state`, same as every other admin mutation)
is enough.

3. Decision 2 — What actually populates this table at launch: a
   small, explicit starter set, not every hardcoded constant in the
   codebase

"MVP Settings must contain business/operational configuration only" is
a boundary on *category*, not an instruction to migrate every
hardcoded constant in this codebase into `admin.settings` in one pass —
many of them are safety- or pricing-adjacent and changing them via a
generic settings screen without the same scrutiny a dedicated ADR gave
them would be exactly the "invent arbitrary" behavior this whole
decision batch is careful to avoid. The implementing task seeds only
what's unambiguous and already has an approved value to seed with:

- `PROMOTION_DEFAULT`: `welcome_discount_percent` (50), `welcome_total_uses`
  (3) — BR-058's own approved values (`modules/promotion/domain/
  entities.py`'s `_WELCOME_DISCOUNT_PERCENT`/`_WELCOME_TOTAL_USES`),
  explicitly NOT the referral-specific values ADR-0043 already made a
  dedicated, versioned home for.
- `OPERATIONAL_THRESHOLD`: none seeded at launch — every threshold
  candidate this codebase has (e.g. the driver cancellation grace
  period, BR-046) is either already a settled BR value with no
  documented admin-editability requirement, or (BR-066's early/late
  cancellation boundary) still genuinely TBD — moving a TBD value into
  an admin-editable table would be answering the TBD question by
  implication, not resolving it. Flagged as an open gap, not filled.
- `FEATURE_FLAG`: none seeded at launch — no flag currently gates any
  code path in this codebase (WhatsApp/PUSH are gated by "no provider
  configured" errors, not a flag row); adding flags with nothing to
  flag would be inventing a mechanism with no consumer.
- `GENERAL`: none seeded at launch.

This ADR builds the *mechanism*; growing the seeded set is each
individual future value's own decision, made with the same rigor
BR-058/BR-011/BR-022 already got, not a bulk migration.

4. Decision 3 — Admin endpoints

```
GET   /api/v1/admin/settings?category=          List (grouped by category)
GET   /api/v1/admin/settings/{key}                Get one
PATCH /api/v1/admin/settings/{key}                Update value (audited; before_state/after_state
                                                    capture the full old/new value)
```

No Create/Delete — the set of valid keys is fixed by what the
implementing migration seeds (Decision 2); a key not already in the
table returns `RESOURCE_NOT_FOUND` on PATCH, same "closed vocabulary,
not client-invented" treatment this codebase gives every other fixed
enum. New permission key: none — reuses `SETTINGS`, already reserved
in the 20-module catalog and already correctly restricted to
Super-Admin-only, never grantable (BR-126) — appropriate here, since
these values can affect promotion economics platform-wide.

5. Decision 4 — Secret exposure is a response-shape guarantee, not
   just a promise

`admin.settings.value` is a generic JSONB column, which means nothing
in the schema itself prevents an admin from typing a secret into it.
The guarantee the owner asked for ("never expose API keys, passwords,
cloud secrets, DB credentials, or private keys") is enforced by: (a)
the seeded key list (Decision 2) never includes anything
credential-shaped, and (b) real provider credentials continue to live
exclusively in `core/config.py` environment configuration, which no
admin endpoint anywhere (this one included) reads from or writes to.
This is the identical boundary ADR-0044 §4 draws for notification
provider secrets — restated here because Settings is exactly the kind
of generic mechanism a future, less careful addition could misuse for
that if this constraint isn't written down as a hard rule up front.

6. What this does NOT resolve

- Migrating the wider set of hardcoded operational constants across
  this codebase into `admin.settings` — deliberately not attempted
  here (Decision 2); each is its own future decision.
- Any actual feature-flag *consumer* — no code path checks
  `admin.settings` for a flag anywhere; adding one is a separate,
  feature-specific task.
