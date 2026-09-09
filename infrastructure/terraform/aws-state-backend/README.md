# AWS Terraform State Backend (Bootstrap Module)

Provisions the S3 bucket + DynamoDB lock table that `../aws/`'s own
remote state backend (`versions.tf`'s `backend "s3" {}` block) needs.
Closes deployment-runbook.md §5.3's previously-open gap: "local state
only exists today — fine for a first `plan`, not for more than one
operator ever running `apply`."

> [!IMPORTANT]
> Same honesty note as `../aws/README.md`: written and reviewed, not
> run — no `terraform` CLI in this environment, no AWS account to apply
> against. Run `terraform init && terraform validate` yourself before
> trusting this further.

## Why a separate module

A Terraform remote-state backend cannot bootstrap its own storage —
something has to create the S3 bucket and DynamoDB table *before*
`../aws/` can point its own state at them, and that something's state
has nowhere remote to live yet. This is the standard, documented
solution to that chicken-and-egg problem: a small bootstrap module that
keeps its own state locally (or moved somewhere durable by hand — a
private ops repo, not this one), applied once, rarely touched again
after.

## Usage

```bash
cd infrastructure/terraform/aws-state-backend
export AWS_ACCESS_KEY_ID=REPLACE_ME
export AWS_SECRET_ACCESS_KEY=REPLACE_ME
terraform init
terraform plan   # read the computed bucket name here before applying —
                  # vistaar-terraform-state-<your account id>-ap-south-1
terraform validate
terraform apply

# Then wire ../aws/ to use it:
terraform output backend_config_snippet
# copy the output into ../aws/backend.hcl (from backend.hcl.example)
cd ../aws
terraform init -backend-config=backend.hcl
```

The bucket name is not a manual input — owner decision, 2026-09-03:
"Use an account-specific bucket naming convention:
`vistaar-terraform-state-<AWS_ACCOUNT_ID>-ap-south-1`. Do not assume
availability of a generic bucket name." `main.tf` computes this
directly from the currently-authenticated account
(`data.aws_caller_identity.current.account_id`), so it can never drift
from whichever account you're actually applying against. S3 bucket
names are still globally unique across *every* AWS account, not just
this one, so a collision remains theoretically possible even with the
account ID embedded — "verify before creating it" means reading the
computed name in `terraform plan`'s output before `apply`, and
optionally `aws s3api head-bucket --bucket <name>` first to confirm
directly.

If `../aws/` was already applied once with local state before this
module existed, `terraform init -backend-config=backend.hcl` will offer
to migrate that existing local state into the new S3 backend
automatically — say yes; do not manually recreate resources.

## What this does NOT do

- Does not apply `../aws/` itself — this module only provisions the
  place its state lives.
- Does not configure state locking beyond the DynamoDB table itself —
  Terraform's S3 backend handles the lock/unlock protocol automatically
  once `dynamodb_table` is set; no further configuration needed.
- Does not enable cross-region replication or a lifecycle policy on the
  state bucket — versioning (enabled here) already protects against
  accidental state corruption/overwrite; a full DR story for the state
  bucket itself was judged out of scope for a first pass.
