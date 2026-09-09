VISTAAR — Load Testing Plan (100,000-concurrent-user target)

Date: 2026-09-03
Author: Claude Code
Status: **Plan only — no benchmark has been run.** Per explicit
instruction: "Prepare a realistic load-testing plan for the
100,000-concurrent-user target. Do not make capacity claims without
benchmark evidence." Nothing in this document is a capacity claim; every
number under §4 is a worked example computed from real, already-shipped
client behavior, offered to size the test, not to promise an outcome.

1. What "100,000 concurrent users" needs to mean before it's testable

No source document in this project (business-rules.md,
technical-architecture.md, the roadmap) defines this target — it was
named directly in the owner's 2026-09-03 production-readiness
instruction, with no further specification. "Concurrent users" is
ambiguous by itself: a customer with the app open but no active ride
generates almost no backend traffic, while an ONLINE Sarthi generates
continuous background traffic (see §2). A load test needs one specific,
falsifiable definition, not the phrase itself. This plan proposes a
working definition and states it as an assumption requiring the owner's
confirmation, not a decision made silently:

**Working assumption**: "100,000 concurrent users" = 100,000 app
sessions open at the same time, split across three states that drive
very different load:
- **Online Sarthis** (actively available for rides — the highest
  per-user load, continuous polling; see §2).
- **Customers with an active or searching ride** (moderate load —
  polling ride status).
- **Idle sessions** (app open, no active ride, no ONLINE status — near-
  zero backend load; periodic token refresh only).

The split between these three (e.g. 20% online Sarthi / 30% active
customer / 50% idle) is not defined anywhere and directly determines the
required request rate. §4 works a specific example split for
illustration; **the owner should confirm or correct this split before
any real benchmark run is sized against it** — testing the wrong split
produces a number that answers a question nobody asked.

2. Real traffic shape — grounded in the actual shipped client, not assumed

VISTAAR has no push channel (no WebSocket, no FCM-driven live event) for
location or ride-offer delivery — confirmed by a repo-wide search of
`src/modules/*/router.py`. Every real-time-feeling interaction in the
shipped mobile app is **client-side polling** against plain REST
endpoints, at intervals hardcoded in the Flutter client today:

| Client behavior | Interval | Source |
| :-- | :-- | :-- |
| Driver location update (`POST /api/v1/drivers/me/location`) | every 5s, while ONLINE | `apps/mobile/lib/features/home/sarthi_home_screen.dart` |
| Driver ride-offer poll (`GET /api/v1/drivers/me/ride-offers`) | every 4s, while ONLINE | same file |
| Ride status poll (customer + driver, active ride) | every 4s | `apps/mobile/lib/features/rides/ride_status_screen.dart`, `ride_execution_screen.dart` |

This means the dominant load at any real scale is **polling, not
business-action throughput** — ride creation, OTP, wallet recharge, etc.
happen orders of magnitude less often per user than these three
background polls. A load test that only exercises "interesting" write
endpoints (book a ride, accept an offer) and ignores background polling
volume will systematically understate real load. §5's test scenarios
weight polling accordingly.

`POST /drivers/me/location` writes into Redis via
`geo.upsert_driver_location` (not Postgres) — this is the single
highest-frequency write path in the entire system at scale, and it never
touches the RDS instance. Every candidate-search read in matching
(`MatchingService.dispatch_offer`, `_CANDIDATE_LIMIT = 20` per dispatch)
also goes through Redis geo queries, not Postgres. This means Redis
(ElastiCache), not RDS, is the more likely first bottleneck for
location/matching load specifically — see §3's infrastructure findings.

3. Current infrastructure — what the AWS baseline (ADR-0063) actually
provisions today, and where it will bind first

Read directly from `infrastructure/terraform/aws/variables.tf` and
`infrastructure/kubernetes/backend-hpa.yaml`. **Updated 2026-09-03**:
`docs/12-deployment/aws-cost-capacity-review-2026-09-03.md` reviewed
these defaults directly — implementing the clear-cut availability
recommendations (RDS Multi-AZ, an ElastiCache replica) while
deliberately leaving instance-type/count sizing unchanged, pending the
real load-test run this document itself describes. Restated here
because they directly bound what any load test against a freshly-
provisioned environment would show, before any tuning:

