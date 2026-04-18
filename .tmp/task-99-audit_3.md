# Static Delivery Acceptance + Architecture Audit

- Scope: Static-only audit of backend + frontend code and tests.
- Execution constraints honored: no app run, no tests run, no docker run, no edits to product code.
- Evidence style: file:line references only from inspected repository files.

## 1) Executive Verdict

Verdict: CONDITIONALLY ACCEPTABLE (not full pass yet).

The latest implementation resolves the prior blocker and most high-risk findings (secret-key default/validation consistency, integration actor attribution, review form tenancy checks, roster API availability, and multilevel reporting-line COI checks). Two material gaps remain for strict acceptance:

1. High: roster write operations are privileged mutations without immutable audit-log events.
2. Medium: no static evidence of concurrency-focused tests for seat contention around enrollment locking.

If the acceptance bar requires every privileged write to be auditable and tested for race-sensitive behavior, this rerun should remain open until those two gaps are closed.

## 2) Requirement Coverage Snapshot

### Security and config controls

- SECRET_KEY validation is now strict and rejects weak or short values: `backend/app/core/config.py:48-56`.
- `.env.example` and compose default align on a valid >=24-char development key: `.env.example:2`, `docker-compose.yml:27`.
- README now documents fail-fast behavior and minimum SECRET_KEY policy: `README.md:18-20`, `README.md:66`.
- Config tests explicitly verify default-secret validity and compose alignment: `backend/unit_tests/test_config.py:27-36`.

### Integrations

- Audit framework enforces actor by default: `backend/app/core/audit.py:26-30`.
- Integration sync/import now record actor via `ensure_client_actor(...)`: `backend/app/routers/integrations.py:74-83`, `backend/app/routers/integrations.py:101-110`.
- Integration actor creation/linking exists and is persisted on client lifecycle operations: `backend/app/services/integration_service.py:44-60`, `backend/app/services/integration_service.py:63-80`, `backend/app/services/integration_service.py:203-214`.
- Signature/timestamp/nonce/rate-limit controls remain present: `backend/app/services/integration_service.py:87-110`, `backend/app/services/integration_service.py:112-124`, `backend/app/services/integration_service.py:127-140`, `backend/app/services/integration_service.py:142-166`, `backend/app/services/integration_service.py:168-200`.
- API tests assert integration audit entries have non-null actor_id: `backend/API_tests/test_integrations_api.py:101-103`, `backend/API_tests/test_integrations_api.py:124-126`.

### Reviews

- Review form + round scope checks now gate both form access and form-section org match:
  - `backend/app/routers/reviews.py:105-110`
  - `backend/app/services/review_service.py:53-64`
- Manual/auto assignment paths enforce round/form scope before assignment: `backend/app/routers/reviews.py:151-154`, `backend/app/routers/reviews.py:199-202`.
- COI logic includes multilevel reporting graph conflict through registration helper: `backend/app/services/review_service.py:71-80` and `backend/app/services/registration_service.py:46-75`.
- Tests cover cross-tenant form misuse rejection and multilevel reporting conflict rejection: `backend/API_tests/test_reviews_api.py:550-575`, `backend/API_tests/test_reviews_api.py:577-608`.

### Registration

- Roster endpoints now exist (list/add/remove): `backend/app/routers/registration.py:155-176`.
- Roster service methods exist and enforce role/scope checks: `backend/app/services/registration_service.py:288-339`.
- Seat-claim lock for enroll path remains `with_for_update()`: `backend/app/services/registration_service.py:167-171`, used by `enroll(...)` at `backend/app/services/registration_service.py:190`.
- Roster behavior has API tests for scope denial and instructor add/remove success: `backend/API_tests/test_registration_api.py:280-291`.

### Finance, messaging, data quality

- Finance privileged write operations include audit logging in router: `backend/app/routers/finance.py:67-95`, `backend/app/routers/finance.py:112-140`, `backend/app/routers/finance.py:157-185`, `backend/app/routers/finance.py:200-228`, `backend/app/routers/finance.py:243-271`, `backend/app/routers/finance.py:315-327`.
- Messaging dispatch and trigger-update writes are audited: `backend/app/routers/messaging.py:36-45`, `backend/app/routers/messaging.py:71-82`.
- Data quality quarantine/resolve writes are audited: `backend/app/routers/data_quality.py:43-52`, `backend/app/routers/data_quality.py:83-92`.
- Broad API coverage exists for finance/messaging/data-quality:
  - `backend/API_tests/test_finance_api.py:32-153`
  - `backend/API_tests/test_messaging_api.py:58-254`
  - `backend/API_tests/test_data_quality_api.py:21-63`

