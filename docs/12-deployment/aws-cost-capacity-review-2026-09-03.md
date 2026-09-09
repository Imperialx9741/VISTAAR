VISTAAR — AWS Cost / Capacity Review

Date: 2026-09-03
Author: Claude Code
Status: A recommendation for **initial production sizing**, not a final
budget approval and not a capacity guarantee. Per explicit instruction:
"Do not claim that the initial configuration supports 100,000
concurrent users without actual load-test evidence." Nothing in this
document claims a specific request-per-second or concurrent-user
ceiling for the sizing recommended here — that number only exists once
`docs/10-testing/load-testing-plan-2026-09-03.md` is actually run
against a real environment.

1. Scope and method

This reviews `infrastructure/terraform/aws/`'s defaults — read directly
from `variables.tf`/`rds.tf`/`elasticache.tf`/`eks.tf`/`kafka.tf`, not
assumed — against what a real initial production launch needs, and
recommends what to change before the first real `apply`. Two kinds of
recommendation are made, and treated differently:

- **Availability/redundancy** (Multi-AZ RDS, a Redis replica) — a
  clear-cut "do this regardless of traffic volume" call, standard
  practice for any real production system handling money and live ride
  state. Implemented directly in this pass (`rds.tf`/`elasticache.tf`),
  not just written up as a suggestion — see each file's own updated
  comment.
- **Throughput sizing** (instance types/counts, autoscaling ceilings) —
  genuinely depends on measured load this environment has never had.
  Recommended as a *range* and a *process* below, not silently baked
  into a new default — bumping instance counts without evidence would
  itself be exactly the kind of unsupported capacity claim the owner's
  instruction warns against, just expressed as a Terraform default
  instead of a sentence.

2. Recommended initial production sizing

| Component | Current default | Recommendation for launch | Why |
| :-- | :-- | :-- | :-- |
| EKS nodes | `m6i.large` (2 vCPU/8GB), min 2 / max 5 | **Keep as-is** | Already reasonable headroom for HPA's own 2–6 backend pods (§3.1) plus the Celery worker and monitoring stack (Prometheus/Grafana/Alertmanager — lightweight, ~50–100m CPU requests each); re-evaluate only after real load-test data exists (§7) |
| Backend HPA | 2–6 pods, scale at 70% CPU | **Keep as-is** | Same reasoning — this is a launch-scale ceiling, not a 100k-scale one; §7 gives the process for raising it with evidence |
| RDS | `db.m6i.large`, single-AZ, 100GB | **`db.m6i.large`, Multi-AZ** (implemented) | Instance class is a reasonable launch size (2 vCPU/8GB, matches node sizing); Multi-AZ is the real change — automatic failover for the ride/wallet/penalty ledger, independent of traffic volume |
| ElastiCache | `cache.m6g.large`, 1 node, no failover | **`cache.m6g.large` × 2 nodes, automatic failover** (implemented) | Same reasoning as RDS — a replica removes a single point of failure for the live matching/rate-limiting store, regardless of scale |
| Kafka | Self-hosted, single `m6i.large` EC2 | **Keep as-is, sizing-wise** | Instance size is reasonable for launch-scale event volume (ride/wallet/notification events); redundancy is a known, already-documented gap (ADR-0063 §3), not resolved by this pass — see §6 |
| ALB | Newly added (ADR-0067) | **Keep default ALB settings** | No capacity concern at launch scale; ALB itself scales automatically far beyond what this platform needs at any realistic near-term traffic level |
| S3 | Standard storage class, versioned | **Keep as-is** | Object storage for driver documents/evidence — negligible volume and cost at launch scale |

3. EKS compute/node sizing — the detail behind the table

