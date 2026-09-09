ADR-0063 — AWS Deployment Baseline (Supersedes ADR-0035's DigitalOcean Choice)

Status: Accepted — owner decision, explicit written instruction,
2026-09-03. Implemented the same day (config/script layer only — no
real cloud account access exists in this environment; nothing has been
applied).
Date recorded: 2026-09-03
Deciders: Project owner (explicit written instruction: "Update
deployment planning to AWS only. Do not use DigitalOcean.").

1. Decision

AWS is the deployment target, replacing DigitalOcean everywhere it was
the documented baseline (`technical-architecture.md` §64, ADR-0035):

- **EKS** (Elastic Kubernetes Service) instead of DOKS.
- **RDS PostgreSQL** (with PostGIS enabled) instead of DigitalOcean
  Managed PostgreSQL.
- **ElastiCache for Redis** instead of DigitalOcean Managed Redis
  (Valkey-compatible).
- **A self-hosted Kafka EC2 instance** instead of a self-hosted Kafka
  Droplet — same reasoning as ADR-0035 (no managed Kafka was used
  there either), see §3 below for why this stays true even though AWS,
  unlike DigitalOcean, does offer a genuinely managed option (MSK).
- **S3** instead of DigitalOcean Spaces — a real simplification, not
  just a swap: `shared/storage.py`'s `S3ObjectStorage` (ADR-0031) was
  always built directly against boto3's real S3 client; Spaces only
  ever needed the `STORAGE_ENDPOINT` override because it's a
  *third-party* S3-compatible store. On real AWS S3, that override is
  simply left blank.
- **ECR** instead of DigitalOcean Container Registry — resolves
  `deployment-runbook.md` §5.1's previously-open "container registry
  choice," which had never actually been decided or created under the
  DigitalOcean plan either.

`apps/backend/Dockerfile` and every file under
`infrastructure/kubernetes/` are **provider-agnostic** (plain
Kubernetes YAML, a plain multi-stage Docker build) and needed **no
changes** for this switch — only the Terraform layer (which provisions
the cloud resources those Kubernetes manifests assume already exist)
and the CI/CD deploy workflow are provider-specific.

2. Why this happened twice (AWS → DigitalOcean → AWS)

Worth recording plainly, since it's a real process lesson, not just a
decision: ADR-0035 documents the *first* switch — the owner originally
picked AWS, then switched to DigitalOcean specifically because
`technical-architecture.md` §64 already documented DOKS as the
baseline at that point, and the task flagged the contradiction back to
the owner rather than silently building against whichever choice came
first. This ADR is a second, later, and this time final (per the
owner's explicit "AWS only" instruction) reversal — the owner's own
call, not a re-litigation of ADR-0035's own reasoning. Every
DigitalOcean-specific reference this ADR corrects is corrected because
the owner said so directly, not because AWS is being silently assumed
better.

3. Kafka: self-hosted EC2, not AWS MSK

AWS, unlike DigitalOcean, has a genuinely managed Kafka product (MSK).
This ADR does not default to it, for the same reason ADR-0035 didn't
default to a hypothetical managed Kafka either: it's a real cost and
operational-complexity increase over a single EC2 instance, and neither
the owner's "AWS only" instruction nor any other input to this session
asked for MSK specifically. `infrastructure/terraform/aws/kafka.tf`
keeps the exact same self-hosted approach ADR-0035 chose — the same
`apache/kafka:3.7.0` KRaft-mode image, on a single EC2 instance instead
of a single Droplet — so replacing it with MSK later is a Terraform-only
change (swap the `aws_instance` resource for `aws_msk_cluster` and
point `KAFKA_BOOTSTRAP_SERVERS` at MSK's own bootstrap string), not an
application code change, exactly as ADR-0035 §6 already promised for
its own Droplet.

4. Real IaC, honestly unverified against AWS itself

`infrastructure/terraform/aws/` is real, complete Terraform — VPC (with
explicit public/private subnets across 2 AZs, a NAT Gateway, and route
tables; AWS has no single-resource VPC equivalent to DigitalOcean's,
so this is genuinely more Terraform surface than the superseded
module, not scope added for its own sake), EKS with its own IAM
role/node-group IAM role, RDS with PostGIS (via the same `postgresql`
provider `postgresql_extension` mechanism the DigitalOcean module
already used), ElastiCache with TLS in transit, a self-hosted Kafka EC2
instance, an encrypted/versioned/fully-private S3 bucket with a
bucket-scoped IAM user, and an ECR repository with image scanning
enabled.

**Honestly, not just structurally, unverified**: unlike the
superseded DigitalOcean module (whose own README records that an
earlier session ran `terraform init`/`terraform validate` against the
real `digitalocean` provider schema), this environment has no
`terraform` CLI installed at all — none was added for this pass either.
This module has been reviewed by reading only (HCL syntax, resource
references, the dependency graph between files) — see its own README's
own `[!IMPORTANT]` callout for the full accounting, and run
`terraform init && terraform validate` before trusting it further. No
AWS account credentials exist in this environment either way; nothing
has been, or could have been, applied.

5. The superseded DigitalOcean module is deprecated, not deleted

`infrastructure/terraform/digitalocean/` remains in the repository,
marked deprecated (a note added to its own README pointing here) —
kept for the historical record and in case of a future reversal, not
removed outright, since deleting real prior work is a bigger decision
than "stop using it going forward" and wasn't asked for.
`.github/workflows/deploy-do.yml` is similarly left in place but is no
longer the active deploy path — see `deployment-runbook.md`'s own
updated status for the new `deploy-aws.yml`.

6. Consequences

- `technical-architecture.md` §64's deployment diagram and
  implementation-status note are corrected to name AWS, with an
  explicit pointer back to this ADR (the same "don't leave a
  contradiction for the next reader" discipline ADR-0035 itself
  established after finding one).
- `deployment-runbook.md` is rewritten for AWS end to end — prerequisites,
  first-time setup sequence, rollback, backup/restore all change to
  their AWS-specific equivalents (`aws eks`/`kubectl` instead of
  `doctl`, RDS's fork-based restore instead of DigitalOcean's, etc.).
- A new `.github/workflows/deploy-aws.yml` replaces `deploy-do.yml` as
  the active (still `workflow_dispatch`-only, matching ADR-0035's own
  "controlled authorization" reasoning, unchanged) deploy path.
- Object storage's `STORAGE_ENDPOINT` should be left blank in the real
  Kubernetes Secret going forward (real AWS S3 needs no override) —
  `.env.example`'s own comment is updated to stop suggesting Spaces as
  an example third-party endpoint.
- Does not change any application code, business rule, or the P2P
  ride-fare model — this ADR is infrastructure-only.
