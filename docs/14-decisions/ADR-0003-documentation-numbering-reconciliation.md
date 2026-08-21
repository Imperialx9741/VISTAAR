ADR-0003 — Domain Design Location and Documentation Folder Numbering

Status: Accepted (structural/filing correction — no business content changed)
Date recorded: 2026-08-20
Deciders: Recorded from repository evidence during documentation/architecture
reconciliation.

1. Context

Six documents (database-design.md, api-contracts.md, event-contracts.md,
state-machines.md, security.md, testing-strategy.md, and
implementation-readiness.md) cite "Domain Design v1.0" as a document they are
derived from. The document exists — docs/04-database/design/domain-design.md
— but was filed inside the database folder rather than in its own top-level
location.

domain-design.md's own footer (§45, "What Comes Next") already declared its
intended canonical path explicitly:

  04-domain-design/domain-design.md       ← THIS
                  ↓
  05-database/database-design.md
                  ↓
  06-api/api-contracts.md
                  ↓
  07-events/event-contracts.md
                  ↓
  08-state-machines/state-machines.md
                  ↓
  09-security/security.md
                  ↓
  10-testing/testing-strategy.md

implementation-readiness.md §3 (Recommended Repository) and §78 (Current
Readiness) independently confirm the same intended sequence: 01-product,
02-business, 03-architecture, 04-domain-design, 05-database, 06-api,
07-events, 08-state-machines, 09-security, 10-testing.

The actual repository never created a 04-domain-design/ folder, and
database-design.md was filed at docs/04-database/ (keeping the "04" prefix)
rather than docs/05-database/. Because every document after it in the
sequence kept its own original folder number rather than shifting forward,
the actual folder sequence became:

  01-product, 02-business, 03-architecture, 04-database, 05-api, 06-events,
  07-state-machines, 08-security, 09-errors, 10-testing, 11-implementation,
  12-deployment, 13-project-management, 14-decisions

This left database-design.md's, api-contracts.md's, and event-contracts.md's
own "Next Document" footer sections referring to their own folder by the
wrong number (e.g. database-design.md's footer called itself
"05-database/database-design.md" while actually living in 04-database/).

The offset happens to resolve by the time it reaches 10-testing/, because an
unplanned docs/09-errors/ folder (currently empty, reserved for a future
error-catalog document) absorbs the one-folder gap between 08-security/ and
10-testing/.

Additionally, docs/11-implementation/ contained an accidentally duplicated
inner folder — docs/11-implementation/11-implementation/ — holding
implementation-readiness.md.

2. Decision

a. domain-design.md is relocated to docs/04-domain-design/domain-design.md,
   matching the path its own footer always specified. No content was
   changed; only the file's location.

b. implementation-readiness.md is relocated from
   docs/11-implementation/11-implementation/implementation-readiness.md to
   docs/11-implementation/implementation-readiness.md, removing the
   duplicated folder. No content was changed beyond the moves and the
   corrections in (c)–(d) below.

c. Existing numbered folders (04-database/, 05-api/, 06-events/,
   07-state-machines/, 08-security/, 09-errors/, 10-testing/,
   11-implementation/, 12-deployment/, 13-project-management/,
   14-decisions/) are NOT renamed. Renumbering five populated folders to
   match the originally-planned sequence would be a large, unnecessary
   structural change for a text-only inconsistency, and 09-errors/,
   12-deployment/, 13-project-management/, and 14-decisions/ were never part
   of the originally-planned 10-folder sequence in the first place — the
   repository has organically grown beyond that early plan. The actual
   folder names are treated as authoritative going forward.

d. Each document's own self-referential "Next Document" footer text is
   corrected to match the actual folder it lives in, rather than the
   originally-planned number:
   - database-design.md: "05-database" → "04-database ← THIS"
   - api-contracts.md: "06-api" → "05-api ← THIS"
   - event-contracts.md: "07-events" → "06-events ← THIS"
   - Each corrected chain also now lists 04-domain-design/domain-design.md
     as the preceding document and notes that 09-errors/ is a reserved,
     currently-empty folder not yet part of the chain.
   - implementation-readiness.md §3 and §78 are annotated (not rewritten) to
     show the actual folder name next to the originally-planned one, with a
     pointer to this ADR.

3. Consequences

- docs/04-database/design/ (now empty) was removed as part of the move.
- docs/11-implementation/11-implementation/ (now empty) was removed as part
  of the move.
- Two "04-"-numbered top-level folders now coexist: docs/04-domain-design/
  and docs/04-database/. This is a known, accepted quirk of keeping
  database-design.md's original folder name (2.c above) rather than
  renumbering it to 05-database/. It does not affect any tooling — nothing
  in apps/, packages/, or infrastructure/ references docs/ paths — and is
  recorded here rather than silently left unexplained.
- No business rule, API contract, event contract, database schema, or state
  machine content was changed by this ADR. This is a filing and
  cross-reference correction only.
