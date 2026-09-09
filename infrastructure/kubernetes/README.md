# Kubernetes Manifests

Deployment target for the VISTAAR backend, per technical-architecture.md
§64 and [ADR-0063](../../docs/14-decisions/ADR-0063-aws-deployment-baseline.md)
(superseding [ADR-0035](../../docs/14-decisions/ADR-0035-digitalocean-deployment-and-production-dockerfile.md)'s
DigitalOcean choice, 2026-09-03). **These manifests are themselves
provider-agnostic plain Kubernetes YAML — nothing in this directory
changed for the AWS switch.** Only the Terraform layer that provisions
what these manifests assume already exists is provider-specific; that
now lives in `infrastructure/terraform/aws/`.

> [!IMPORTANT]
> These manifests are written and reviewed but have never been applied
> against a real cluster — this task has no AWS account credentials.
> `REPLACE_ME_*` placeholders throughout must be filled in before any
> `kubectl apply`. Provision the cluster and managed services first via
> `infrastructure/terraform/aws/` — several placeholders here come
> straight from `terraform output`.

## Files

| File | Purpose |
| :--- | :--- |
| `namespace.yaml` | The `vistaar` namespace everything else lives in. |
| `backend-configmap.yaml` | Non-secret backend env vars. |
| `backend-secret.example.yaml` | **Template only.** Copy to `backend-secret.yaml`, fill in real values, apply directly — do not commit the filled-in file. |
| `backend-migrate-job.yaml` | One-shot `alembic upgrade head` Job — apply and wait for completion before rolling out a new `backend-deployment.yaml` image. |
| `backend-migrate-downgrade-job.yaml` | Manual incident-time rollback Job (added 2026-09-03) — `alembic downgrade <revision>`, not part of the normal deploy sequence. See deployment-runbook.md §8.2. |
| `backend-deployment.yaml` | The API Deployment (2 replicas, readiness/liveness against `/health`). |
| `backend-service.yaml` | ClusterIP Service in front of the Deployment. |
| `backend-hpa.yaml` | CPU-based autoscaler (2–6 replicas), needs the metrics-server add-on installed explicitly on EKS (unlike DOKS, which enabled it by default — see that file's own comment). |
| `backend-ingress.yaml` | Ingress — ALB-class, ACM-terminated TLS (owner decision, 2026-09-03: AWS Load Balancer Controller, not community Ingress-NGINX; no cert-manager needed). Needs the AWS Load Balancer Controller installed first (§ "Installing the AWS Load Balancer Controller" below) and a real domain + ACM certificate ARN filled in. |
| `kafka-external-service.yaml` | Points the in-cluster `kafka` DNS name at the self-hosted Kafka EC2 instance (see Terraform). |
| `celery-worker-deployment.yaml` | Background Worker Foundation (ADR-0039) — a single combined Celery worker+Beat process, same image as `backend-deployment.yaml`, different command. Deliberately `replicas: 1`. |
| `monitoring-configmap.yaml` | Monitoring (ADR-0053) — Prometheus scrape config + Grafana datasource/dashboard provisioning, plus alerting rules (added 2026-09-03 — `vistaar-prometheus-rules`: backend-down, high error rate, high p99 latency, scoped to the metrics that actually exist today), as ConfigMaps. |
| `prometheus-deployment.yaml` | Self-hosted Prometheus Deployment + ClusterIP Service. `emptyDir` data volume — swap for a real PVC before production use. |
| `grafana-deployment.yaml` | Self-hosted Grafana Deployment + ClusterIP Service, reading admin credentials from `grafana-secret.yaml`. Same `emptyDir` caveat as Prometheus. |
| `grafana-secret.example.yaml` | **Template only.** Copy to `grafana-secret.yaml`, fill in a real admin password, apply directly — do not commit the filled-in file. |
| `alertmanager-deployment.yaml` | Self-hosted Alertmanager (added 2026-09-03) — Deployment + ClusterIP Service, reads its whole config (including the notification webhook URL) from `alertmanager-secret.yaml`. |
| `alertmanager-secret.example.yaml` | **Template only.** Copy to `alertmanager-secret.yaml`, replace the placeholder receiver URL with a real Slack/PagerDuty/Opsgenie webhook, apply directly — do not commit the filled-in file. Until replaced, Alertmanager starts and evaluates alerts normally but notifies no one (see that file's own comment on why the placeholder must stay a syntactically valid URL). |

## Apply order

```bash
kubectl apply -f namespace.yaml
kubectl apply -f backend-configmap.yaml
kubectl apply -f backend-secret.yaml       # your filled-in copy, not the .example
kubectl apply -f kafka-external-service.yaml

# One-shot migration before every deploy — wait for it, then delete it
# (Job names are per-tag; a rerun with the same tag would collide).
kubectl apply -f backend-migrate-job.yaml
kubectl wait --for=condition=complete --timeout=120s \
  job/vistaar-backend-migrate-<tag> -n vistaar
kubectl delete job/vistaar-backend-migrate-<tag> -n vistaar

kubectl apply -f backend-deployment.yaml
kubectl apply -f backend-service.yaml
kubectl apply -f backend-hpa.yaml
kubectl apply -f backend-ingress.yaml      # only once the AWS Load Balancer Controller exists (see below)
kubectl apply -f celery-worker-deployment.yaml

# Monitoring (ADR-0053) — independent of the backend rollout above,
# apply in any order relative to it.
kubectl apply -f monitoring-configmap.yaml
kubectl apply -f grafana-secret.yaml       # your filled-in copy, not the .example
kubectl apply -f alertmanager-secret.yaml  # your filled-in copy, not the .example
kubectl apply -f prometheus-deployment.yaml
kubectl apply -f grafana-deployment.yaml
kubectl apply -f alertmanager-deployment.yaml
```

`.github/workflows/deploy-aws.yml` automates this sequence (image build/
push + manifest apply) once the repository has real `AWS_ROLE_TO_ASSUME`
and the other AWS secrets configured — see that workflow's own comments.
(`deploy-do.yml` also still exists but is deprecated — see its own
header.)

## Installing the AWS Load Balancer Controller

Required before `backend-ingress.yaml` can be applied — owner decision,
2026-09-03: AWS ALB + the AWS Load Balancer Controller, explicitly not
community Ingress-NGINX. Verified first that this cluster is standard
EKS (a classic managed node group, `infrastructure/terraform/aws/eks.tf`),
not EKS Auto Mode — Auto Mode bundles its own load-balancing management
and would make a separately-installed controller redundant; standard
EKS has no such built-in, so this install is required, not duplicated.

The controller software itself is a Helm chart, not something Terraform
applies (same treatment cert-manager always had here) — but the IAM
role it needs (IRSA, no static AWS credentials in the cluster) IS
Terraform-managed, in `eks.tf`, output as
`aws_load_balancer_controller_role_arn`.

```bash
# 1. Get the controller's IAM role ARN from Terraform.
terraform -chdir=../terraform/aws output aws_load_balancer_controller_role_arn

# 2. Create the ServiceAccount, annotated with that role ARN — IRSA's
#    mechanism for letting only this ServiceAccount assume the role.
kubectl create serviceaccount aws-load-balancer-controller -n kube-system
kubectl annotate serviceaccount aws-load-balancer-controller -n kube-system \
  eks.amazonaws.com/role-arn=REPLACE_ME_ROLE_ARN_FROM_STEP_1

# 3. Install the controller via its official Helm chart.
helm repo add eks https://aws.github.io/eks-charts
helm repo update
helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=<eks_cluster_name output> \
  --set serviceAccount.create=false \
  --set serviceAccount.name=aws-load-balancer-controller

# 4. Confirm it's running before applying backend-ingress.yaml.
kubectl get deployment -n kube-system aws-load-balancer-controller
```

Then request/validate an ACM certificate for the real domain
(`aws acm request-certificate --domain-name REPLACE_ME_DOMAIN
--validation-method DNS`) and fill both its ARN and the domain into
`backend-ingress.yaml` before applying it.

## Scope notes (ADR-0063, ADR-0039)

- The backend API and a Celery worker (ADR-0039 — approved 2026-08-26)
  are deployed here. §64's diagram also names a Support/AI service,
  which has not been approved as a real technology decision anywhere in
  this project yet — no Deployment for it is invented here.
- The Notification domain (ADR-0034) mostly runs in-process inside the
  backend Deployment (its Kafka consumer, ADR-0038, covers 4 event
  types there) — only its two *scheduled* jobs (promotion/document
  expiry warnings, ADR-0039) run in the separate Celery worker, since
  those need a scheduler, not an event to react to.