### Frontend security-related tests (static presence)

- Route-guard behavior test exists for login/app redirection: `frontend/src/App.test.tsx:34-63`.
- Notification read journey e2e spec exists (mocked network): `frontend/e2e/student-notifications.spec.js:3-87`.

## 3) Findings (Ordered by Severity)

### High

1. Roster privileged writes are not audit-logged.
   - Why this matters: add/remove roster operations alter enrollment state and should be tamper-evident under governance/audit requirements.
   - Evidence:
     - Router add/remove calls only service methods, no `write_audit_log(...)`: `backend/app/routers/registration.py:160-176`.
     - Service mutates enrollment/history and commits without audit log entries: `backend/app/services/registration_service.py:301-320`, `backend/app/services/registration_service.py:323-339`.
     - By contrast, other privileged domains do log writes (finance/messaging/data-quality): `backend/app/routers/finance.py:67-95`, `backend/app/routers/messaging.py:36-45`, `backend/app/routers/data_quality.py:43-52`.
   - Recommendation: emit explicit `registration.roster.add` and `registration.roster.remove` audit records with actor_id, section_id, student_id, and before/after state hashes.

### Medium

2. Missing explicit concurrency tests for enrollment seat contention.
   - Why this matters: lock usage is present, but static test inventory does not demonstrate race-condition validation under concurrent enroll attempts.
   - Evidence:
     - Locking implementation exists: `backend/app/services/registration_service.py:167-171`, `backend/app/services/registration_service.py:190`.
     - Registration tests validate idempotency/full/waitlist/roster paths, but no concurrent multi-request contention test is evident: `backend/API_tests/test_registration_api.py:89-314`.
   - Recommendation: add a targeted integration test that issues concurrent enroll requests against a capacity-constrained section and asserts single winner + deterministic outcomes.

### Low / Residual risk notes

3. Actorless bootstrap remains a deliberate exception.
   - Evidence: `allow_actorless=True` in bootstrap-admin audit write: `backend/app/routers/auth.py:60-69`.
   - Context: this is likely intentional for first-admin creation and no longer indicates the earlier broad actor-null issue.
   - Recommendation: keep as-is, but consider adding an explicit justification note in docs/audit policy and a dedicated unit test guarding this single allowed path.

## 4) Previously Reported Issues Status

- SECRET_KEY default/validation mismatch: RESOLVED.
  - Evidence: `backend/app/core/config.py:48-56`, `.env.example:2`, `docker-compose.yml:27`, `backend/unit_tests/test_config.py:27-36`.

- Integration audit actor nullability on import/sync: RESOLVED.
  - Evidence: `backend/app/routers/integrations.py:74-83`, `backend/app/routers/integrations.py:101-110`, `backend/API_tests/test_integrations_api.py:101-103`, `backend/API_tests/test_integrations_api.py:124-126`.

- Review form-scope/tenant hardening: RESOLVED.
  - Evidence: `backend/app/routers/reviews.py:105-110`, `backend/app/services/review_service.py:53-64`, `backend/API_tests/test_reviews_api.py:550-575`.

- Missing roster management flow: RESOLVED (feature availability).
  - Evidence: `backend/app/routers/registration.py:155-176`, `backend/API_tests/test_registration_api.py:280-291`.

- Multilevel reporting-line COI gap: RESOLVED.
  - Evidence: `backend/app/services/registration_service.py:46-75`, `backend/app/services/review_service.py:79`, `backend/API_tests/test_reviews_api.py:577-608`.

## 5) Testing and Observability Assessment (Static)

- Positive:
  - API test suite includes core domain paths across admin/auth/registration/reviews/integrations/finance/messaging/data-quality.
  - Audit-actor enforcement has a unit test for rejecting actorless privileged writes: `backend/unit_tests/test_audit.py:1-23`.
  - Frontend has route-security unit test and notifications flow e2e spec.

- Gaps:
  - No static evidence of explicit concurrency/race tests for enrollment seat contention.
  - No static evidence that roster writes emit immutable audit events (also a functional governance gap, not just a testing gap).

## 6) Acceptance Decision and Close Conditions

Current decision: NOT FULLY ACCEPTED (close to pass).

Required to close:

1. Add immutable audit-log writes for roster add/remove operations.
2. Add at least one deterministic concurrency test for capacity contention on enrollment.

Once the above are present (and statically verifiable), this codebase would satisfy the previously flagged acceptance concerns from this audit track.