3.1 **Why "keep as-is" isn't "unreviewed."** `backend-deployment.yaml`
requests 250m CPU / 256Mi memory per pod, limits 1 CPU / 512Mi. At
HPA's own ceiling (6 pods), that's up to 6 vCPU of demand; an
`m6i.large` node has 2 vCPU (a portion reserved for the kubelet/system
daemons, roughly 1.7–1.8 allocatable). `node_count_max = 5` gives
~8.5–9 allocatable vCPU across the node group — enough for 6 backend
pods at their CPU *limit* simultaneously, plus the Celery worker and
monitoring pods, without needing every pod to hit its ceiling at once
(the realistic case, not the worst case). This is arithmetic, not a
guess — but it says "the current ceiling is internally consistent,"
not "the current ceiling is enough for 100k users."

3.2 **A real, higher-leverage finding than instance count**, carried
forward from `docs/10-testing/load-testing-plan-2026-09-03.md` §3:
the backend runs a **single uvicorn worker process per pod** (no
`--workers` flag in `apps/backend/Dockerfile`'s `CMD`) with a **sync**
SQLAlchemy engine and SQLAlchemy's *default* connection pool
(`pool_size=5`, `max_overflow=10` — neither set explicitly). Before
spending more on node/pod *count*, the cheaper first lever is very
likely process-level: running multiple uvicorn/gunicorn worker
processes per pod (each with its own connection pool) would raise
per-pod throughput without provisioning a single additional node. This
is an application-level change, not a Terraform sizing knob — flagged
here because a cost/capacity review that only turns infrastructure
dials while leaving a single-process bottleneck in place would be
recommending the more expensive fix first. Not changed in this pass
(out of this review's own scope); a real candidate for the "before the
first load-test stage" checklist in the load-testing plan.

4. RDS sizing

`db.m6i.large` (2 vCPU/8GB) is a reasonable instance class for launch —
matches the EKS node type in vCPU/memory ratio, a sensible default
absent real query-load data. **Multi-AZ, implemented this pass**:
automatic failover to a synchronously-replicated standby in a second
AZ. `backup_retention_period = 7` (unchanged) and `deletion_protection
= true` (unchanged) were already reasonable. Storage (`100GB`,
`gp3`-class default) is generous for a launch-scale ride/wallet/penalty
ledger — PostGIS geometry columns and JSON audit fields are the main
growth vectors, worth re-checking storage utilization a few months in
rather than over-provisioning now.

5. Redis (ElastiCache) sizing

`cache.m6g.large` is a reasonable node size for the matching/rate-
limiting workload (security.md §83: never the source of truth for
anything financial, so a cache miss/restart loses no authoritative
data — but it IS the live store behind ride matching and every
rate-limit counter, so availability still matters). **A second node +
automatic failover, implemented this pass** — the clear-cut
availability call, independent of traffic volume.

6. Kafka sizing

Self-hosted on a single `m6i.large` EC2 instance (ADR-0063 §3's own
already-recorded reasoning for self-hosting over AWS MSK — not
revisited here, out of this review's scope). Reasonable sizing for
launch-scale event volume (ride lifecycle, wallet, notification events
— see event-contracts.md for the full list). **Not made redundant in
this pass** — unlike RDS/Redis, a second Kafka broker is a materially
bigger change (a real multi-broker cluster, replication factor,
ZooKeeper/KRaft coordination — not a one-line Terraform flag flip the
way `multi_az`/`automatic_failover_enabled` were), so it's named here
as a known gap rather than silently addressed. Revisit once real event
volume is measured; a single-broker EC2 instance is a genuine single
point of failure for every domain event in the system today.

7. Autoscaling approach

- **Backend**: `backend-hpa.yaml`'s CPU-based HorizontalPodAutoscaler
  (2–6 replicas, unchanged) — requires the `metrics-server` add-on
  installed explicitly on EKS (unlike the superseded DOKS target,
  which enabled it by default; that file's own comment already flags
  this).
- **EKS nodes**: the managed node group's own `min_size`/`max_size`
  (2/5, unchanged) scales node count to fit scheduled pods, but EKS
  managed node groups don't natively scale *themselves* in response to
  pending/unschedulable pods without the Cluster Autoscaler (or Karpenter)
  also installed — **not currently installed anywhere in this stack**,
  a real gap: today, if HPA wants to schedule a 7th backend pod beyond
  what 5 nodes can fit, it stays Pending rather than triggering a new
  node. Flagged as a concrete next step, not silently assumed to work.
- **RDS/ElastiCache**: no autoscaling — vertical (instance class) or
  horizontal (read replicas/additional cache nodes) scaling are both
  manual `terraform apply` changes, standard for these services at this
  scale; RDS Storage Autoscaling (`max_allocated_storage`, already set
  to `2×` the base allocation in `rds.tf`) is the one automatic
  exception, already configured.

8. Estimated monthly AWS cost (ap-south-1)

**Approximate only — this environment could not reliably fetch live
current AWS pricing** (attempted directly; ap-south-1-specific
on-demand rates are served by AWS's own interactive pricing tools,
which don't render as static content this environment can read).
The figures below are rough-order-of-magnitude, based on well-known
general AWS pricing patterns, not a live Pricing Calculator run.
**Verify against the real [AWS Pricing Calculator](https://calculator.aws/)
before treating this as a budget commitment.**

| Line item | Rough monthly estimate (USD) |
| :-- | --: |
| EKS control plane (flat fee) | ~$73 |
| EKS nodes, 2–5× `m6i.large` (on-demand) | ~$165–$410 |
| RDS `db.m6i.large`, Multi-AZ + 100GB storage | ~$370–$400 |
| ElastiCache, 2× `cache.m6g.large` | ~$170–$180 |
| Kafka EC2, 1× `m6i.large` + EBS | ~$90 |
| NAT Gateway (base hourly, excl. data processing) | ~$33 |
| ALB (base hourly, excl. LCU usage) | ~$16 |
| S3 + ECR (launch-scale volume) | ~$5–$10 |
| **Subtotal (base, before usage-driven costs)** | **~$920–$1,100/month** |
| Data transfer out, ALB LCU-hours, NAT data processing | **Not estimated — usage-driven, no real traffic to measure yet** |

This subtotal reflects the sizing in §2 (Multi-AZ RDS + Redis replica
included, node/HPA ceilings unchanged from today's defaults). The
biggest source of real variance once live is data transfer and ALB
request volume — both scale with actual usage this review has no way
to predict without the load-testing plan's own real run.

9. Scaling path toward the 100,000-concurrent-user target

Matches `docs/10-testing/load-testing-plan-2026-09-03.md`'s own staged
ramp (§5.3 there) — restated here as an infrastructure lens on the same
plan, not a competing one:

1. **Launch, this sizing.** Ship with §2's recommendations. No load
   test has run yet at this stage.
2. **Baseline load test** (500–2,500 VUs, the load-testing plan's stage
   2) against this exact sizing. This is where the app-level single-
   worker-process bottleneck (§3.2) most likely shows up first —
   fixing that is probably cheaper than the next infrastructure step.
3. **Install the Cluster Autoscaler/Karpenter** (§7's named gap) before
   raising HPA's `maxReplicas` further — otherwise a higher HPA
   ceiling just produces more Pending pods, not more capacity.
4. **Design-load test** (10,000–25,000 VUs) — likely the point at
   which RDS/Redis instance *class* (not just replica count) needs
   re-evaluating, informed by real CloudWatch metrics from stage 2/3,
   not guessed at here.
5. **Target-load test** (100,000 VUs, the load-testing plan's own
   stage 4) — only after 2–4 are done and their findings acted on.
   Whatever sizing survives that run is the first real, evidence-backed
   capacity number for this platform — not this document, and not any
   number written before it.

10. What this review explicitly does not do

- Does not claim the sizing in §2 supports any specific concurrent-user
  or request-per-second figure — no load test has been run.
- Does not commit to the §8 cost figures as a final budget — explicitly
  approximate, unverified against live AWS pricing.
- Does not resolve Kafka's own redundancy gap (§6) or install the
  Cluster Autoscaler/Karpenter (§7) — both named as real next steps,
  neither implemented in this pass.
- Does not change EKS node type/count or HPA ceilings — those stay
  exactly as they were, deliberately, pending real load-test evidence
  rather than a guess dressed up as a recommendation.
