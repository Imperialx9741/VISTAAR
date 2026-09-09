ADR-0053 — Monitoring: Sentry + Prometheus + Grafana

Status: Accepted and implemented (2026-08-28) — owner decision
("Monitoring → Sentry + Prometheus + Grafana"), resolving security.md
§89's "Exact backup retention"-adjacent open item and the roadmap's own
standing "Never claim production readiness without... monitoring active"
gate (Phase 20/21).

Date recorded: 2026-08-28.
Deciders: Project owner (explicit written decision, 2026-08-28).

1. Context

No monitoring/observability code existed anywhere in this codebase
before this ADR — `security.md`'s production-readiness checklist names
"monitoring active" as a hard gate, and the roadmap's Phase 21 entry
already flagged this as unbuilt. The owner named all three tools
explicitly, so no provider survey was needed (unlike, e.g., the payment
gateway or WhatsApp BSP, which remain genuinely open).

2. Decision 1 — Sentry (application error tracking)

`sentry-sdk[fastapi]` added as a dependency, initialized once at
`main.py`'s module level (before the FastAPI app is constructed, so it
can capture startup-time errors too) via `sentry_sdk.init(dsn=settings.
SENTRY_DSN, ...)`. `SENTRY_DSN` defaults to an empty string —
`sentry_sdk.init()` treats an empty/missing DSN as "disabled" natively
(the SDK's own documented no-op behavior, not custom code this codebase
had to write), the same "wired, real credential arrives later" pattern
every other provider integration in this codebase already follows.
`traces_sample_rate`/`profiles_sample_rate` are set low (0.1) by
default — full tracing on every request is a cost/volume decision for
whoever holds the real Sentry account, not this ADR's to make blindly.

3. Decision 2 — Prometheus (metrics exposition)

`prometheus-fastapi-instrumentator` added as a dependency, wired onto
the FastAPI app to expose `GET /metrics` — standard HTTP request
metrics (latency histograms, request count, status code, path) with
zero configuration needed and zero external credential ever required
(Prometheus scrapes a plain HTTP endpoint; nothing to authenticate).
This is real and fully functional immediately, unlike Sentry/Grafana
which need a real account/instance to be useful — `/metrics` returns
real data from the moment the app starts.

4. Decision 3 — Grafana (dashboards)

Self-hosted, not a managed Grafana Cloud account (the owner named
"Prometheus + Grafana" together, the standard self-hosted pairing,
matching this codebase's existing self-hosted-over-managed pattern for
Kafka, ADR-0017/ADR-0035). Added to `docker-compose.dev.yml` for local
development (a real, immediately runnable `prometheus` + `grafana`
service pair scraping the dev backend's `/metrics`, with one starter
dashboard auto-provisioned) and to `infrastructure/kubernetes/` as
plain Deployment/Service manifests for production — written and
syntax-validated (`kubeconform` against the real Kubernetes schemas,
matching ADR-0035's own verification method for every other manifest),
not applied — no live cluster exists in this environment, the same
already-disclosed Phase 21 gap.

5. What this does NOT resolve

- A real Sentry account/DSN, or a real production Grafana/Prometheus
  deployment — `SENTRY_DSN` stays empty and the Kubernetes manifests
  stay unapplied until a live account/cluster exists.
- Alerting rules/thresholds (Prometheus Alertmanager, Grafana alert
  rules) — no source document specifies what should page whom; building
  alert rules with invented thresholds would be exactly the kind of
  unrequested business/operational decision this codebase avoids
  inventing.

  **Partially revisited 2026-09-03**, under the owner's explicit
  instruction to "continue backup/restore, rollback, monitoring and
  production-readiness work that does not require my external
  credentials." Alertmanager was deployed
  (`infrastructure/kubernetes/alertmanager-deployment.yaml`) with three
  starter rules (`infrastructure/kubernetes/monitoring-configmap.yaml`'s
  `vistaar-prometheus-rules`): backend scrape-target down, 5xx rate
  above 5%, p99 latency above 2s. These are conventional infra-health
  defaults (not a business/operational judgment call like a refund
  policy or fare threshold), and are scoped to metrics that already
  exist rather than a hypothetical SLO. They are explicitly **not** an
  owner-approved SLO/paging policy — thresholds, which alerts page vs.
  merely log, and the actual notification channel (§ this ADR's own
  gap above) remain open and should be revisited once real traffic
  data exists to calibrate against. See
  `docs/12-deployment/deployment-runbook.md` §5.10 and §6 for what was
  verified and what remains open.
- Log aggregation (a separate concern from error tracking/metrics — no
  source document names a log-aggregation tool, and the owner's decision
  named only these three).
