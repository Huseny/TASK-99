# CEMS — Collegiate Enrollment & Assessment Management System (fullstack)

A fullstack, Dockerised platform for enrollment, scoring, finance, governance, and offline messaging.  Everything runs inside Docker — no local Python or Node installation required to start the system or run tests.

---

## Quick Start

```sh
docker-compose up
```

Services:

| Service | URL | Description |
|---------|-----|-------------|
| API | http://localhost:8000 | FastAPI backend |
| Web | http://localhost:5173 | React + MUI frontend |
| DB | localhost:5432 | PostgreSQL 15 (internal) |

---

## Bootstrap Demo Credentials

The system starts with no users.  Create the first admin account with the bootstrap token (set in `docker-compose.yml`):

```sh
# Create the first admin
curl -s -X POST http://localhost:8000/api/v1/auth/bootstrap-admin \
  -H "Content-Type: application/json" \
  -H "X-Bootstrap-Token: integration-test-bootstrap-2026" \
  -d '{"username": "admin", "password": "AdminPassword1!"}' | jq .

# Log in and capture token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "AdminPassword1!"}' | jq -r '.token')

# Create a demo student
curl -s -X POST http://localhost:8000/api/v1/admin/users \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"username": "student1", "password": "StudentPassword1!", "role": "STUDENT", "is_active": true}' | jq .
```

| Role | Username | Password |
|------|----------|----------|
| Admin | admin | AdminPassword1! |
| Student | student1 | StudentPassword1! |
| Instructor | instructor1 | InstructorPass1! |
| Reviewer | reviewer1 | ReviewerPass1!! |
| Finance Clerk | finance1 | FinancePass1!!!! |

> **Note:** Only the Admin and Student accounts are created by the bootstrap snippet above.  Create the remaining demo users by repeating the `curl … /admin/users` command with the appropriate `role` and credentials.

---

## Web Verification Flow

After `docker-compose up` completes and the API is healthy:

1. Open **http://localhost:5173** in a browser — you should be automatically redirected to `/login`.
2. Enter the admin credentials (`admin` / `AdminPassword1!`) and click **Sign In**.
3. Confirm you land on `/app` and the AppShell header shows the admin username.
4. Click the **notifications bell** icon — the Notifications drawer opens; for a fresh instance it shows *"No notifications yet"*.
5. Click the **logout** icon — you are redirected back to `/login`.
6. Re-login as the student (`student1` / `StudentPassword1!`) — you should see **Student Workspace** in the main panel.
7. Verify the API is responding:

```sh
curl -s http://localhost:8000/api/v1/health/live | jq .
# → {"status":"ok","service":"api"}
```

---

## Verification

```sh
# Liveness probe
curl -s http://localhost:8000/api/v1/health/live | jq .
# → {"status":"ok","service":"api"}

# Readiness probe (confirms database connectivity)
curl -s http://localhost:8000/api/v1/health/ready | jq .
# → {"status":"ready"}

# List organizations (admin token required)
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "AdminPassword1!"}' | jq -r '.token')
curl -s http://localhost:8000/api/v1/admin/organizations \
  -H "Authorization: Bearer $TOKEN" | jq .
```

---

## Run Tests

```sh
./run_tests.sh
```

The script is the single entry point for the full test suite.  It:

1. Starts `db`, `api`, and `web` services if they are not already running (`docker compose up -d`)
2. Waits for the API to pass its health check
3. Runs **backend unit tests** inside the `api` container (`unit_tests/`)
4. Runs **backend API tests** inside the `api` container (`API_tests/`)
5. Runs **backend integration tests** inside the `api` container (`integration/`)
6. Runs **frontend unit tests** (Vitest) inside a disposable `frontend-test` container
7. Runs **frontend E2E tests** (Playwright + Chromium) inside the same disposable container

Everything runs inside Docker.  No local Python, Node, or browser installation is required.

---

## Architecture

```
┌──────────────────────────────────────────────┐
│  Browser  →  http://localhost:5173            │
│  React + MUI (Vite dev-server / nginx)        │
│  /api/*  proxied  →  http://localhost:8000    │
└───────────────────┬──────────────────────────┘
                    │ HTTP
┌───────────────────▼──────────────────────────┐
│  FastAPI  (uvicorn)  :8000                    │
│  Routers: auth · admin · registration ·       │
│           reviews · finance · messaging ·      │
│           data_quality · integrations          │
│  Alembic migrations run at startup            │
└───────────────────┬──────────────────────────┘
                    │ psycopg
┌───────────────────▼──────────────────────────┐
│  PostgreSQL 15  :5432  (cems/cems)            │
└──────────────────────────────────────────────┘
```

---

## Roles & Permissions

| Role | Capabilities |
|------|-------------|
| `ADMIN` | Full access to all routes; manage users, orgs, catalog, audit log, integrations |
| `INSTRUCTOR` | Scoped access to assigned sections; submit and view review scores |
| `REVIEWER` | Scoped access to review rounds; submit scores; view outlier report |
| `STUDENT` | Enroll in sections; view own enrollment status; receive notifications |
| `FINANCE_CLERK` | View and record payments; access finance dashboard |

Scope grants (`ORGANIZATION` or `SECTION`) restrict non-admin roles to their assigned resources.  Admin role bypasses all scope checks.

---

## Integration Clients (SIS / QBank)

Third-party systems authenticate with HMAC-SHA256 signed requests:

```sh
# Register an integration client (admin only)
curl -s -X POST http://localhost:8000/api/v1/integrations/clients \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name": "My SIS", "organization_id": 1, "rate_limit_rpm": 60}' | jq .
```

The response contains `client_id` and `client_secret`.  Subsequent requests must include `X-Client-ID`, `X-Signature-256`, `X-Nonce`, and `X-Timestamp` headers.

---

## Configuration

All settings have development-safe defaults in `docker-compose.yml`.  Override via environment variables or a `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+psycopg://cems:cems@db:5432/cems` | PostgreSQL connection string |
| `SECRET_KEY` | `dev-secret-key-…` | JWT signing key (≥ 24 chars; change in production) |
| `BOOTSTRAP_ADMIN_TOKEN` | `integration-test-bootstrap-2026` | One-time token for first-admin creation |
| `BCRYPT_ROUNDS` | `12` | Password hashing cost |
| `SESSION_IDLE_TIMEOUT` | `28800` | Session idle timeout in seconds (8 h) |
| `SESSION_ABSOLUTE_TIMEOUT` | `86400` | Absolute session lifetime in seconds (24 h) |
| `DEDUP_THRESHOLD` | `0.92` | Fuzzy-match threshold for course deduplication |
| `HMAC_TIMESTAMP_TOLERANCE` | `300` | Max clock skew for integration request signing (seconds) |

`SECRET_KEY` must be at least 24 characters and must not use the default value in shared or production environments.

---

## Notes

- Alembic migrations run automatically at API startup.
- Audit retention policy is 7 years with archive-then-purge; trigger via `POST /api/v1/admin/audit-log/retention`.
- The messaging poller dispatches queued notifications on a configurable interval (`MESSAGING_POLLER_INTERVAL_SECONDS`, default 30 s).
- Playwright browser binaries are pre-installed in the Docker image; all E2E tests run inside Docker without any manual install step.
