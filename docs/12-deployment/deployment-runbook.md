VISTAAR — Deployment Runbook

Date: 2026-09-02, rewritten for AWS 2026-09-03 (ADR-0063 — the owner
switched the deployment target from DigitalOcean to AWS, explicitly
instructing "Do not use DigitalOcean"). Consolidates and verifies
`infrastructure/terraform/aws/README.md`,
`infrastructure/kubernetes/README.md`, `.github/workflows/deploy-aws.yml`,
and ADR-0063 into one operational sequence, rather than duplicating them —
this document links to the authoritative source for each step and adds
what none of them individually cover: a rollback procedure, a
backup/restore procedure, and a single consolidated list of every open
decision still blocking a real deploy.

1. What's being deployed, and where things stand

VISTAAR's backend deployment target — AWS EKS, RDS PostgreSQL
(PostGIS-enabled), ElastiCache for Redis, a self-hosted Kafka EC2
instance, and S3 object storage — was decided and recorded in ADR-0063
(2026-09-03, superseding ADR-0035's DigitalOcean choice), not a decision
this document makes. All of the infrastructure code for it already
exists:

- `infrastructure/terraform/aws/` — provisions the cluster and managed
  services.
- `infrastructure/kubernetes/` — the backend, Celery worker, and
  monitoring (Prometheus/Grafana) manifests. **Unchanged by the AWS
  switch** — plain Kubernetes YAML, provider-agnostic.
- `apps/backend/Dockerfile` — the production image. **Also unchanged**
  by the switch — a plain multi-stage Docker build, provider-agnostic.
- `.github/workflows/deploy-aws.yml` — a manual-dispatch GitHub Actions
  workflow that builds, pushes, and applies the above.
  `.github/workflows/deploy-do.yml` still exists but is deprecated —
  see its own header comment.

**None of it has ever been applied against a real AWS account** —
ADR-0063 §4 recorded this explicitly, and it remains true today: no AWS
credentials exist in this environment, and this environment additionally
has no `terraform` CLI installed at all (unlike the superseded
DigitalOcean module, which an earlier session did validate against the
real provider schema — see `infrastructure/terraform/aws/README.md`'s
own honesty callout). What this pass verified for real, and what
remains only reviewed-by-reading, is in §6.

2. Prerequisites — what the operator needs before starting

- An AWS account and credentials with permission to create VPC, EKS,
  RDS, ElastiCache, EC2, S3, ECR, and IAM resources.
- `terraform` >= 1.7.0 installed (not available in the environment this
  runbook was written in — see §6).
- `kubectl` and the AWS CLI (`aws`) installed.
- `TF_VAR_postgres_password` (a real, randomly generated password) and
  `TF_VAR_kafka_ami_id` (a real, current Ubuntu 22.04 AMI id for the
  target region) — both required by `infrastructure/terraform/aws/`,
  neither has a default on purpose.
- An IAM OIDC identity provider for
  `token.actions.githubusercontent.com` in the AWS account, plus an IAM
  role `deploy-aws.yml` can assume via that provider — a one-time,
  account-level setup step outside Terraform's scope here (see that
  workflow's own header comment).
- The four GitHub Actions repository secrets `deploy-aws.yml` requires:
  `AWS_ROLE_TO_ASSUME`, `AWS_REGION`, `ECR_REPOSITORY_URI`,
  `EKS_CLUSTER_NAME` — none exist yet.
- A real `JWT_SECRET` (e.g. `openssl rand -hex 32`) — `core/config.py`
  hard-rejects the placeholder default outside `APP_ENV=development`
  (security-review-2026-09-02.md finding 2.1), so this is not optional.
- A domain name for the backend API, and an ACM certificate requested
  and validated for it (`aws acm request-certificate`) — neither is
  decided/done anywhere in this project yet. (No contact email needed:
  TLS is ACM-terminated at the ALB, not cert-manager/Let's Encrypt —
  see the ingress controller note below.)
- The AWS Load Balancer Controller installed on the cluster (owner
  decision, 2026-09-03 — AWS ALB, explicitly not community
  Ingress-NGINX; `infrastructure/terraform/aws/eks.tf` provisions its
  IAM role, the controller software itself is a Helm chart install —
  see `infrastructure/kubernetes/README.md`'s exact steps).

3. First-time environment setup

Run in this order — each step's own file has the authoritative detail;
this is the sequence, not a restatement of every flag.

1. **Provision infrastructure** — follow
   `infrastructure/terraform/aws/README.md` (`terraform init`,
   `validate`, `plan`, `apply`). Before the first real `apply`, review
   `variables.tf`'s defaults — region (`ap-south-1`), instance types,
   and counts are reasonable starting points the README itself says are
   "not an approved cost/capacity decision," not values this runbook
   approves either.
2. **Install the AWS Load Balancer Controller** onto the new cluster
   (a Helm chart — `infrastructure/kubernetes/backend-ingress.yaml`
   assumes it already exists; not installed by Terraform, though the
   IAM role it needs is). No cert-manager needed — see §2's own note
   and `infrastructure/kubernetes/README.md`'s exact steps.
3. **The container registry is already provisioned by Terraform** —
   `infrastructure/terraform/aws/ecr.tf` creates it as part of step 1,
   unlike the superseded DigitalOcean plan, where this was a separate,
   never-completed manual step (deployment-runbook.md's own previous
   revision, §5.1). `terraform output ecr_repository_url` gives the
   value to feed into the `ECR_REPOSITORY_URI` secret.
4. **Copy `terraform output` values into real Kubernetes Secrets** —
   `infrastructure/kubernetes/backend-secret.example.yaml` →
   `backend-secret.yaml` (git-ignored template, per that folder's own
   README), same for `grafana-secret.example.yaml` →
   `grafana-secret.yaml`. Never commit the filled-in files. Leave
   `STORAGE_ENDPOINT` blank — real AWS S3 needs no override, unlike the
   superseded DigitalOcean Spaces setup.
5. **Apply the Kubernetes manifests** in the exact order
   `infrastructure/kubernetes/README.md`'s "Apply order" section
   documents (namespace → configmap → secret → migration Job → wait →
   deployment → service → HPA → ingress → celery worker → monitoring).
   That sequence is reproduced there, not duplicated here, to avoid two
   copies drifting.
6. **Verify** — see §7.

4. Ongoing deploys

`.github/workflows/deploy-aws.yml` automates build → push → migrate →
deploy once the four repository secrets in §2 exist. It is deliberately
`workflow_dispatch`-only (manual "Run workflow" click), not triggered on
every push to `main` — the workflow's own header comment records this as
a real operational decision the owner should make explicitly (how much CI
verification should gate a production rollout, whether staging/production
need separate approval), not one this runbook invents by silently wiring
it to `push`.

Note what the workflow does **not** do: there is no automated rollback
step, and no smoke-test/health-check gate between "deployment applied"
and "considered successful" beyond `kubectl rollout status`'s own
timeout. See §8 for the manual rollback procedure this gap requires.

5. Open decisions — not made by this runbook

Per standing project discipline, these are documented as open, not
decided silently:

5.1 **~~Container registry choice~~ — RESOLVED (ADR-0063).** ECR is
provisioned directly by `infrastructure/terraform/aws/ecr.tf` — no
longer an open manual step the way DigitalOcean Container Registry was
under the superseded plan.

5.2 **~~Admin Web's deployment target~~ — RESOLVED 2026-09-03.** Owner
decision: AWS Amplify Hosting, kept in its own separate Terraform
module (`infrastructure/terraform/aws-admin-web/`) from the backend's
EKS infrastructure. `platform = "WEB_COMPUTE"` (SSR), not a static
export — verified by inspecting `apps/admin-web` directly: 18
dynamically-segmented routes with no `generateStaticParams`, which a
static export cannot serve at all. See that module's own README for
the full inspection and the GitHub-connection step still needed by
hand (a one-time Console action, deliberately not automated via a
stored access token).

5.3 **~~Remote Terraform state backend~~ — RESOLVED 2026-09-03.** A new
bootstrap module, `infrastructure/terraform/aws-state-backend/`,
provisions the S3 bucket (versioned, encrypted, private) + DynamoDB lock
table; `infrastructure/terraform/aws/versions.tf` now declares a
`backend "s3" {}` block, filled in at `terraform init` time via
`backend.hcl` (template: `backend.hcl.example`). Still needs a real
`terraform apply` of the bootstrap module before the main module's first
`init -backend-config=...` — not possible without AWS credentials, same
as everything else in this runbook's §6 "not verified" list — but the
config itself is no longer an open gap.

5.4 **~~Cost/capacity review~~ — DONE 2026-09-03, see
`aws-cost-capacity-review-2026-09-03.md`.** Availability/redundancy
recommendations (RDS Multi-AZ, an ElastiCache replica) are implemented
directly in `rds.tf`/`elasticache.tf`; instance-type/count sizing is
kept at today's defaults deliberately, pending real load-test evidence
rather than a guessed bump — see that document's own §2/§9 for the
full reasoning and the staged path to a real number. **Not** a final
budget approval (the document's own cost estimate is explicitly
approximate, unverified against live AWS pricing) and **not** a
100,000-concurrent-user capacity claim.

5.5 **Domain name** for `backend-ingress.yaml`, and an ACM certificate
requested/validated for it. (No separate "TLS contact email" needed —
resolved alongside §5.6: ACM-terminated TLS at the ALB has no Let's
Encrypt-style registration contact the way cert-manager did.)

5.6 **~~Which ingress controller for EKS~~ — RESOLVED 2026-09-03.**
Owner decision: AWS Load Balancer Controller (ALB), explicitly not
community Ingress-NGINX. `infrastructure/terraform/aws/eks.tf` now
provisions the OIDC provider + IRSA IAM role it needs; the controller
software itself installs via Helm — see
`infrastructure/kubernetes/README.md`'s "Installing the AWS Load
Balancer Controller" for the exact steps. `backend-ingress.yaml` is
rewritten for the `alb` ingress class with ACM-terminated TLS
(`alb.ingress.kubernetes.io/certificate-arn`) — cert-manager is no
longer needed for this Ingress at all.

5.7 **IRSA for S3 access.** `infrastructure/terraform/aws/s3.tf`
still provisions a static IAM user/access key for the backend to reach
S3 — works with zero Kubernetes manifest changes, but IAM Roles for
Service Accounts (no static credentials in the cluster at all) is the more
secure AWS-native alternative. Closer to reach than before: the EKS
cluster's OIDC provider now exists (`eks.tf`, added 2026-09-03 for the
AWS Load Balancer Controller's own IRSA role, §5.6) — only a second
IAM role plus a ServiceAccount annotation would be needed now, not a
new OIDC provider too. Still not done here — not asked for, and a
working static-credential path already exists.

5.8 **AWS MSK vs. self-hosted Kafka.** `infrastructure/terraform/aws/
kafka.tf` self-hosts Kafka on a single EC2 instance, matching the
superseded DigitalOcean plan's own single-Droplet approach — see
ADR-0063 §3 for why this doesn't default to MSK (AWS's genuinely
managed Kafka product) even though, unlike DigitalOcean, AWS actually
offers one.

5.9 **Rate limiting architecture.** The application-level half is built
(ADR-0061, 2026-09-02): ships purely in the existing backend image, no
new Kubernetes-level component needed for it. A second, coarser
**edge-level** layer for unauthenticated/pre-session abuse remains
open — on AWS this would typically be AWS WAF attached to the ALB/API
Gateway, now that the real cloud target is known, but this specific
design has not been built yet; still an open decision, not silently
assumed.

5.10 **Notification channel for alerts.** `alertmanager-secret.example.yaml`
ships a syntactically valid but non-functional placeholder receiver URL
(verified for real that a bare invalid string crash-loops the pod at
config-load time — see that file's own comment) so the pod starts
cleanly either way. Which real channel to use (Slack, PagerDuty,
Opsgenie, email) is a genuine open decision, not invented here — until
one is chosen and wired in, alerts evaluate and are visible in
Alertmanager's own UI but notify no one.

6. What was actually verified in this pass, and what wasn't

Honest accounting, since "the files exist and read correctly" is not the
same claim as "this was tested":

**Verified for real, this pass:**
- `docker build` on `apps/backend/Dockerfile` — succeeds. Unaffected by
  the AWS switch (the Dockerfile is provider-agnostic) — this was last
  independently re-verified 2026-09-03 after switching to a committed
  dependency lockfile (security-review-pass-2-2026-09-03.md §3.2), not
  re-run again specifically for the AWS documentation rewrite, since
  nothing about the image itself changed for that.
- `docker run` on the built image, against local Postgres/Redis (Kafka
  intentionally left unreachable to confirm the documented
  "degrades, doesn't crash" behavior) — the container started, logged
  the expected Kafka-retry backoff without crashing, and `GET /health`
  returned `200 {"status":"OK"}` for real, over a real HTTP request to
  the running container.
- The same running container's response headers — `X-Content-Type-
  Options`, `Referrer-Policy`, `X-Frame-Options`,
  `Strict-Transport-Security`, and `Content-Security-Policy` were all
  present and correctly valued, confirming `SecurityHeadersMiddleware`
  (ADR-0036) actually works in the production image, not only in tests.
- The container runs as the non-root `vistaar` user (`docker exec ...
  whoami`), matching security.md §74.
- All 14 YAML files under `infrastructure/kubernetes/` parse as
  structurally valid YAML (Python's `yaml.safe_load_all`, checking
  document count per file matches what `infrastructure/kubernetes/
  README.md`'s table describes — e.g. `backend-ingress.yaml`'s 2
  documents, `monitoring-configmap.yaml`'s 4). Unaffected by the AWS
  switch — these manifests never referenced DigitalOcean at all.
- `.github/workflows/deploy-aws.yml` and `ci.yml` parse as structurally
  valid YAML (`yaml.safe_load`).
- The alerting addition (2026-09-03) — `monitoring-configmap.yaml`'s
  `vistaar-prometheus-rules` and `alertmanager-secret.example.yaml`'s
  embedded configs — were extracted from their ConfigMap/Secret YAML and
  validated for real against the actual binaries: `promtool check
  config`/`check rules` against Prometheus v2.53.0, `amtool check-config`
  against Alertmanager v0.27.0, and both images were actually started via
  `docker run` with these exact configs mounted and confirmed to reach a
  healthy, non-crashing state in their logs (not just "the file parses as
  YAML"). This caught one real bug before it shipped: the first
  Alertmanager draft used `envsubst` in a shell entrypoint override to
  inject the webhook URL from an env var, but `prom/alertmanager`'s image
  has no `envsubst` binary — confirmed directly, then fixed by moving the
  whole config (webhook URL included) into the Secret instead, which
  needs no substitution step at all.

**Not verified — genuine environment limits, not skipped by choice:**
- `terraform init`/`validate`/`plan` against `infrastructure/terraform/
  aws/` — the `terraform` CLI is not installed in this environment, and
  none was added for this rewrite. The AWS Terraform files were
  reviewed by reading only. This is a real regression in verification
  depth versus the superseded DigitalOcean module, whose own README
  records an earlier session's real `terraform init`+`validate` pass
  against the DigitalOcean provider schema — this environment could not
  reconfirm the equivalent for AWS. Run `terraform init && terraform
  validate` yourself before trusting the AWS module further.
- `kubectl apply --dry-run` against a live API server — no Kubernetes
  cluster (local or real) was reachable in this environment (`kubectl
  config get-contexts` returns none), so only structural YAML validity
  was checked, not schema/API-group validation a real dry-run would
  catch (e.g. a typo'd `apiVersion`, an invalid field name for the
  actual resource kind).
- Everything AWS-account-specific — the actual `terraform apply`, EKS
  cluster creation, RDS/ElastiCache provisioning, S3 bucket/ECR
  repository creation, and the full `kubectl apply` sequence against a
  real cluster. None of this is possible without real AWS credentials,
  which this environment does not have and was not asked to obtain.

7. Post-deploy verification checklist

Once a real deploy exists, confirm:

- `kubectl get pods -n vistaar` — `vistaar-backend` (2+ replicas),
  `vistaar-celery-worker` (1), `vistaar-prometheus`, `vistaar-grafana` all
  `Running`.
- `curl https://<real-domain>/health` → `200 {"status":"OK"}`.
- `curl https://<real-domain>/health/db`, `/health/redis`, `/health/kafka`
  → all `200`, confirming the app can reach every real managed service
  (RDS/ElastiCache/the Kafka EC2 instance), not just that its own
  process started.
- `kubectl logs -n vistaar deployment/vistaar-backend` shows no repeated
  Kafka-connection-retry loop (that log pattern is expected and benign
  only when Kafka is genuinely unreachable, as verified locally in §6 —
  in a real deploy it should connect once and stop retrying).
- Prometheus is scraping (`/metrics` returns real data, per
  `monitoring-configmap.yaml`'s scrape config) and Grafana's datasource
  resolves.
- Alertmanager is running and Prometheus's own `/targets` page shows it
  as a healthy alertmanager target (added 2026-09-03 —
  `alertmanager-deployment.yaml` + the `vistaar-prometheus-rules`
  ConfigMap in `monitoring-configmap.yaml`). Confirm
  `alertmanager-secret.yaml` was filled in with a real notification
  webhook, not left as the example template's placeholder — otherwise
  alerts fire but reach no one, silently.
- A real end-to-end smoke test: request OTP → verify → book a ride, using
  the mobile app or a direct API call against the real domain — nothing
  in this checklist so far proves the *application* works against real
  managed Postgres/Redis/Kafka, only that the process is up.

8. Rollback procedure

Standard Kubernetes rollback mechanics — provider-agnostic, unaffected
by the AWS switch.

8.1 **Application-only rollback** (no schema change involved in the bad
deploy):

```bash
kubectl rollout undo deployment/vistaar-backend -n vistaar
kubectl rollout status deployment/vistaar-backend -n vistaar --timeout=180s
kubectl rollout undo deployment/vistaar-celery-worker -n vistaar
kubectl rollout status deployment/vistaar-celery-worker -n vistaar --timeout=180s
```

This reverts both Deployments to their previous ReplicaSet/image. Safe
whenever the bad deploy did **not** include a new Alembic migration.

8.2 **A migration was part of the bad deploy — rollback is not automatic**

This is the case the workflow's own "no rollback step" gap (§4) matters
most for. `backend-migrate-job.yaml` only ever runs `alembic upgrade
head` — there is no corresponding downgrade Job anywhere in
`infrastructure/kubernetes/`, and rolling back the *application*
Deployment (§8.1) does **not** roll back the *database schema* — the
previous application code would now be running against a newer schema
than it expects, which is very likely worse than the original bug, not a
fix.

Two real options — an operator decision at incident time, not a default
this runbook picks:

- **Forward-fix**: write and apply a new migration that corrects the
  problem, keep the new application code running. Usually safer than a
  schema downgrade for anything that isn't purely additive.
- **Schema downgrade**: `infrastructure/kubernetes/
  backend-migrate-downgrade-job.yaml` (added 2026-09-03, mirroring
  `backend-migrate-job.yaml`'s pattern) runs `alembic downgrade
  <revision>` the same way. Only safe if the migration being reverted
  has a real, tested `downgrade()` and no data was written in a shape
  the older schema can't represent — that file's own header comment
  repeats this check.

  **Verified for real, 2026-09-03, not just reviewed by reading**: every
  one of the 37 migrations under `apps/backend/migrations/versions/` was
  actually run in both directions against a real disposable
  `postgis/postgis:16-3.4` container (not the shared dev database) —
  `alembic upgrade head` from empty, then `alembic downgrade base`
  (exercising every `downgrade()` in the chain), then `alembic upgrade
  head` again, landing back at the correct head revision with no errors
  anywhere in either direction. Additionally, the two most recent
  migrations (`d4e8f1a52c6b`, `f2a9c6e18b3d` — ADR-0058/ADR-0062's wallet
  columns) were downgraded a second time **with a real row present**
  (a seeded wallet with `outstanding_debt = 30.00`), specifically because
  the full-chain run above only exercised empty tables and a downgrade
  that drops a populated column can behave differently than one that
  drops an empty one — both columns dropped cleanly, the row survived
  with its other columns intact, confirming the schema round-trip
  genuinely works with data present, not just against an empty database.
  This does not by itself make every future migration safe to downgrade
  — each new migration still needs the same check at the time it's
  written — but it does confirm the *mechanism* itself (Alembic's chain,
  this repo's `downgrade()` implementations to date) actually works,
  closing a gap that was previously untested in either direction.

**Neither path is safe to run without first confirming what the bad
migration actually changed** — read the specific migration file under
`apps/backend/migrations/versions/` before choosing.

9. Backup / restore

9.1 **Database.** RDS PostgreSQL includes automatic daily backups
(configurable retention, `aws_db_instance.postgres`'s
`backup_retention_period = 7` in `infrastructure/terraform/aws/rds.tf`)
as a real Terraform-managed setting, not an assumed platform default the
way the superseded DigitalOcean plan had to rely on. **Still not
verified against a real provisioned instance in this environment** — no
account exists here to confirm the restore UX for real; confirm in the
AWS Console/CLI the first time a real instance exists.

RDS's documented restore mechanism (point-in-time recovery, or restoring
from a specific automated/manual snapshot) is also **fork-based**, not
in-place — same shape as the superseded DigitalOcean mechanism: restoring
creates a *new* DB instance, rather than overwriting the existing one.
Restoring therefore also requires updating `DATABASE_URL` in
`backend-secret.yaml` to point at the new instance's endpoint and
re-applying it. **Verify this exact mechanism against the real AWS
Console/CLI before relying on it during an actual incident** — this
runbook describes RDS's documented general behavior, not a tested one.

9.2 **Object storage (S3).** S3 versioning is enabled
(`aws_s3_bucket_versioning` in `infrastructure/terraform/aws/s3.tf`) —
a real improvement over the superseded Spaces bucket, which had no
backup/versioning story at all — but evidence uploads (GPS disputes,
driver documents) still have no separate cross-region replication or
lifecycle backup policy configured. Flagged as open, not assumed fully
safe just because versioning exists.

9.3 **Redis.** security.md §83 already establishes Redis is never the
source of truth for anything financial (wallet/payment/ride
state/ledger) — a Redis (ElastiCache) data loss degrades matching/
rate-limiting behavior temporarily but loses no authoritative data. No
backup is needed for it by design, not an oversight.

9.4 **Restore drills.** None have been run — cannot be, without a real
provisioned instance. This section documents the *procedure*; actually
rehearsing it (security.md §79's "tested for restoration") is real work
that remains open until a real environment exists.

10. Cross-references

- Backend production readiness overall: the "what else is needed"
  conversation this runbook is part of,
  `docs/08-security/security-review-2026-09-02.md` and
  `docs/08-security/security-review-pass-2-2026-09-03.md` for the
  security angle, and `docs/10-testing/e2e-findings-2026-09-02.md` for
  real journey-level test results (§7's own "real end-to-end smoke
  test" line above is what that document actually verified, at the API
  layer, against local Postgres/Redis — not yet against a real
  deployment).
- `docs/14-decisions/ADR-0063-aws-deployment-baseline.md` for the full
  account of the DigitalOcean → AWS switch and what changed vs. what
  stayed the same.
- Mobile app store submission (a separate, not-yet-started piece of
  "getting VISTAAR in front of real users") is out of this runbook's
  scope — it covers backend/infrastructure deployment only.
- `docs/10-testing/load-testing-plan-2026-09-03.md` for the
  100,000-concurrent-user load-testing plan — a plan only, blocked on
  the same AWS access this runbook is blocked on; §3 of that document
  reads today's HPA/node-group/RDS/ElastiCache defaults directly from
  this repo's Terraform/Kubernetes config as the starting point for what
  a real benchmark would need to scale past.
