# VISTAAR Continuous Integration (CI) Documentation

This directory configures continuous integration workflows for the VISTAAR repository.

## Purpose of CI
The CI pipeline automatically verifies code quality, static formatting, typing, and test suites across all VISTAAR applications and services upon code integration. This ensures that:
- Code remains consistently formatted.
- Static type violations are caught early.
- Breaking modifications are flagged before merging.
- No deployment actions are triggered; the pipeline is strictly for verification.

## Triggering Rules
The CI workflow runs automatically on:
- All push events targeting the `main` or `development` branches.
- All pull requests targeting the `main` or `development` branches.

## CI Workflow Structure & Check Steps

### 1. Backend Checks
- **Target Location**: `apps/backend/`
- **Environment**: Python 3.12 (utilizing `setup-python` and the `astral-sh/setup-uv-action` tool).
- **Execution Steps**:
  1. Installs project requirements and development dependencies declared in the project's pyproject.toml `dev` dependency-group using `uv pip install --system -e . --group dev`.
  2. Runs Ruff format checks (`ruff format --check src tests`).
  3. Runs Ruff linter checks (`ruff check src tests`).
  4. Runs MyPy type checks (`mypy src tests`).
  5. Runs backend unit tests (`pytest`).

### 2. Customer Mobile Checks
- **Target Location**: `apps/customer-mobile/`
- **Environment**: Flutter stable.
- **Execution Steps**:
  1. Fetches Dart packages (`flutter pub get`).
  2. Runs code analyzer checks (`flutter analyze`).
  3. Runs unit/widget tests (`flutter test`).

### 3. Driver Mobile Checks
- **Target Location**: `apps/driver-mobile/`
- **Environment**: Flutter stable.
- **Execution Steps**:
  1. Fetches Dart packages (`flutter pub get`).
  2. Runs code analyzer checks (`flutter analyze`).
  3. Runs unit/widget tests (`flutter test`).

### 4. Admin Web Checks
- **Target Location**: `apps/admin-web/`
- **Environment**: Node.js v20.
- **Execution Steps**:
  1. Installs package dependencies (`npm ci`).
  2. Runs ESLint checks (`npm run lint`).
  3. Runs production Next.js build compilation (`npm run build`).
