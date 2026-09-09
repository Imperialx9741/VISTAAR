ADR-0035 — DigitalOcean Kubernetes Deployment Baseline and Production
Dockerfile Fixes

Status: **Superseded 2026-09-03 by
[ADR-0063](ADR-0063-aws-deployment-baseline.md)** — the owner switched
the deployment target to AWS only, explicitly instructing "Do not use
DigitalOcean." Decision 1 (the cloud provider itself) and Decision 2
(Spaces object storage) below are no longer current; Decisions 3
(Dockerfile fixes) and 4 (config artifacts, not a live deployment)
remain accurate — the Dockerfile and Kubernetes manifests are
provider-agnostic and were unaffected by the switch. Kept for the
historical record, not deleted.
Date recorded: 2026-08-25.
Deciders: Project owner (cloud provider), via AskUserQuestion earlier in
this session — VISTAAR session, 2026-08-25. Everything else decided
under the owner's phase-level-autonomy grant; the items below were real
mandatory-stop conditions (roadmap §0.3), not guessed past.

1. Context

Starting Phase 21 (Deployment), this task asked the owner to choose a
cloud provider (AWS, GCP, or Azure were offered, with AWS recommended
because ADR-0031's object storage integration already targets an S3
API). The owner picked AWS at that point. Only while surveying existing
infrastructure files immediately afterward did this task find that
technical-architecture.md §64 already documents a specific baseline:

    DigitalOcean Kubernetes
    ├── API/BFF
    ├── Core services
    ├── Workers
    ├── Notification service
    └── Support/AI service

    Managed PostgreSQL
    Managed Redis
    Kafka

This directly contradicts the AWS choice this task had just steered the
owner into — a real process failure: the correct discipline (the same
one that caught the `ride.change_requests` schema miss earlier in this
session) is to search all relevant docs *before* asking a question with
options, not after. This task flagged the conflict immediately, before
writing any AWS-specific IaC, via a fresh AskUserQuestion: "Stick with
AWS" vs. "Switch to DigitalOcean Kubernetes, matching the document." The
owner chose to switch, explicitly overriding their own earlier AWS
pick: **DigitalOcean Kubernetes is the governing deployment target**,
correcting every "AWS chosen" reference written earlier in this
session's own roadmap docs (VISTAAR_IMPLEMENTATION_ROADMAP.md,
VISTAAR_AUTONOMOUS_EXECUTION_PLAN.md).

2. Decision 1 — DigitalOcean Kubernetes Service (DOKS), Managed
   PostgreSQL, Managed Redis, self-hosted Kafka

Matches technical-architecture.md §64 literally. DOKS hosts the single
backend deployment (this modular monolith serves API/BFF, core
services, and — per ADR-0034 — the Notification domain in-process;
there is no separate Workers or Support/AI service to deploy yet, since
neither the Background Worker Foundation nor the AI support service has
been approved as a real technology decision anywhere in this session —
§64's diagram names them as an eventual target architecture, not
something to scaffold now). DigitalOcean Managed PostgreSQL must be
provisioned with the PostGIS extension enabled (`ride.rides` requires
`GEOMETRY(Point, 4326)` columns per ADR-0010 Decision 4 /
database-design.md §9.1) — DigitalOcean's managed Postgres offering
supports enabling PostGIS as a database extension via `CREATE EXTENSION
postgis;`, which the Terraform module below runs as a
`postgresql_extension` resource once the cluster exists. Kafka has no
DigitalOcean-managed offering as of this ADR; §64 lists it without
"Managed" in front (unlike PostgreSQL and Redis), consistent with
self-hosting it — this task provisions a single-node DigitalOcean
Droplet running the same `apache/kafka:3.7.0` KRaft-mode image already
used in `infrastructure/docker/docker-compose.dev.yml`, not a new
technology choice, just the existing dev image moved onto a small
always-on host. A managed Kafka service (e.g. a third-party add-on) can
replace this later without changing application code, since the app
only ever talks to `KAFKA_BOOTSTRAP_SERVERS`.

3. Decision 2 — Object storage moves from AWS S3 to DigitalOcean Spaces,
   with zero application code changes

ADR-0031 built `shared/storage.py`'s `S3ObjectStorage` against boto3's
S3 client with a configurable `STORAGE_ENDPOINT` (blank in
`.env.example`, meaning "use AWS's real S3 endpoint"). DigitalOcean
Spaces is S3-API-compatible; pointing `STORAGE_ENDPOINT` at a Spaces
region endpoint (e.g. `https://blr1.digitaloceanspaces.com`) and
`STORAGE_REGION` at that region is the only change required — verified
by reading `S3ObjectStorage.__init__` again for this ADR, which passes
`endpoint_url=STORAGE_ENDPOINT or None` straight into
`boto3.client("s3", ...)`, exactly the seam boto3 documents for
S3-compatible third-party stores. No code in `apps/backend/src` changes
for this decision; only the Kubernetes Secret/ConfigMap values set in
Section 5 below change.

