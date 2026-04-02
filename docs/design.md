# design.md — Collegiate Enrollment & Assessment Management System (CEAMS)

## 1. Overview

CEAMS is a single-tenant, air-gapped backend service for managing the full academic lifecycle at a university or training provider. It covers:

- **Enrollment**: course registration, add/drop, waitlist, prerequisites, capacity enforcement
- **Assessment**: multi-round review/scoring workflows with assignment, blind modes, outlier flags, and recheck
- **Finance**: internal ledger for prepayment, deposit, and month-end billing; reconciliation; late fees
- **Governance**: RBAC, immutable audit log, org/term/course/section management, integration controls

The system is delivered as a single Docker-deployable Python/FastAPI service backed by PostgreSQL. There is no external dependency (no email, no SMS, no third-party login).

---

## 2. Architecture

### 2.1 Deployment Model

```
┌──────────────────────────────────────────────────────┐
│  Docker Compose                                       │
│                                                       │
│  ┌────────────────────┐   ┌────────────────────────┐ │
│  │  api  (FastAPI)    │──▶│  db  (PostgreSQL 15)   │ │
│  │  port 8000         │   │  port 5432 (internal)  │ │
│  └────────────────────┘   └────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

- `api` container: Python 3.11, FastAPI, Uvicorn, SQLAlchemy (async), Alembic
- `db` container: PostgreSQL 15 with a named volume for persistence
- No reverse proxy required in the base deployment; operators may add one externally
- Environment variables injected via `.env.example` → `.env` (never committed)

### 2.2 Layered Architecture

```
┌──────────────────────────────────────┐
│  API Layer      (routers/)           │  FastAPI routers — request parsing, auth middleware, response shaping
├──────────────────────────────────────┤
│  Service Layer  (services/)          │  Business logic, workflow orchestration, rule enforcement
├──────────────────────────────────────┤
│  Repository Layer (repositories/)    │  SQLAlchemy queries, unit-of-work, transactional helpers
├──────────────────────────────────────┤
│  Domain Models  (models/)            │  SQLAlchemy ORM models, Alembic migrations
└──────────────────────────────────────┘
```

Additional cross-cutting modules:
- `core/security.py` — password hashing (bcrypt), session token management, HMAC verification
- `core/auth.py` — session validation middleware, RBAC dependency injectors
- `core/audit.py` — immutable audit log writer
- `core/notifications.py` — in-app notification dispatch and trigger engine
- `core/data_quality.py` — field coverage checks, range validation, similarity dedup, quarantine queue
- `core/rate_limit.py` — per-client rate limiting for integration endpoints

### 2.3 Resource Groups (API Prefixes)

| Prefix                   | Responsibility                                                                 |
|--------------------------|--------------------------------------------------------------------------------|
| `/auth`                  | Sign-in, sign-out, session status, password management                         |
| `/admin`                 | Organisations, terms, courses, sections, registration rounds, user management |
| `/courses`               | Course discovery, section browsing, eligibility checks                         |
| `/registration`          | Add/drop, waitlist, enrollment status, change history                          |
| `/reviews`               | Reviewer assignment, scoring, outlier flags, recheck, round lifecycle          |
| `/finance`               | Ledger entries, payment recording, reconciliation, late fees, refunds          |
| `/messaging`             | In-app notifications, delivery/read tracking                                   |
| `/integrations`          | SIS and question-bank hooks, HMAC auth, rate limit management                 |
| `/data-quality`          | Quality scores, quarantine queue management, dedup reports                    |

---

## 3. Domain Model

### 3.1 Core Entities

#### Organisation & Academic Structure
- `Organisation` — top-level tenant; defines scope for all other entities
- `Term` — academic period with `start_date`, `end_date`, `status`
- `Course` — catalog entry with `code`, `title`, `credits`, `prerequisites[]`
- `Section` — offering of a course in a term; has `capacity`, `instructor_id`, `location`
- `RegistrationRound` — time window during which students may enroll; has `opens_at`, `closes_at`

#### Users & Roles
- `User` — `username` (student ID or employee ID), `password_hash`, `salt`, `role`, `status`, `reports_to`
- `Role` — enum: `STUDENT | INSTRUCTOR | REVIEWER | FINANCE_CLERK | ADMIN`
- `OrgGrant` / `ScopeGrant` — RBAC grants scoped to org-level or class-level

#### Enrollment
- `Enrollment` — `student_id`, `section_id`, `status` (`ENROLLED | WAITLISTED | DROPPED | COMPLETED`)
- `WaitlistEntry` — `student_id`, `section_id`, `queued_at` (FIFO ordering)
- `AddDropRequest` — `idempotency_key`, `actor_id`, `operation`, `status`, `created_at`

#### Review & Assessment
- `ReviewRound` — `section_id`, `visibility_mode` (`blind | semi_blind | open`), `status`, `scoring_form_id`
- `ScoringForm` — `name`, `criteria[]` (each with `weight`, `min_score`, `max_score`)
- `ReviewerAssignment` — `reviewer_id`, `submission_id`, `round_id`, `assignment_type` (`manual | rules`)
- `Score` — `assignment_id`, `criterion_id`, `value`, `comment`
- `OutlierFlag` — `score_id`, `median_at_time`, `deviation`, `resolved`, `resolved_by`
- `RecheckRequest` — `submission_id`, `round_id`, `requested_by`, `status`

#### Finance
- `LedgerAccount` — one per student; `balance`, `currency` (`USD`)
- `LedgerEntry` — `account_id`, `type` (`PREPAYMENT | DEPOSIT | BILLING | LATE_FEE | REFUND | REVERSAL`), `amount`, `reference`, `created_by`
- `PaymentInstrument` — `type` enum (`CASH | CHECK | INTERNAL_TRANSFER`)
- `BankStatementLine` — imported CSV rows for reconciliation
- `ReconciliationReport` — summary of matched/unmatched lines per import run

#### Messaging
- `Notification` — `recipient_id`, `type`, `payload`, `status` (`pending | delivered | read`), `delivered_at`, `read_at`
- `NotificationLog` — immutable status transition log

#### Governance
- `AuditLog` — `actor_id`, `action`, `entity_type`, `entity_id`, `before_hash`, `after_hash`, `timestamp`; write-once, 7-year retention
- `LoginAttempt` — tracks failed attempts per username; lockout after 5 in 15 minutes

#### Integration
- `IntegrationClient` — `client_id`, `secret_hash`, `rate_limit_rpm`, `allowed_scopes`
- `NonceLog` — `nonce`, `client_id`, `used_at`; replay protection

---

## 4. Module Specifications

### 4.1 Authentication / Accounts

**Responsibility:** Credential validation, session lifecycle, lockout, password rules.

**Rules:**
- Usernames may be student ID or employee ID
- Passwords: minimum 12 characters, must contain uppercase, lowercase, digit, and special character
- Passwords salted + hashed with bcrypt (work factor ≥ 12)
- 5 failed attempts within 15 minutes triggers a 30-minute lockout
- Sessions: 8-hour idle timeout, 24-hour absolute expiry
- Deactivation immediately revokes all active sessions (`revoked = true`)
- No SMS, no email, no third-party login

**Key Flows:**
1. `POST /auth/login` → validate credentials → check lockout → create session → return opaque token
2. Authenticated request middleware → look up session → check idle/absolute expiry → update `last_active_at`
3. `POST /auth/logout` → revoke session
4. `POST /auth/password/change` → verify current password → validate new complexity → update hash

**Failure Paths:**
- Wrong credentials: increment `LoginAttempt`; if threshold hit, set `locked_until`; return `401`
- Account locked: `403` with `locked_until` timestamp
- Expired session: `401` with `reason: session_expired`

---

### 4.2 Admin / Governance

**Responsibility:** Define and manage organisations, terms, courses, sections, and registration rounds. Manage users and RBAC grants.

**Key Flows:**
1. Admin creates `Organisation` → `Term` → `Course` (with prerequisites) → `Section` (assigns instructor, capacity)
2. Admin creates `RegistrationRound` for a term (time-windowed)
3. Admin creates user accounts, assigns roles, sets `reports_to`
4. Every mutation goes through `core/audit.py`: before/after hash written to `AuditLog`

**Validations:**
- Section capacity ≥ 1
- `RegistrationRound.opens_at` < `closes_at`, both within term dates
- Prerequisite courses must belong to the same organisation

---

### 4.3 Course Registration

**Responsibility:** Enrollment, add/drop, waitlist management, prerequisite and capacity enforcement.

**Rules:**
- Enrollment only allowed during an open `RegistrationRound` for the relevant term
- Prerequisite check: student must have `COMPLETED` enrollment in all prerequisite sections
- Capacity: enforced via `SELECT FOR UPDATE` + transactional insert; no oversubscription
- Add/drop is idempotent via `Idempotency-Key` header (uuid, 24-hour uniqueness per actor+operation)
- Waitlist backfill: when a seat opens (`DROPPED` or `COMPLETED`), a background task selects `min(queued_at)` eligible student, checks prerequisites and financial holds, promotes to `ENROLLED`

**Key Flows:**
1. `POST /registration/enroll` → check round open → check prereqs → check capacity → insert enrollment
2. `POST /registration/drop` → idempotency check → update status to `DROPPED` → trigger waitlist backfill
3. `GET /registration/status` → return current enrollment and waitlist status
4. `GET /registration/history` → change history for a student across terms

**Failure Paths:**
- Round closed: `409 Conflict`
- Missing prerequisite: `422 Unprocessable Entity` with missing courses listed
- Section full: `409 Conflict`, offer waitlist placement
- Duplicate idempotency key: `200 OK` with cached result, no re-execution

---

### 4.4 Review / Scoring Workbench

**Responsibility:** Manage review rounds, reviewer assignment, blind/semi-blind identity handling, scoring, outlier detection, recheck.

**Rules:**
- Reviewer assignment: manual (admin picks) or rules-based (system picks by load-balancing)
- Conflict of interest: reviewer cannot be assigned if `reviewer.section_ids ∩ student.section_ids ≠ ∅` or `reviewer.user_id == student.reports_to` or vice versa
- Identity visibility: API filters submission payload based on `ReviewRound.visibility_mode`
- Scoring: form-based (criteria with weights); `aggregate_score = Σ(criterion_score × weight) / Σ(weights)`
- Outlier: if `abs(score - rolling_median) >= 2.0` on a 5-point scale, write `OutlierFlag`; round cannot close with unresolved flags
- Recheck: a student or instructor may request re-review; coordinator assigns a new reviewer or overrides

**Key Flows:**
1. Admin/Instructor opens `ReviewRound`, sets `visibility_mode` and `scoring_form_id`
2. Reviewer assigned to submission (manual or automatic)
3. Reviewer fetches submission (identity filtered by visibility mode)
4. Reviewer submits scores per criterion + comments
5. System checks outlier threshold; flags if exceeded
6. Coordinator resolves/dismisses flags
7. Coordinator closes round → export scores and comments (structured JSON/CSV)

**Failure Paths:**
- COI violation: `409 Conflict` with conflict details
- Submitting score out of form range: `422 Unprocessable Entity`
- Round close with unresolved flags: `409 Conflict` listing unresolved `OutlierFlag` IDs

---

### 4.5 Finance / Settlement

**Responsibility:** Internal ledger, payment recording, reconciliation, late fees, refunds, arrears.

**Rules:**
- Ledger entries are immutable: refunds create reversing entries (never update)
- Payment instruments: `CASH | CHECK | INTERNAL_TRANSFER` only
- Late fee: 1.5% monthly, applied to current overdue balance, 10-day grace period, no compounding
- Reconciliation: CSV import → parse → match by reference/date ± 1 day → flag discrepancies

**Key Flows:**
1. Finance Clerk records payment → `POST /finance/payments` → write `LedgerEntry`
2. Month-end job: calculate late fees for accounts with overdue balance > 10 days
3. Reconciliation: `POST /finance/reconciliation/import` → CSV upload → parse → run match job → return report
4. Refund: `POST /finance/refunds` → validate original entry → write `REVERSAL` entry
5. Arrears view: `GET /finance/arrears` → accounts with balance_due > 0

**Failure Paths:**
- Negative payment amount: `422 Unprocessable Entity`
- Invalid CSV format: `400 Bad Request` with row-level errors
- Refund exceeds original payment: `422 Unprocessable Entity`

---

### 4.6 Messaging / Notifications

**Responsibility:** In-app notification generation, delivery tracking, read-status management.

**Trigger Events (configurable):**
- `ASSIGNMENT_POSTED` — when a reviewer is assigned a submission
- `DEADLINE_72H` — 72 hours before round closes
- `DEADLINE_24H` — 24 hours before round closes
- `DEADLINE_2H` — 2 hours before round closes
- `GRADING_COMPLETED` — when a round is closed and scores are finalized

**Rules:**
- Air-gapped: no email or push; only database-backed in-app notifications
- `delivered_at`: set when the record is persisted
- `read_at`: set when client calls `PATCH /messaging/notifications/{id}/read`
- All status transitions logged to `notification_log`

**Key Flows:**
1. Event fires (e.g., round closes) → `notifications.dispatch(event_type, recipients)`
2. Record inserted: `status = delivered`, `delivered_at = now()`
3. Client polls `GET /messaging/notifications` → returns unread count and list
4. Client marks read → `PATCH /messaging/notifications/{id}/read`

---

### 4.7 Data Quality

**Responsibility:** Enforce data completeness, validity, uniqueness, and similarity-based deduplication on record writes.

**Controls:**
- Required-field coverage: configurable per entity; writes rejected if coverage < threshold
- Range validation: numeric fields validated against defined min/max bounds
- Uniqueness: enforced by database constraints + pre-write uniqueness checks
- Similarity dedup: fingerprint (normalised lowercase stripped) + threshold string similarity (e.g., Jaro-Winkler ≥ 0.92) to detect near-duplicate records before insert
- Quality score: computed per record (0–100) based on field coverage and validation pass rate
- Quarantine queue: writes that fail quality checks land in `QuarantineEntry` with rejection reason; reviewable by Admin

**Key Flows:**
1. Write attempted → `data_quality.check(entity, payload)` → pass/fail
2. Fail → write to `QuarantineEntry` → return `202 Accepted` with quarantine ID
3. Admin reviews quarantine queue → resolves or discards entries
4. Quality report: `GET /data-quality/report` → summary of scores and quarantine stats

---

### 4.8 Open API Integrations

**Responsibility:** Authenticated, rate-limited, replay-protected endpoints for local SIS and question-bank integration.

**Rules:**
- HMAC-SHA256 signature on request body, `X-Signature-256` header
- Per-client rate limit: 120 requests/minute (configurable per `IntegrationClient`)
- Replay protection: `X-Nonce` + `X-Timestamp` (reject if timestamp > 5 minutes old or nonce reused)
- Client secrets shown once at registration; stored as SHA-256 hash

**Key Flows:**
1. SIS pushes student enrollment sync → `POST /integrations/sis/students`
2. Question bank pushes question sets → `POST /integrations/qbank/forms`
3. Rate limit exceeded: `429 Too Many Requests` with `Retry-After` header
4. Bad signature: `401 Unauthorized`
5. Replayed request: `409 Conflict` with `reason: nonce_reused`

---

## 5. Security Architecture

| Concern                  | Implementation                                                                 |
|--------------------------|--------------------------------------------------------------------------------|
| Authentication           | Local username/password only; bcrypt salted hash; stateful session tokens     |
| Session management       | 8h idle / 24h absolute expiry; instant revocation on deactivation              |
| Lockout                  | 5 failures in 15 min → 30-min cooldown; tracked per username                  |
| RBAC                     | Role + org/class-scope grants; enforced in service layer, not just router      |
| Audit log                | Immutable append-only; actor, action, before/after hash, timestamp; 7-year retention |
| Password rules           | ≥12 chars, upper + lower + digit + special; complexity enforced at set/change  |
| Secrets                  | No secrets in source or committed config; `.env.example` only                 |
| Integration auth         | HMAC-SHA256, nonce, timestamp; constant-time comparison                        |
| Data in transit          | TLS termination at reverse proxy (operator responsibility in air-gapped net)  |
| COI enforcement          | Checked server-side at reviewer assignment; escalated overrides audit-logged   |

---

## 6. Validation Rules Summary

| Field / Rule              | Validation                                                                    |
|---------------------------|-------------------------------------------------------------------------------|
| Password                  | ≥12 chars, upper, lower, digit, special char                                  |
| Score value               | Within `[ScoringCriterion.min_score, ScoringCriterion.max_score]`            |
| Outlier threshold         | ≥2.0 deviation from criterion median on a 5-point scale                       |
| Late fee rate             | Configurable; default 1.5% per month                                          |
| Grace period              | Configurable; default 10 days                                                 |
| Rate limit                | Configurable per `IntegrationClient`; default 120 req/min                     |
| Idempotency key TTL       | 24 hours per actor+operation                                                  |
| Session idle timeout      | 8 hours                                                                       |
| Session absolute timeout  | 24 hours                                                                       |
| HMAC timestamp tolerance  | ±5 minutes                                                                    |
| CSV reconciliation date   | Match window ±1 day                                                           |
| String similarity dedup   | Jaro-Winkler ≥ 0.92 (configurable)                                            |

---

## 7. Logging Approach

- Structured JSON logs to stdout (Docker-compatible)
- Log levels: `DEBUG` (dev), `INFO` (default production), `WARNING`, `ERROR`
- Key business events logged at `INFO`: login success/failure, enrollment change, payment recorded, round closed, flag raised/resolved, late fee applied, reconciliation run
- Errors logged at `ERROR` with request ID, actor ID (if known), and a safe error message (no stack traces in response body)
- All audit-log-worthy writes also emit a structured `AUDIT` log entry for correlation

---

## 8. Testing Approach

| Layer          | Coverage Target | Tools                        |
|----------------|-----------------|------------------------------|
| Unit tests     | Core services, validators, scoring calc, outlier detection, fee calc | `pytest` |
| API tests      | ≥90% API surface; happy path, missing params, permission errors, boundary values | `pytest` + `httpx` (TestClient) |
| Integration    | Enrollment → waitlist → backfill flow; scoring round full lifecycle; finance posting + reconciliation | `pytest`, Dockerized DB |
| Auth tests     | Lockout, expiry, revocation, RBAC enforcement | `pytest` |
| Data quality   | Dedup, quarantine, coverage checks | `pytest` |

All tests run via `run_tests.sh` at project root.

---

## 9. Docker Assumptions

- `docker compose up` is the canonical start command
- `api` service depends on `db` with a healthcheck wait
- `db` uses a named volume for persistence across restarts
- Migrations run automatically at API startup via Alembic `upgrade head`
- Environment variables are loaded from `.env` (copied from `.env.example` on first run)
- No interactive startup; all config is environment-driven
- The stack is self-contained: no outbound network required
