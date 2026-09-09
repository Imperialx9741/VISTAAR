ADR-0067 — EKS Ingress: AWS Load Balancer Controller (not Ingress-NGINX)

Status: Accepted and implemented (2026-09-03) — owner decision
("FINAL ANSWERS FOR QUESTIONS 11–15", item 11)
Date recorded: 2026-09-03
Deciders: Project owner (explicit written decision).
Resolves: deployment-runbook.md §5.6, previously an open "which ingress
controller for EKS" decision.

1. Decision

1. VISTAAR's backend Ingress on EKS uses the **AWS Load Balancer
   Controller** (ALB, `alb` ingress class) — not community
   Ingress-NGINX, which the owner explicitly ruled out for the new
   production deployment.
2. Before installing anything, this task verified whether the planned
   cluster uses standard EKS or EKS Auto Mode, per the owner's explicit
   instruction not to install a duplicate controller. **Confirmed:
   standard EKS** — `infrastructure/terraform/aws/eks.tf` provisions a
   classic `aws_eks_node_group` (a user-managed node group with its own
   IAM role/scaling config); EKS Auto Mode is a structurally different
   cluster configuration (a `compute_config { enabled = true }` block
   with no separate node-group resource at all, since Auto Mode manages
   compute automatically) and bundles its own load-balancing management
   as part of that. Since this module uses neither, there is nothing
   built-in to duplicate — installing the AWS Load Balancer Controller
   is required, not redundant. This finding is recorded directly in
   `eks.tf`'s own comment, not just this ADR.
3. TLS is **ACM-terminated at the ALB**, not cert-manager/Let's
   Encrypt in-cluster — the idiomatic pattern for an ALB Ingress
   (`alb.ingress.kubernetes.io/certificate-arn`), and simpler than
   running cert-manager for a certificate AWS already issues, attaches,
   and auto-renews. This removes a dependency the previous
   (DigitalOcean-era, ingress-nginx-based) `backend-ingress.yaml` still
   assumed — cert-manager is no longer needed anywhere in this stack.

2. What was built

- `infrastructure/terraform/aws/eks.tf`: an OIDC identity provider for
  the cluster's own issuer (`aws_iam_openid_connect_provider`, using
  `data "tls_certificate"` to fetch the real, current signing-CA
  thumbprint rather than hardcoding one that could go stale), and an
  IAM role scoped via IRSA to exactly the
  `kube-system:aws-load-balancer-controller` Kubernetes ServiceAccount
  — no static AWS credentials stored in the cluster for this.
- `infrastructure/terraform/aws/iam-policy-aws-load-balancer-controller.json`:
  the official IAM policy the controller needs, fetched verbatim from
  `kubernetes-sigs/aws-load-balancer-controller`'s own published
  `docs/install/iam_policy.json` — not reconstructed from memory. A
  large (14-statement), security-sensitive document; getting it
  byte-for-byte right mattered more than typing it out by hand.
- `infrastructure/kubernetes/backend-ingress.yaml`: rewritten from
  `kubernetes.io/ingress.class: nginx` + a cert-manager `ClusterIssuer`
  to `kubernetes.io/ingress.class: alb` with
  `alb.ingress.kubernetes.io/*` annotations (`target-type: ip` — routes
  directly to pod IPs via the VPC CNI, the recommended EKS mode;
  `certificate-arn`; HTTP→HTTPS redirect; a `/health` health check
  path). The `ClusterIssuer` resource is removed entirely.
- `infrastructure/kubernetes/README.md`: a new "Installing the AWS
  Load Balancer Controller" section with the real `kubectl`/`helm`
  commands — the controller software itself is a Helm chart install,
  same "not Terraform-applied" treatment cert-manager always had here,
  now pointed at the IAM role Terraform provisions instead.
- `deployment-runbook.md` §2/§5.5/§5.6 updated to match.

3. What this ADR explicitly does not do

- Does not switch the cluster to EKS Auto Mode — that would be a
  larger, materially different infrastructure decision the owner did
  not ask for; this ADR only verifies which mode is already in use
  (standard EKS) and proceeds accordingly.
- Does not install the AWS Load Balancer Controller software itself —
  that happens once a real cluster exists to `helm install` onto; this
  environment has none.
- Does not request or validate a real ACM certificate, or decide the
  real domain name — both remain the owner's own AWS-Console-side
  actions; `backend-ingress.yaml` keeps `REPLACE_ME_DOMAIN`/
  `REPLACE_ME_ACM_CERTIFICATE_ARN` as explicit placeholders.
- Does not attach a WAF WebACL to the ALB — the IAM policy includes the
  `wafv2:*`/`waf-regional:*` permissions the controller needs *if* one
  is ever attached (`alb.ingress.kubernetes.io/wafv2-acl-arn`), but
  none is configured here; edge-level rate limiting (ADR-0061's own
  still-open "second, coarser layer") remains a separate, undecided
  follow-up.

4. Verification

- The real, current IAM policy document was fetched directly from the
  upstream project (not paraphrased) and saved verbatim.
- `terraform` is not available in this environment (unchanged
  limitation, every AWS Terraform ADR this session has carried the same
  caveat) — the new resources were reviewed by reading, plus the same
  automated dangling-reference cross-check used for the rest of this
  module (every `aws_<type>.<name>`/`var.<name>` reference resolves to
  a real declaration).
- `backend-ingress.yaml` was validated as structurally correct YAML
  (`yaml.safe_load_all`).