4. Decision 3 — Two real, pre-existing production-Dockerfile bugs found
   and fixed while building this deployment target

Neither bug is new to this session; both were caught only because
Phase 21 required actually building and running the image for the
first time (CI never builds or runs the Docker image — `ci.yml` has no
Docker step at all). Both were reproduced with a real `docker build` +
`docker run` before being fixed, and the fix was re-verified the same
way afterward (`/health` returned `200 {"status":"OK"}` and the image's
own `HEALTHCHECK` reported `healthy`):

   a. `httpx` is imported unconditionally at module load time by
      `modules/identity/sms.py` (the MSG91 SMS provider's HTTP calls,
      extended for Notification/SMS under ADR-0034) but was declared
      only under `[dependency-groups].dev` in `pyproject.toml`, never
      under `[project].dependencies`. A production install therefore
      never installs it. Reproduced: `docker run` on the pre-existing
      `Dockerfile` crashed at startup with `ModuleNotFoundError: No
      module named 'httpx'`, before the process ever bound a port.
      Fixed by moving the `httpx` dependency to `[project].dependencies`
      in `apps/backend/pyproject.toml`.

   b. The pre-existing `Dockerfile` ran `pip install .` and separately
      `COPY src/ ./src/`. With no `[build-system]`/packages table in
      `pyproject.toml`, `pip install .` triggers setuptools'
      auto-discovery, which silently flattens `src/` into
      `site-packages` (`main`, `core`, `modules`, `shared` install as
      top-level modules there) — confirmed with a real `pip install .`
      into a scratch venv and inspecting the resulting `site-packages`
      layout. `CMD ["uvicorn", "src.main:app", ...]` then resolved
      `src.main` from the *separately copied* raw `/app/src/main.py`
      (via Python's implicit namespace packages, since uvicorn adds the
      working directory to `sys.path`), while that file's own internal
      absolute imports (`from modules.admin.router import ...`)
      resolved against the *other*, pip-installed copy in
      site-packages — two divergent copies of the same code kept in
      sync only by accident of always being built from the same source
      in the same build. This is exactly the shape of bug (a) above
      hid inside: the site-packages copy was the one missing `httpx`.
      Fixed by no longer installing the project as a package at all —
      the rewritten `Dockerfile` installs only the declared
      dependencies (`uv pip install --python <venv> -r pyproject.toml`,
      which reads `[project.dependencies]` without building/installing
      the local project) and puts the single `src/` tree on
      `PYTHONPATH`, matching how the rest of the codebase already
      treats it (`pytest`'s own `pythonpath = ["src"]` and
      `alembic.ini`'s own `prepend_sys_path = src`). `CMD` changed from
      `uvicorn src.main:app` to `uvicorn main:app` accordingly.

5. Decision 4 — Kubernetes manifests and Terraform are hand-written
   config artifacts, not a live deployment

No DigitalOcean account credentials exist in this environment (same
"config/script authorship without live infrastructure" scope every
other Phase 21 candidate in the roadmap already assumed). The
Kubernetes manifests under `infrastructure/kubernetes/` and the
Terraform module under `infrastructure/terraform/digitalocean/` are
written and internally reviewed (manifest YAML structure,
Terraform HCL syntax, and the Docker image they reference) but have
never been applied against a real DOKS cluster — `terraform plan`/
`terraform apply` and `kubectl apply` both require a `DIGITALOCEAN_
TOKEN` this task does not have and was not asked to obtain. Anything
env-specific (the actual DOKS cluster name, Managed PostgreSQL
connection string, Spaces bucket name/keys, the real container
registry the CI/CD workflow pushes to) is left as a Terraform variable
or a Kubernetes Secret placeholder for the owner to fill in before the
first real `terraform apply`.

6. Consequences

- The AWS choice recorded verbally earlier in this session is
  superseded; every "AWS chosen, no live account yet" reference in
  `docs/VISTAAR_IMPLEMENTATION_ROADMAP.md` and
  `docs/VISTAAR_AUTONOMOUS_EXECUTION_PLAN.md` is corrected to name
  DigitalOcean Kubernetes instead, citing this ADR.
- `apps/backend/Dockerfile` and `apps/backend/pyproject.toml` change in
  this task (see Decision 3); `apps/backend/README.md`'s Docker
  Containerization Guide is updated to match the corrected `CMD` and
  multi-stage build.
- Future work needing a real Background Worker process or a
  Support/AI service (both named only as an eventual §64 diagram box,
  neither approved as a real technology decision) must get that
  approval before any Kubernetes Deployment for them is written — this
  ADR does not manufacture that approval.
- Kafka remains self-hosted (a single Droplet) under this decision;
  replacing it with a managed offering later is a Terraform-only change
  (swap the Droplet resource for whatever managed product is chosen),
  not an application code change.
