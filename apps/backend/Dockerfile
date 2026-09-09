# syntax=docker/dockerfile:1
#
# Production image for the VISTAAR backend (Phase 21 / ADR-0035).
#
# This project ships a flat `src/` layout (main.py, core/, modules/,
# shared/) with no `[build-system]`/packages table in pyproject.toml —
# the same convention pytest (`pythonpath = ["src"]`) and Alembic
# (`prepend_sys_path = src` in alembic.ini) already rely on. Earlier
# revisions of this Dockerfile instead ran `pip install .`, which let
# setuptools' auto-discovery silently flatten `src/` into site-packages
# and installed the app as a distributable wheel alongside a *second*,
# separately-copied raw `src/` tree — two divergent copies of the same
# code, one of which (site-packages) was missing `httpx`, a runtime
# dependency of modules/identity/sms.py that had only ever been
# declared under the dev dependency group. Verified via `docker run`
# that this crashed the container at import time with
# `ModuleNotFoundError: No module named 'httpx'` before ever serving a
# request. This revision installs only the declared runtime
# dependencies (via `uv pip install -r pyproject.toml`, which reads
# `[project.dependencies]` without building/installing the project
# itself) and puts the single `src/` tree on PYTHONPATH, matching how
# the rest of the codebase already runs it — no second copy, no
# fragile auto-discovery.

FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install uv (already used by CI — see .github/workflows/ci.yml) to
# resolve and install runtime dependencies into an isolated venv.
RUN pip install --no-cache-dir uv==0.9.*

# uv.lock (security review pass 2, 2026-09-03 — security.md §73/§74's
# "pin important dependency versions") — every pyproject.toml dependency
# was declared with an unbounded `>=` floor and no lockfile existed
# anywhere in this repo, so every build (this image AND CI) re-resolved
# "whatever is newest and compatible" at build time: not reproducible
# build-to-build, and a newly-published compromised package version
# would be pulled in automatically with no review. `--frozen` below
# means this build fails loudly if uv.lock and pyproject.toml have
# drifted, rather than silently re-resolving — regenerate uv.lock
# (`uv lock`) and commit it whenever pyproject.toml's dependencies
# change.
COPY pyproject.toml uv.lock ./

# Install only [project.dependencies] (production deps) into a venv —
# not the dev group, and not the project itself as a package. `uv sync`
# (not `uv pip install -r pyproject.toml`, the old command) is uv's
# lockfile-aware interface — `uv pip install` ignores uv.lock entirely
# even when one exists, which would have made committing it pure
# security theater. UV_PROJECT_ENVIRONMENT points uv at /opt/venv
# directly, rather than its own default `.venv` — venv scripts embed an
# absolute shebang path back to their own interpreter, so creating it
# at the default location and `mv`-ing the directory afterward breaks
# every entry point in it (confirmed by direct reproduction: `exec
# uvicorn: no such file or directory` at container start).
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN uv sync --frozen --no-dev --no-install-project --python 3.12


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Non-root runtime user (the original image ran as root).
RUN groupadd --system vistaar && useradd --system --gid vistaar --create-home vistaar

COPY --from=builder /opt/venv /opt/venv

# Application code, plus the pieces needed to run migrations
# (alembic.ini + migrations/) from this same image via a Kubernetes
# Job/initContainer ahead of the rolling deploy — see
# infrastructure/kubernetes/backend-migrate-job.yaml.
COPY README.md ./
COPY alembic.ini ./
COPY migrations/ ./migrations/
COPY src/ ./src/

RUN chown -R vistaar:vistaar /app
USER vistaar

EXPOSE 8000

# python -c avoids depending on curl/wget, which python:3.12-slim
# does not ship.
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
