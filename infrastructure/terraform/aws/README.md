# AWS Infrastructure (Terraform)

Provisions VISTAAR's deployment target per
[ADR-0063](../../../docs/14-decisions/ADR-0063-aws-deployment-baseline.md),
which supersedes ADR-0035's DigitalOcean choice at the owner's explicit
instruction (2026-09-03): EKS, RDS PostgreSQL (with PostGIS enabled),
ElastiCache for Redis, a self-hosted Kafka EC2 instance (see ADR-0063 §3
for why this isn't AWS MSK), an S3 bucket for object storage, and an ECR
repository for the backend image.

> [!IMPORTANT]
> Unlike the superseded `../digitalocean/` module (which an earlier
> session ran `terraform init`/`terraform validate` against the real
> provider schemas for), **this module has not been validated against
> the real `aws`/`postgresql` provider schemas at all** — this
> environment has no `terraform` CLI installed and none was added for
> this pass. What was actually done: reviewed by reading (HCL syntax,
> resource names/references, the dependency graph between files), plus
> an automated cross-check (every `aws_<type>.<name>` reference across
> all 807 lines matched an actual `resource` declaration, and every
> `var.<name>` reference matched an actual `variable` block — zero
> dangling references either way) — a genuine partial verification, but
> still not a substitute for `terraform validate` against the real
> provider schema (which also catches things this check can't: wrong
> argument names, invalid attribute types, provider-specific
> constraints). Run `terraform init && terraform validate` yourself
> before trusting this further. Every instance size/region/version here
> is a reasonable starting point, not an approved cost/capacity
> decision — review `variables.tf` and adjust before the first real
> `terraform apply`.

## Prerequisites

- An AWS account and credentials (access key or an assumable role) with
  permission to create VPC, EKS, RDS, ElastiCache, EC2, S3, ECR, and IAM
  resources — exported as `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` (or
  via an AWS CLI profile / `AWS_PROFILE`).
- Terraform >= 1.7.0.
- `TF_VAR_postgres_password` set to a real, randomly generated password
  — `postgres_password` has no default on purpose (see `variables.tf`).
- `var.kafka_ami_id` set to a real, current Ubuntu 22.04 LTS AMI id for
  the target region — also has no default on purpose (see
  `variables.tf`).
- A remote state backend — apply `../aws-state-backend/` once first (see
  its own README), then copy its `backend_config_snippet` output into
  `backend.hcl` (from `backend.hcl.example`) before `terraform init`
  here. Resolved 2026-09-03; the superseded DigitalOcean module never
  had this wired up.

## Usage

```bash
# One-time, before the first init here — see ../aws-state-backend/README.md
cd infrastructure/terraform/aws
cp backend.hcl.example backend.hcl   # fill in real values first

export AWS_ACCESS_KEY_ID=REPLACE_ME
export AWS_SECRET_ACCESS_KEY=REPLACE_ME
export TF_VAR_postgres_password=REPLACE_ME
export TF_VAR_kafka_ami_id=ami-REPLACE_ME
terraform init -backend-config=backend.hcl
terraform validate
terraform plan
terraform apply
```

## What this does NOT do

- Does not install the AWS Load Balancer Controller itself onto the
  cluster — a Helm chart install run once the cluster exists (same
  treatment cert-manager always had here, which — unlike the
  superseded DigitalOcean plan — isn't needed at all now: TLS is
  ACM-terminated at the ALB, not cert-manager/Let's Encrypt in-cluster).
  `eks.tf` in this module DOES provision the IAM role (IRSA) the
  controller needs — see `../../kubernetes/README.md`'s "Installing the
  AWS Load Balancer Controller" for the exact Helm install steps.
  Owner decision, 2026-09-03: AWS Load Balancer Controller, explicitly
  not community Ingress-NGINX.
- Does not apply any of `../../kubernetes/*.yaml` — run those with
  `kubectl` (or a rewritten `.github/workflows/deploy-do.yml`, since
  that workflow is still DigitalOcean-specific — see
  `deployment-runbook.md`'s own note) after this module's `apply`
  completes and `terraform output` values are copied into
  `backend-secret.yaml`.
- Does not set up IAM Roles for Service Accounts (IRSA) for S3 access —
  a real, more-secure alternative to the static IAM user/access key
  `s3.tf` provisions instead; see that file's own comment for why this
  starting point was chosen and what IRSA would additionally require.
- Does not itself provision the remote-state S3 bucket/lock table —
  that's `../aws-state-backend/`, a deliberately separate module (a
  backend can't bootstrap its own storage). See Prerequisites above.
- Does not provision AWS MSK (managed Kafka) — see `kafka.tf`'s own
  comment and ADR-0063 §3.

## Files

| File | Purpose |
| :--- | :--- |
| `versions.tf` | Provider requirements + `aws`/`postgresql` provider configuration + the (empty, filled via `-backend-config`) S3 remote-state backend block. |
| `backend.hcl.example` | **Template only.** Copy to `backend.hcl`, fill in real values from `../aws-state-backend/`'s output, do not commit the filled-in file. |
| `variables.tf` | Every tunable (region, instance types, versions) with reasonable defaults — `postgres_password`/`kafka_ami_id` deliberately have none. |
| `vpc.tf` | VPC, public/private subnets across 2 AZs, NAT Gateway, route tables — real Terraform surface DOKS didn't need (§ this file's own header comment). |
| `eks.tf` | The EKS cluster, its IAM role, the managed node group and its IAM role/policies, plus (added 2026-09-03) the OIDC identity provider and IRSA IAM role for the AWS Load Balancer Controller. |
| `iam-policy-aws-load-balancer-controller.json` | The official IAM policy `eks.tf` attaches to that role — fetched verbatim from the `kubernetes-sigs/aws-load-balancer-controller` project, not reconstructed from memory. |
| `rds.tf` | RDS PostgreSQL (+ PostGIS extension via the `postgresql` provider) and its own security group, scoped to EKS nodes only. |
| `elasticache.tf` | ElastiCache for Redis, TLS-in-transit enabled, scoped to EKS nodes only. |
| `kafka.tf` / `kafka-user-data.yaml.tpl` | The self-hosted Kafka EC2 instance and its boot-time Docker setup. |
| `s3.tf` | Object storage bucket (encrypted, versioned, fully private) + a bucket-scoped IAM user/access key. |
| `ecr.tf` | The backend container registry — resolves deployment-runbook.md §5.1's previously-open registry choice. |
| `outputs.tf` | Connection strings/keys to copy into `../../kubernetes/backend-secret.yaml`. |
