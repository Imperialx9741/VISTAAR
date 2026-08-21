# VISTAAR Testing Foundation

This directory houses the project-level verification structures and test suites.

## Testing Philosophy
VISTAAR follows a clean, decoupled testing strategy:
- **Unit and Local Integration Tests** reside alongside the code they test (e.g., inside the backend application directory).
- **Decoupled Workflows** and system-wide tests reside in this root-level `tests/` directory, split by their scope.
- Tests must be deterministic, clean, and not rely on hardcoded environment configurations.

## Test Categories

1. **Backend Unit/Integration Tests**
   - **Location**: [`apps/backend/tests/`](file:///c:/Users/kumar/Downloads/VISTAAR/apps/backend/tests/)
   - **Tool**: `pytest`
   - **Scope**: Focuses on backend API endpoints, models, handlers, and internal business logic.

2. **End-to-End (E2E) Tests**
   - **Location**: [`tests/e2e/`](file:///c:/Users/kumar/Downloads/VISTAAR/tests/e2e/)
   - **Scope**: Integration workflows simulating customer-driver matches, payment completions, and cross-system notifications. *Infrastructure will be added as these user flows are implemented.*

3. **Performance Tests**
   - **Location**: [`tests/performance/`](file:///c:/Users/kumar/Downloads/VISTAAR/tests/performance/)
   - **Scope**: Scalability, latency, API endpoint throughput, and load testing simulations. *Tooling will be configured in later development phases.*

4. **Security Tests**
   - **Location**: [`tests/security/`](file:///c:/Users/kumar/Downloads/VISTAAR/tests/security/)
   - **Scope**: Scans, input validation checks, SQL injection regression checks, RBAC verification, and encryption audits. *Tests will be built concurrently with security system implementations.*

## Running Backend Tests
To run the backend tests, navigate to the `apps/backend` directory, activate the virtual environment, and run:
```bash
pytest
```
Alternatively, from the project root, you can run:
```bash
python -m pytest apps/backend/tests
```
*(Ensure that the backend virtual environment is active first.)*
