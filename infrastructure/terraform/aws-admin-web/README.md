# Admin Web on AWS Amplify

Provisions the Amplify Hosting app for `apps/admin-web` (Next.js) —
owner decision, 2026-09-03: "Use AWS Amplify as the Admin Web
deployment target... Keep the Admin Web separate from the EKS backend
infrastructure." A deliberately separate Terraform module/state from
`../aws/`, same reasoning as `../aws-state-backend/` — Admin Web's own
deploy lifecycle has nothing to do with the backend's EKS/RDS/
ElastiCache/Kafka apply cycle.

> [!IMPORTANT]
> Same honesty note as every other module here: written and reviewed,
> not run — no `terraform` CLI in this environment, no AWS account to
> apply against. Run `terraform init && terraform validate` yourself
> before trusting this further.

## Why WEB_COMPUTE, not a static export

The owner's own instruction: "Before deployment, inspect the existing
Next.js application and verify whether it requires server-side runtime
features. Do not force a static export merely to use S3/CloudFront."
That inspection was done directly, not assumed:

- `apps/admin-web/src/app/` has 18 dynamically-segmented routes
  (`drivers/[driverId]`, `customers/[customerId]`, `rides/[rideId]`,
  and 15 more) — a real admin dashboard, one detail page per resource
  type.
- Every one of them is an async Server Component reading `params` at
  request time (Next.js 16's `params`-as-`Promise` pattern) — checked
  directly against `drivers/[driverId]/page.tsx`.
- None declares `generateStaticParams`. A static export
  (`output: "export"`) requires every dynamically-segmented route to
  either declare `generateStaticParams` (pre-rendering a known,
  fixed list of pages at build time) or fails to build at all — there
  is no server left at request time to resolve an arbitrary,
  build-time-unknown `driverId`. Forcing a static export here would
  mean either the build fails outright, or a real rearchitecture
  (converting every dynamic segment to client-side query-param
  routing) this task was explicitly told not to do.
- No `middleware.ts`, no API routes (`route.ts`) exist either — so this
  isn't a "needs everything" app, just specifically "needs dynamic
  server-side param resolution."

Amplify Hosting's `platform = "WEB_COMPUTE"` (verified directly against
the AWS SDK's own `Platform` enum — `WEB` is static-only, `WEB_DYNAMIC`
and `WEB_COMPUTE` both support server rendering; `WEB_COMPUTE` is what
Amplify's own framework detection assigns a Next.js SSR app) runs the
app's real Node.js server-rendering path via Amplify's managed compute,
not a static bucket.

## Usage

```bash
cd infrastructure/terraform/aws-admin-web
export AWS_ACCESS_KEY_ID=REPLACE_ME
export AWS_SECRET_ACCESS_KEY=REPLACE_ME
export TF_VAR_backend_api_base_url=https://REPLACE_ME_REAL_DOMAIN
terraform init
terraform validate
terraform plan
terraform apply
```

Then, once — connect the GitHub repository:

1. Open the Amplify Console for the app this creates (`terraform
   output amplify_app_id`, or find it by name in the Console).
2. "Connect branch" → authorize the GitHub App installation (AWS's
   current recommended flow — no long-lived personal-access-token
   stored anywhere, unlike this resource's own optional
   `repository`/`access_token` arguments, deliberately left unset here;
   see `main.tf`'s own comment for why).
3. Point it at this repo, branch `main` (or whatever `var.git_branch`
   was set to), monorepo root `apps/admin-web` — Amplify auto-detects
   this from the `build_spec` this module already sets.

Every push to that branch from then on triggers a real Amplify build
and deploy automatically (`enable_auto_build = true` on the
`aws_amplify_branch` resource) — no separate CI/CD pipeline needed for
Admin Web.

## What this does NOT do

- Does not connect the GitHub repository — a one-time Console step,
  deliberately not automated via a stored access token (see above).
- Does not configure a custom domain — Amplify assigns a real,
  immediately-usable `*.amplifyapp.com` URL
  (`terraform output amplify_default_domain`); a custom domain is a
  separate, later decision (Route 53 + `aws_amplify_domain_association`,
  not provisioned here).
- Does not touch `../aws/` or any EKS/Kubernetes resource — Admin Web's
  infrastructure is fully independent, per the owner's own "keep
  separate" instruction.
- Does not set any backend-facing secret — `NEXT_PUBLIC_API_BASE_URL`
  is the one environment variable `apps/admin-web` reads (confirmed by
  grepping its source for every `NEXT_PUBLIC_*`/`process.env` use —
  exactly one), and it's a public URL, not a credential.
