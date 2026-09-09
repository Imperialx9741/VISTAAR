ADR-0068 — Admin Web Deployment: AWS Amplify (WEB_COMPUTE)

Status: Accepted and implemented (2026-09-03) — owner decision
("FINAL ANSWERS FOR QUESTIONS 11–15", item 13)
Date recorded: 2026-09-03
Deciders: Project owner (explicit written decision).
Resolves: deployment-runbook.md §5.2, previously an open "Admin Web's
deployment target" decision naming four candidate options.

1. Decision

1. Admin Web (`apps/admin-web`, Next.js) deploys to **AWS Amplify
   Hosting**.
2. Kept in its own Terraform module/state
   (`infrastructure/terraform/aws-admin-web/`), separate from the
   backend's EKS/RDS/ElastiCache/Kafka module — per the owner's
   explicit "keep separate" instruction. Admin Web's own deploy
   lifecycle never touches backend infrastructure state, or vice versa.
3. Before deploying, this task inspected `apps/admin-web` directly to
   answer the owner's own question ("verify whether it requires
   server-side runtime features. Do not force a static export merely
   to use S3/CloudFront"): it has 18 dynamically-segmented routes
   (`drivers/[driverId]`, `customers/[customerId]`, `rides/[rideId]`,
   and 15 more), each an async Server Component reading `params` at
   request time, none with `generateStaticParams`. A static export
   (`output: "export"`) cannot serve these at all — there is no server
   left at request time to resolve an arbitrary, build-time-unknown
   ID. Amplify's `platform = "WEB_COMPUTE"` (verified against the AWS
   SDK's own `Platform` enum, not assumed) runs the app's real Next.js
   server-rendering path.

2. What was built

- `infrastructure/terraform/aws-admin-web/main.tf`: `aws_amplify_app`
  (`platform = "WEB_COMPUTE"`, a monorepo-aware `build_spec` pointing
  at `apps/admin-web`, `NEXT_PUBLIC_API_BASE_URL` as the one
  environment variable the app actually reads — confirmed by grepping
  its source, not assumed) and `aws_amplify_branch` (auto-build on
  every push, once connected).
- No `repository`/`access_token` set on the Amplify app — the GitHub
  connection is a deliberate one-time Console step (AWS's current
  recommended GitHub-App-based flow, no long-lived personal-access
  token stored in Terraform state) — see that module's own README for
  the exact steps.
- `deployment-runbook.md` §5.2 updated to point here instead of naming
  four still-open candidate options.

3. What this ADR explicitly does not do

- Does not connect the real GitHub repository — a manual, one-time
  Console action, deliberately not automated (see §1.3 above).
- Does not configure a custom domain for the Admin Web app — Amplify's
  own auto-assigned `*.amplifyapp.com` URL works immediately; a real
  custom domain is a separate, later decision.
- Does not touch anything under `infrastructure/terraform/aws/` or
  `infrastructure/kubernetes/` — Admin Web's infrastructure is fully
  independent, per the owner's own instruction.

4. Verification

- Structural inspection of `apps/admin-web/src/app/` confirmed the
  dynamic-route/server-component count and the absence of
  `generateStaticParams`, `middleware.ts`, and API routes directly —
  not inferred from Next.js's general reputation.
- The `WEB_COMPUTE` platform value was verified against
  `aws-sdk-go-v2/service/amplify/types`' own `Platform` enum
  definition (`WEB`, `WEB_DYNAMIC`, `WEB_COMPUTE`), not reconstructed
  from memory.
- `terraform` is not available in this environment (same limitation
  every AWS Terraform ADR this session has carried) — reviewed by
  reading, plus the same automated dangling-reference cross-check used
  for every other module here (zero dangling `aws_<type>.<name>`/
  `var.<name>` references). The embedded `build_spec` YAML was
  extracted and parsed for real (`yaml.safe_load`), confirming it's
  syntactically valid, not just visually plausible.
