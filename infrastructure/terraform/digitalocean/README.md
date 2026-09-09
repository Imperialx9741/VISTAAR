# DigitalOcean Infrastructure (Terraform) — DEPRECATED

> [!WARNING]
> **Superseded 2026-09-03 by
> [ADR-0063](../../../docs/14-decisions/ADR-0063-aws-deployment-baseline.md)
> — the owner switched the deployment target to AWS only, explicitly
> instructing "Do not use DigitalOcean."** This module is kept for the
> historical record, not deleted, but is no longer the active plan —
> use [`../aws/`](../aws/) instead. Do not run `terraform apply`
> against this module.

Provisioned the deployment target originally named in
technical-architecture.md §64 and [ADR-0035](../../../docs/14-decisions/ADR-0035-digitalocean-deployment-and-production-dockerfile.md):
DOKS, Managed PostgreSQL (with PostGIS enabled), Managed Redis, a
self-hosted Kafka Droplet (no DigitalOcean-managed Kafka product
exists), and a Spaces bucket for object storage.

> [!IMPORTANT]
> This has been syntax-validated (`terraform init` against the real
> `digitalocean` and `cyrilgdn/postgresql` provider schemas, then
> `terraform validate` — both pass) but **never applied**. This task has
> no `DIGITALOCEAN_TOKEN` and was not asked to obtain one. Every
> resource name, size slug, and region here is a reasonable starting
> point, not an approved cost/capacity decision — review `variables.tf`
> and adjust before the first real `terraform apply`.

## Prerequisites

- A DigitalOcean account and a Personal Access Token with read/write
  scope, exported as `DIGITALOCEAN_TOKEN`.
- Terraform >= 1.7.0.
- A remote state backend (an DigitalOcean Spaces bucket configured as
  an S3-compatible backend is the natural choice, but none is wired up
  here — local state is fine for a first `plan`, not for real use with
  more than one operator).

## Usage

```bash
cd infrastructure/terraform/digitalocean
export DIGITALOCEAN_TOKEN=REPLACE_ME
terraform init
terraform plan
terraform apply
```

## What this does NOT do

- Does not install `ingress-nginx` or `cert-manager` onto the cluster —
  both are usually a Helm chart install run once the cluster exists
  (`../../kubernetes/backend-ingress.yaml` expects both to already be
  present).
- Does not apply any of `../../kubernetes/*.yaml` — run those with
  `kubectl` (or via `.github/workflows/deploy-do.yml`) after this
  module's `apply` completes and `terraform output` values are copied
  into `backend-secret.yaml`.
- Does not set up a container registry — DigitalOcean Container
  Registry (`doctl registry create`) or any other registry the CI/CD
  workflow's `REPLACE_ME_REGISTRY` should point at is a one-time manual
  step outside Terraform's scope here.
- Does not provision a remote Terraform state backend — see
  Prerequisites above.

## Files

| File | Purpose |
| :--- | :--- |
| `versions.tf` | Provider requirements + `digitalocean`/`postgresql` provider configuration. |
| `variables.tf` | Every tunable (region, sizes, versions) with reasonable defaults. |
| `vpc.tf` | Shared private network. |
| `doks.tf` | The Kubernetes cluster + autoscaling node pool. |
| `database.tf` | Managed PostgreSQL (+ PostGIS extension via the `postgresql` provider) and Managed Redis, both firewalled to the DOKS cluster only. |
| `spaces.tf` | Object storage bucket + a bucket-scoped access key (ADR-0035 Decision 2). |
| `kafka.tf` / `kafka-cloud-init.yaml.tpl` | The self-hosted Kafka Droplet and its boot-time Docker setup. |
| `outputs.tf` | Connection strings/keys to copy into `../../kubernetes/backend-secret.yaml`. |