| Component | Current default | Why it matters at 100k-user scale |
| :-- | :-- | :-- |
| Backend pods (HPA) | `minReplicas: 2`, `maxReplicas: 6`, scale at 70% CPU | Hard ceiling of 6 pods regardless of load — will saturate long before 100k concurrent sessions' worth of polling traffic, by design, until raised |
| Backend process model | 1 uvicorn worker per pod, no `--workers` flag (`Dockerfile` `CMD`) | Each pod is a single ASGI process; concurrency within a pod comes from asyncio + Starlette's threadpool for sync code, not OS processes |
| DB engine | `create_engine(...)` — **sync** SQLAlchemy engine, default pool (`pool_size=5`, `max_overflow=10` — neither set explicitly in `core/database.py`, so SQLAlchemy's defaults apply) | Every DB-touching request blocks a threadpool thread for the query's duration; at most 15 concurrent DB operations per pod before requests queue, regardless of CPU headroom |
| EKS node group | `m6i.large` (2 vCPU/8GB), `min=2`/`max=5` nodes | Bounds how many pods can actually schedule even if HPA's ceiling were raised |
| RDS PostgreSQL | `db.m6i.large`, single instance, no read replica | All reads and writes hit one instance; `MatchingService`/`RideService`/`WalletService` are all synchronous Postgres reads+writes on the request path |
| ElastiCache Redis | `cache.m6g.large`, `num_cache_clusters = 1`, no replica | Single node, no failover — also the busiest component per §2, since every location update and matching candidate search goes through it |
| Kafka | Self-hosted, single EC2 instance (ADR-0063 §3) | Single point of failure and throughput ceiling for every outbox-published domain event; not horizontally scaled |

**None of this has been benchmarked** — these are read-from-code facts
about what's provisioned by default, not measurements. The honest
starting expectation is that the *current* defaults will not sustain a
100,000-concurrent-user polling load without both infrastructure scaling
(raising HPA/node-group ceilings, adding an RDS read replica, sizing the
connection pool explicitly) and possibly application changes (an async
DB driver, given the sync-engine-plus-threadpool ceiling above) — this
plan's job is to produce the evidence for exactly where the current
setup actually breaks, not to assume where it will.

4. Worked example — turning §1's assumption into a target request rate

**Illustrative only, using the working 20/30/50 split from §1.** If the
owner confirms a different split, recompute before using this number to
size a real test.

- 20,000 online Sarthis × (1 location update / 5s + 1 offer poll / 4s)
  ≈ 20,000 × (0.2 + 0.25) req/s ≈ **9,000 req/s**
- 30,000 active-ride customers × 1 status poll / 4s ≈ **7,500 req/s**
- 50,000 idle sessions ≈ negligible (occasional token refresh only)
- **≈ 16,500 req/s of background polling alone**, before counting ride
  creation, OTP, matching dispatch, offer accept/reject, wallet
  operations, or admin traffic layered on top.

For comparison: the current HPA ceiling (§3) is 6 backend pods. Whatever
per-pod req/s a single pod can actually sustain (an unmeasured number —
§5 produces it) needs to clear roughly **2,750 req/s per pod** at 6 pods
to meet this illustrative 16,500 req/s figure — almost certainly
requiring both a materially higher `maxReplicas` and node-group ceiling
than today's defaults, not just "the same cluster running longer."

5. Test methodology

5.1 **Tool**: [k6](https://k6.io/) (Grafana Labs) — scriptable in
JavaScript, native Prometheus remote-write output (integrates directly
with the Grafana/Prometheus stack ADR-0053 already stood up),
distributed/cloud execution mode for reaching six-figure virtual-user
counts without a single test-runner machine being the bottleneck. No
load-testing tool exists in this repo today; this is a new tool choice,
not a business/product decision, so it's made here rather than deferred.

5.2 **Environment**: a real staging AWS environment provisioned from
`infrastructure/terraform/aws/`, sized identically to whatever
production will run (not a scaled-down approximation — HPA/connection-
pool ceilings behave nonlinearly, so testing a smaller environment and
extrapolating would itself be an unsupported capacity claim). **This
cannot run in the current environment** — no AWS credentials exist here
(deployment-runbook.md §1). This is the plan's primary real blocker: it
can be fully authored and staged, but not executed, until AWS access is
provided.

5.3 **Staged ramp, not a single jump to 100k.** Each stage runs to a
stable plateau (steady error rate, steady p95 latency) before the next:

1. **Smoke** (50 VUs) — confirms the test scripts and staging
   environment work at all; catches scripting bugs cheaply.
2. **Baseline** (500 → 2,500 VUs) — first real signal on per-pod
   throughput and where the first bottleneck (§3's candidates: DB
   connection pool, Redis, HPA ceiling) actually shows up.
3. **Design load** (10,000 → 25,000 VUs) — a plausible "real early
   launch" scale; the number that matters most for near-term planning.
4. **Target load** (100,000 VUs, using §4's confirmed split) — the
   named target. Only run once stages 1–3 identify and address (or
   consciously accept) the bottlenecks found at smaller scale — running
   stage 4 first would just reproduce stage 2's bottleneck at higher
   cost without new information.
5. **Soak** (a sustained 2–4 hour run at design load, not target load,
   given cost) — catches slow leaks (connection pool exhaustion, memory
   growth) a short spike test wouldn't surface.

5.4 **Scenarios** (weighted by §2's real traffic shape, not evenly):

| Scenario | Weight | Endpoints exercised |
| :-- | :-- | :-- |
| Driver background polling | ~55% of request volume | `POST /drivers/me/location`, `GET /drivers/me/ride-offers` |
| Ride status polling | ~45% of request volume | `GET /api/v1/rides/{ride_id}` |
| Ride lifecycle (low frequency, high importance) | small % of volume, scripted as a full flow | OTP request/verify → book ride → matching dispatch → offer accept → ride start/complete → wallet debit |
| Wallet recharge | low frequency | Razorpay order creation (against Razorpay **test** credentials only — ADR-0060; never load-test against a real payment gateway) |
| Admin/reporting | low frequency, separate VU pool | representative admin dashboard/report endpoints, since `RATE_LIMIT_ADMIN_API_PER_MINUTE` (300/min) already caps this independently |

5.5 **Metrics captured per stage** (via the existing Prometheus/Grafana
stack, ADR-0053, plus k6's own output):
- p50/p95/p99 request latency, per endpoint (not just an overall
  average — the matching-dispatch and wallet-debit paths are expected to
  be materially slower than a location-update write).
- Error rate, per endpoint and status code (a 5xx spike matters
  differently from a 429 rate-limit response — ADR-0061's limits are
  expected to start rejecting traffic well before 100k users if VUs
  don't authenticate as distinct accounts; the test must simulate
  distinct driver/customer identities, not hammer one account).
- Backend pod CPU/memory and replica count over time (confirms whether
  HPA scaled as expected, or hit its ceiling).
- RDS: connections in use, CPU, read/write IOPS (via the
  `HighErrorRate`/`HighLatencyP99` alerts already wired in
  `monitoring-configmap.yaml`, plus RDS's own CloudWatch metrics once a
  real instance exists).
- ElastiCache: CPU, connected clients, evictions.
- Kafka EC2: CPU, disk I/O (the self-hosted single instance is a named
  risk in §3).

6. What this plan explicitly does not do

- Does not claim any RPS/VU number the current or a scaled infrastructure
  can sustain — every number in §4 is a target to test against, derived
  from real client polling intervals, not a measured result.
- Does not run any test — no AWS environment is reachable from this
  environment. Test scripts can be authored and reviewed now; execution
  is blocked on AWS access, consistent with items 4/5's own scope.
- Does not decide the §1 user-mix split, the final HPA/node-group/RDS
  sizing to test against, or a budget ceiling for a k6 Cloud run at
  100k VUs (k6 Cloud's own pricing scales with VU-hours) — these are
  cost/product decisions for the owner, not invented here.
- Does not test the mobile app's own client-side behavior under load
  (battery/network conditions on real devices) — this plan is a backend
  capacity test only.

7. Next steps, in order

1. Owner confirms or corrects §1's user-mix split.
2. Author the actual k6 scripts against the five §5.4 scenarios (real,
   runnable code — not part of this planning pass; a follow-up
   implementation task).
3. Provision a staging AWS environment from
   `infrastructure/terraform/aws/` (blocked on AWS access —
   deployment-runbook.md §1).
4. Run stages 1–3 of §5.3, capture real numbers, identify the first
   real bottleneck.
5. Only then decide whether stage 4 (100k VUs) is run as-is or after a
   round of the tuning §3 already flags as likely necessary (raise HPA/
   node-group ceilings, add an RDS read replica, set an explicit
   connection-pool size, consider an async DB driver).
