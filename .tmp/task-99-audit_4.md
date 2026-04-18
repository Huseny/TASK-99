# Static Delivery Acceptance + Architecture Audit (Rerun #4)

- Scope: static-only review of backend, frontend, tests, docs, and configuration.
- Constraints honored: no app execution, no test execution, no docker execution.
- Evidence: repository file references with line numbers.

## 1) Executive Verdict

Verdict: ACCEPTABLE (static acceptance pass), with low residual risks.

The two previously open gaps are now addressed in the current implementation:

1. Roster privileged writes now produce immutable audit events with actor attribution.
2. A dedicated concurrent enrollment contention test now exists and verifies no oversubscription.

No new blocker/high findings were identified in this rerun.

## 2) Coverage Against Prior Risk Areas

### Security and config hardening

- SECRET_KEY validation is enforced for minimum length and weak-value rejection: [backend/app/core/config.py](backend/app/core/config.py#L48).
- Development defaults stay consistent across env and compose:
  - [.env.example](.env.example#L2)
  - [docker-compose.yml](docker-compose.yml#L27)
- Documentation states fail-fast and minimum-key requirement: [README.md](README.md#L19), [README.md](README.md#L66).
- Config tests verify documented default compatibility and validation behavior: [backend/unit_tests/test_config.py](backend/unit_tests/test_config.py#L27).

### Integration security and auditability

- Integration sync/import audits now use integration actor IDs: [backend/app/routers/integrations.py](backend/app/routers/integrations.py#L74), [backend/app/routers/integrations.py](backend/app/routers/integrations.py#L101).
- Integration actor creation/linking is implemented in service: [backend/app/services/integration_service.py](backend/app/services/integration_service.py#L44).
- Signature, timestamp window, nonce replay, and rate limiting remain in place: [backend/app/services/integration_service.py](backend/app/services/integration_service.py#L87), [backend/app/services/integration_service.py](backend/app/services/integration_service.py#L112), [backend/app/services/integration_service.py](backend/app/services/integration_service.py#L142), [backend/app/services/integration_service.py](backend/app/services/integration_service.py#L127).
- API tests assert non-null actors for integration audit events: [backend/API_tests/test_integrations_api.py](backend/API_tests/test_integrations_api.py#L101), [backend/API_tests/test_integrations_api.py](backend/API_tests/test_integrations_api.py#L124).

### Reviews tenancy and COI controls

- Review round creation enforces section/form scope and org match: [backend/app/routers/reviews.py](backend/app/routers/reviews.py#L105), [backend/app/routers/reviews.py](backend/app/routers/reviews.py#L109), [backend/app/services/review_service.py](backend/app/services/review_service.py#L53).
- Manual and auto assignment paths enforce round/form scope: [backend/app/routers/reviews.py](backend/app/routers/reviews.py#L153), [backend/app/routers/reviews.py](backend/app/routers/reviews.py#L201).
- COI checks include multilevel reporting-line graph conflict: [backend/app/services/review_service.py](backend/app/services/review_service.py#L79), [backend/app/services/registration_service.py](backend/app/services/registration_service.py#L55).
- Tests cover cross-tenant form misuse and multilevel conflict blocking: [backend/API_tests/test_reviews_api.py](backend/API_tests/test_reviews_api.py#L550), [backend/API_tests/test_reviews_api.py](backend/API_tests/test_reviews_api.py#L577).

### Registration integrity and governance

- Enrollment still uses row-level lock path (`with_for_update`) to protect seat allocation: [backend/app/services/registration_service.py](backend/app/services/registration_service.py#L176), [backend/app/services/registration_service.py](backend/app/services/registration_service.py#L199).
- Roster add/remove now write audit logs with before/after state and actor:
  - add path: [backend/app/services/registration_service.py](backend/app/services/registration_service.py#L333)
  - remove path: [backend/app/services/registration_service.py](backend/app/services/registration_service.py#L361)
- Roster tests now assert audit creation and no-audit on unauthorized mutation:
  - [backend/API_tests/test_registration_api.py](backend/API_tests/test_registration_api.py#L287)
  - [backend/API_tests/test_registration_api.py](backend/API_tests/test_registration_api.py#L308)
  - [backend/API_tests/test_registration_api.py](backend/API_tests/test_registration_api.py#L326)

### Concurrency testing evidence

- Dedicated PostgreSQL-backed concurrency test exists and is explicitly marked:
  - test marker/skip contract: [backend/unit_tests/test_registration_concurrency.py](backend/unit_tests/test_registration_concurrency.py#L21)
  - threaded concurrent enrollment execution: [backend/unit_tests/test_registration_concurrency.py](backend/unit_tests/test_registration_concurrency.py#L78)
  - oversubscription assertions: [backend/unit_tests/test_registration_concurrency.py](backend/unit_tests/test_registration_concurrency.py#L81)
- Marker is registered in pytest config: [backend/pytest.ini](backend/pytest.ini#L4).

### Other privileged write domains

- Finance writes remain audit logged: [backend/app/routers/finance.py](backend/app/routers/finance.py#L84), [backend/app/routers/finance.py](backend/app/routers/finance.py#L125), [backend/app/routers/finance.py](backend/app/routers/finance.py#L315).
- Messaging dispatch/trigger updates are audit logged: [backend/app/routers/messaging.py](backend/app/routers/messaging.py#L36), [backend/app/routers/messaging.py](backend/app/routers/messaging.py#L71).
- Data-quality quarantine/resolve are audit logged: [backend/app/routers/data_quality.py](backend/app/routers/data_quality.py#L43), [backend/app/routers/data_quality.py](backend/app/routers/data_quality.py#L83).

### Frontend static test coverage (security-relevant flows)

- Route guard behavior unit test exists: [frontend/src/App.test.tsx](frontend/src/App.test.tsx#L34).
- Notification read journey e2e spec exists: [frontend/e2e/student-notifications.spec.js](frontend/e2e/student-notifications.spec.js#L3).

## 3) Findings (Severity-Ordered)

### Blocker

- None identified.

### High

- None identified.

### Medium

- None identified.

### Low

1. Actorless bootstrap remains a deliberate exception.
   - Evidence: bootstrap admin audit call permits actorless write: [backend/app/routers/auth.py](backend/app/routers/auth.py#L68).
   - Assessment: acceptable as a bootstrap-only path, but should remain narrowly scoped.

## 4) Previously Open Items Status

1. Roster privileged writes missing audit logs: RESOLVED.
   - Evidence: [backend/app/services/registration_service.py](backend/app/services/registration_service.py#L333), [backend/app/services/registration_service.py](backend/app/services/registration_service.py#L361), plus tests [backend/API_tests/test_registration_api.py](backend/API_tests/test_registration_api.py#L287).
2. Missing concurrency seat-contention test: RESOLVED.
   - Evidence: [backend/unit_tests/test_registration_concurrency.py](backend/unit_tests/test_registration_concurrency.py#L23), [backend/unit_tests/test_registration_concurrency.py](backend/unit_tests/test_registration_concurrency.py#L81).
3. Earlier secret-key and integration actor concerns: still resolved.
   - Evidence: [backend/app/core/config.py](backend/app/core/config.py#L48), [backend/app/routers/integrations.py](backend/app/routers/integrations.py#L74).

## 5) Test and Observability Assessment (Static)

- Positive:
  - Broad backend API/domain test suite remains present.
  - Unit tests enforce audit actor guardrails: [backend/unit_tests/test_audit.py](backend/unit_tests/test_audit.py#L14).
  - Concurrency test now explicitly targets capacity contention behavior.
- Residual:
  - Concurrency test is environment-gated (`POSTGRES_TEST_DATABASE_URL`), so pipeline effectiveness depends on CI/environment wiring: [backend/unit_tests/test_registration_concurrency.py](backend/unit_tests/test_registration_concurrency.py#L22).

## 6) Acceptance Decision and Close Conditions

Decision: PASS (static acceptance).

Recommended operational follow-up (non-blocking):

1. Ensure CI always provisions `POSTGRES_TEST_DATABASE_URL` for the `concurrent` marker path.
2. Keep bootstrap actorless exception constrained to [backend/app/routers/auth.py](backend/app/routers/auth.py#L52) and covered by policy/tests.
