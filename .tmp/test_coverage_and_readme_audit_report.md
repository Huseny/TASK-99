# Combined Audit Report: Test Coverage + README Compliance

Date: 2026-04-18
Audit mode: static inspection only (no execution)
Project type detection: declared in README title as fullstack

---

## 1. Test Coverage Audit

### Backend Endpoint Inventory

Resolved from router decorators in backend/app/routers/\*.py plus app mount prefix /api/v1 in backend/app/main.py.
Total endpoints: 82

1. DELETE /api/v1/admin/courses/{course_id}
2. DELETE /api/v1/admin/organizations/{organization_id}
3. DELETE /api/v1/admin/registration-rounds/{round_id}
4. DELETE /api/v1/admin/scope-grants/{grant_id}
5. DELETE /api/v1/admin/sections/{section_id}
6. DELETE /api/v1/admin/terms/{term_id}
7. DELETE /api/v1/admin/users/{user_id}
8. DELETE /api/v1/sections/{section_id}/roster/{student_id}
9. GET /api/v1/admin/audit-log
10. GET /api/v1/admin/courses
11. GET /api/v1/admin/organizations
12. GET /api/v1/admin/registration-rounds
13. GET /api/v1/admin/scope-grants
14. GET /api/v1/admin/sections
15. GET /api/v1/admin/terms
16. GET /api/v1/admin/users
17. GET /api/v1/auth/me
18. GET /api/v1/courses
19. GET /api/v1/courses/{course_id}
20. GET /api/v1/courses/{course_id}/sections/{section_id}/eligibility
21. GET /api/v1/data-quality/quarantine
22. GET /api/v1/data-quality/report
23. GET /api/v1/finance/accounts/{student_id}
24. GET /api/v1/finance/arrears
25. GET /api/v1/finance/reconciliation/{import_id}/report
26. GET /api/v1/health/live
27. GET /api/v1/health/ready
28. GET /api/v1/messaging/notifications
29. GET /api/v1/messaging/triggers
30. GET /api/v1/registration/history
31. GET /api/v1/registration/status
32. GET /api/v1/reviews/rounds/{round_id}/assignments
33. GET /api/v1/reviews/rounds/{round_id}/export
34. GET /api/v1/reviews/rounds/{round_id}/outliers
35. GET /api/v1/sections/{section_id}/roster
36. PATCH /api/v1/data-quality/quarantine/{entry_id}/resolve
37. PATCH /api/v1/messaging/notifications/{notification_id}/read
38. POST /api/v1/admin/audit-log/retention
39. POST /api/v1/admin/courses
40. POST /api/v1/admin/organizations
41. POST /api/v1/admin/registration-rounds
42. POST /api/v1/admin/scope-grants
43. POST /api/v1/admin/sections
44. POST /api/v1/admin/terms
45. POST /api/v1/admin/users
46. POST /api/v1/auth/bootstrap-admin
47. POST /api/v1/auth/login
48. POST /api/v1/auth/logout
49. POST /api/v1/auth/password/change
50. POST /api/v1/data-quality/validate-write
51. POST /api/v1/finance/deposits
52. POST /api/v1/finance/month-end-billing
53. POST /api/v1/finance/payments
54. POST /api/v1/finance/prepayments
55. POST /api/v1/finance/reconciliation/import
56. POST /api/v1/finance/refunds
57. POST /api/v1/integrations/clients
58. POST /api/v1/integrations/clients/{client_id}/rotate-secret
59. POST /api/v1/integrations/qbank/forms
60. POST /api/v1/integrations/sis/students
61. POST /api/v1/messaging/dispatch
62. POST /api/v1/messaging/triggers/process-due
63. POST /api/v1/registration/drop
64. POST /api/v1/registration/enroll
65. POST /api/v1/registration/waitlist
66. POST /api/v1/reviews/forms
67. POST /api/v1/reviews/rechecks
68. POST /api/v1/reviews/rechecks/{recheck_id}/assign
69. POST /api/v1/reviews/rounds
70. POST /api/v1/reviews/rounds/{round_id}/assignments/auto
71. POST /api/v1/reviews/rounds/{round_id}/assignments/manual
72. POST /api/v1/reviews/rounds/{round_id}/close
73. POST /api/v1/reviews/rounds/{round_id}/outliers/{flag_id}/resolve
74. POST /api/v1/reviews/scores
75. POST /api/v1/sections/{section_id}/roster
76. PUT /api/v1/admin/courses/{course_id}
77. PUT /api/v1/admin/organizations/{organization_id}
78. PUT /api/v1/admin/registration-rounds/{round_id}
79. PUT /api/v1/admin/sections/{section_id}
80. PUT /api/v1/admin/terms/{term_id}
81. PUT /api/v1/admin/users/{user_id}
82. PUT /api/v1/messaging/triggers/{trigger_type}

### API Test Mapping Table

Legend:

- true no-mock HTTP = real network HTTP via httpx against running API, no DI override
- HTTP with mocking = FastAPI TestClient with dependency override (SQLite substitution)

| Endpoint                                                          | Covered | Test type         | Test files                                 | Evidence                                                                              |
| ----------------------------------------------------------------- | ------- | ----------------- | ------------------------------------------ | ------------------------------------------------------------------------------------- |
| DELETE /api/v1/admin/courses/{course_id}                          | yes     | true no-mock HTTP | backend/integration/test_api_external.py   | test_full_catalog_crud_lifecycle (uses \_delete loop)                                 |
| DELETE /api/v1/admin/organizations/{organization_id}              | yes     | true no-mock HTTP | backend/integration/test_api_external.py   | test_org_create_update_delete_lifecycle                                               |
| DELETE /api/v1/admin/registration-rounds/{round_id}               | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_admin_registration_rounds_list_and_update (cleanup helper)                       |
| DELETE /api/v1/admin/scope-grants/{grant_id}                      | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_admin_scope_grants_create_list_delete                                            |
| DELETE /api/v1/admin/sections/{section_id}                        | yes     | true no-mock HTTP | backend/integration/test_api_external.py   | test_full_catalog_crud_lifecycle (uses \_delete loop)                                 |
| DELETE /api/v1/admin/terms/{term_id}                              | yes     | true no-mock HTTP | backend/integration/test_api_external.py   | test_full_catalog_crud_lifecycle (uses \_delete loop)                                 |
| DELETE /api/v1/admin/users/{user_id}                              | yes     | true no-mock HTTP | backend/integration/test_api_external.py   | test_full_auth_lifecycle (cleanup), test_student_cannot_access_admin_routes (cleanup) |
| DELETE /api/v1/sections/{section_id}/roster/{student_id}          | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_registration_full_workflow                                                       |
| GET /api/v1/admin/audit-log                                       | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_admin_audit_log_and_retention                                                    |
| GET /api/v1/admin/courses                                         | yes     | true no-mock HTTP | backend/integration/test_api_external.py   | test_full_catalog_crud_lifecycle                                                      |
| GET /api/v1/admin/organizations                                   | yes     | true no-mock HTTP | backend/integration/test_api_external.py   | test_org_create_update_delete_lifecycle                                               |
| GET /api/v1/admin/registration-rounds                             | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_admin_registration_rounds_list_and_update                                        |
| GET /api/v1/admin/scope-grants                                    | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_admin_scope_grants_create_list_delete                                            |
| GET /api/v1/admin/sections                                        | yes     | true no-mock HTTP | backend/integration/test_api_external.py   | test_full_catalog_crud_lifecycle                                                      |
| GET /api/v1/admin/terms                                           | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_admin_terms_list_and_update                                                      |
| GET /api/v1/admin/users                                           | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_admin_users_list_and_update                                                      |
| GET /api/v1/auth/me                                               | yes     | true no-mock HTTP | backend/integration/test_api_external.py   | test_unauthenticated_request_returns_401, test_full_auth_lifecycle                    |
| GET /api/v1/courses                                               | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_registration_full_workflow                                                       |
| GET /api/v1/courses/{course_id}                                   | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_registration_full_workflow                                                       |
| GET /api/v1/courses/{course_id}/sections/{section_id}/eligibility | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_registration_full_workflow                                                       |
| GET /api/v1/data-quality/quarantine                               | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_data_quality_quarantine_and_report                                               |
| GET /api/v1/data-quality/report                                   | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_data_quality_quarantine_and_report                                               |
| GET /api/v1/finance/accounts/{student_id}                         | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_finance_payment_lifecycle                                                        |
| GET /api/v1/finance/arrears                                       | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_finance_payment_lifecycle                                                        |
| GET /api/v1/finance/reconciliation/{import_id}/report             | yes     | HTTP with mocking | backend/API_tests/test_finance_api.py      | test_payment_refund_arrears_reconciliation                                            |
| GET /api/v1/health/live                                           | yes     | true no-mock HTTP | backend/integration/test_api_external.py   | test_health_live_returns_ok                                                           |
| GET /api/v1/health/ready                                          | yes     | true no-mock HTTP | backend/integration/test_api_external.py   | test_health_ready_performs_db_check                                                   |
| GET /api/v1/messaging/notifications                               | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_messaging_dispatch_triggers_and_notification_lifecycle                           |
| GET /api/v1/messaging/triggers                                    | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_messaging_dispatch_triggers_and_notification_lifecycle                           |
| GET /api/v1/registration/history                                  | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_registration_full_workflow                                                       |
| GET /api/v1/registration/status                                   | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_registration_full_workflow                                                       |
| GET /api/v1/reviews/rounds/{round_id}/assignments                 | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_review_round_lifecycle                                                           |
| GET /api/v1/reviews/rounds/{round_id}/export                      | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_review_round_lifecycle                                                           |
| GET /api/v1/reviews/rounds/{round_id}/outliers                    | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_review_round_lifecycle                                                           |
| GET /api/v1/sections/{section_id}/roster                          | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_registration_full_workflow                                                       |
| PATCH /api/v1/data-quality/quarantine/{entry_id}/resolve          | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_data_quality_quarantine_and_report                                               |
| PATCH /api/v1/messaging/notifications/{notification_id}/read      | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_messaging_dispatch_triggers_and_notification_lifecycle                           |
| POST /api/v1/admin/audit-log/retention                            | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_admin_audit_log_and_retention                                                    |
| POST /api/v1/admin/courses                                        | yes     | true no-mock HTTP | backend/integration/test_api_external.py   | test_full_catalog_crud_lifecycle                                                      |
| POST /api/v1/admin/organizations                                  | yes     | true no-mock HTTP | backend/integration/test_api_external.py   | test_org_create_update_delete_lifecycle                                               |
| POST /api/v1/admin/registration-rounds                            | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_admin_registration_rounds_list_and_update                                        |
| POST /api/v1/admin/scope-grants                                   | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_admin_scope_grants_create_list_delete                                            |
| POST /api/v1/admin/sections                                       | yes     | true no-mock HTTP | backend/integration/test_api_external.py   | test_full_catalog_crud_lifecycle                                                      |
| POST /api/v1/admin/terms                                          | yes     | true no-mock HTTP | backend/integration/test_api_external.py   | test_full_catalog_crud_lifecycle                                                      |
| POST /api/v1/admin/users                                          | yes     | true no-mock HTTP | backend/integration/test_api_external.py   | test_full_auth_lifecycle                                                              |
| POST /api/v1/auth/bootstrap-admin                                 | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_bootstrap_admin_rejected_after_initial_setup                                     |
| POST /api/v1/auth/login                                           | yes     | true no-mock HTTP | backend/integration/test_api_external.py   | test_full_auth_lifecycle                                                              |
| POST /api/v1/auth/logout                                          | yes     | true no-mock HTTP | backend/integration/test_api_external.py   | test_full_auth_lifecycle                                                              |
| POST /api/v1/auth/password/change                                 | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_password_change_lifecycle                                                        |
| POST /api/v1/data-quality/validate-write                          | yes     | HTTP with mocking | backend/API_tests/test_data_quality_api.py | test_quarantine_and_resolution_and_report                                             |
| POST /api/v1/finance/deposits                                     | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_finance_payment_lifecycle                                                        |
| POST /api/v1/finance/month-end-billing                            | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_finance_payment_lifecycle                                                        |
| POST /api/v1/finance/payments                                     | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_finance_payment_lifecycle                                                        |
| POST /api/v1/finance/prepayments                                  | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_finance_payment_lifecycle                                                        |
| POST /api/v1/finance/reconciliation/import                        | yes     | HTTP with mocking | backend/API_tests/test_finance_api.py      | test_payment_refund_arrears_reconciliation                                            |
| POST /api/v1/finance/refunds                                      | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_finance_payment_lifecycle                                                        |
| POST /api/v1/integrations/clients                                 | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_integration_client_create_and_rotate_secret                                      |
| POST /api/v1/integrations/clients/{client_id}/rotate-secret       | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_integration_client_create_and_rotate_secret                                      |
| POST /api/v1/integrations/qbank/forms                             | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_integration_client_create_and_rotate_secret                                      |
| POST /api/v1/integrations/sis/students                            | yes     | HTTP with mocking | backend/API_tests/test_integrations_api.py | test_sis_sync_updates_existing_external_id_without_conflict                           |
| POST /api/v1/messaging/dispatch                                   | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_messaging_dispatch_triggers_and_notification_lifecycle                           |
| POST /api/v1/messaging/triggers/process-due                       | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_messaging_dispatch_triggers_and_notification_lifecycle                           |
| POST /api/v1/registration/drop                                    | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_registration_full_workflow                                                       |
| POST /api/v1/registration/enroll                                  | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_registration_full_workflow                                                       |
| POST /api/v1/registration/waitlist                                | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_registration_waitlist                                                            |
| POST /api/v1/reviews/forms                                        | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_review_round_lifecycle                                                           |
| POST /api/v1/reviews/rechecks                                     | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_review_auto_assign_and_recheck_lifecycle                                         |
| POST /api/v1/reviews/rechecks/{recheck_id}/assign                 | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_review_auto_assign_and_recheck_lifecycle                                         |
| POST /api/v1/reviews/rounds                                       | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_review_round_lifecycle                                                           |
| POST /api/v1/reviews/rounds/{round_id}/assignments/auto           | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_review_auto_assign_and_recheck_lifecycle                                         |
| POST /api/v1/reviews/rounds/{round_id}/assignments/manual         | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_review_round_lifecycle                                                           |
| POST /api/v1/reviews/rounds/{round_id}/close                      | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_review_round_lifecycle                                                           |
| POST /api/v1/reviews/rounds/{round_id}/outliers/{flag_id}/resolve | yes     | HTTP with mocking | backend/API_tests/test_reviews_api.py      | test_review_round_end_to_end                                                          |
| POST /api/v1/reviews/scores                                       | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_review_round_lifecycle                                                           |
| POST /api/v1/sections/{section_id}/roster                         | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_registration_full_workflow                                                       |
| PUT /api/v1/admin/courses/{course_id}                             | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_admin_catalog_update_endpoints                                                   |
| PUT /api/v1/admin/organizations/{organization_id}                 | yes     | true no-mock HTTP | backend/integration/test_api_external.py   | test_org_create_update_delete_lifecycle                                               |
| PUT /api/v1/admin/registration-rounds/{round_id}                  | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_admin_registration_rounds_list_and_update                                        |
| PUT /api/v1/admin/sections/{section_id}                           | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_admin_catalog_update_endpoints                                                   |
| PUT /api/v1/admin/terms/{term_id}                                 | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_admin_terms_list_and_update                                                      |
| PUT /api/v1/admin/users/{user_id}                                 | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_admin_users_list_and_update                                                      |
| PUT /api/v1/messaging/triggers/{trigger_type}                     | yes     | true no-mock HTTP | backend/integration/test_api_real.py       | test_messaging_dispatch_triggers_and_notification_lifecycle                           |

### API Test Classification

1. True No-Mock HTTP

- backend/integration/test_api_external.py
- backend/integration/test_api_real.py
- Evidence: file headers explicitly state real HTTP via httpx and no TestClient/DI override.

2. HTTP with Mocking

- backend/API_tests/\*.py via backend/API_tests/conftest.py
- Evidence: backend/API_tests/conftest.py overrides get_db using app.dependency_overrides and swaps DB to sqlite:///./test_api.db with TestClient.

3. Non-HTTP (unit/integration without HTTP)

- backend/unit_tests/\*.py (direct service/model logic)
- frontend/src/\*_/_.test.\* (component/context/api-module unit tests under Vitest)

### Mock Detection

Detected mocking/overrides:

- Dependency-injection override: app.dependency_overrides[get_db] = override_get_db in backend/API_tests/conftest.py.
- In-memory/local substitute DB for API tests: sqlite test DB in backend/API_tests/conftest.py.
- Frontend vi.mock usage:
  - frontend/src/App.test.tsx (mocks AuthContext, LoginPage, AppPortal)
  - frontend/src/pages/AppPortal.test.tsx (mocks messaging API and dashboard modules)
  - frontend/src/pages/LoginPage.test.tsx (mocks AuthContext)
  - frontend/src/contexts/AuthContext.test.tsx (mocks auth API)
  - frontend/src/api/\*.test.ts (mocks api client)

### Coverage Summary

- Total endpoints: 82
- Endpoints with HTTP tests (any HTTP): 82
- Endpoints with true no-mock HTTP coverage: 77

Computed metrics:

- HTTP coverage = 82 / 82 = 100.0%
- True API coverage = 77 / 82 = 93.9%

Endpoints without true no-mock HTTP evidence (HTTP-with-mocking only):

- POST /api/v1/data-quality/validate-write
- POST /api/v1/finance/reconciliation/import
- GET /api/v1/finance/reconciliation/{import_id}/report
- POST /api/v1/integrations/sis/students
- POST /api/v1/reviews/rounds/{round_id}/outliers/{flag_id}/resolve

### Unit Test Summary

Backend unit tests:

- Files:
  - backend/unit_tests/test_audit.py
  - backend/unit_tests/test_auth_service.py
  - backend/unit_tests/test_config.py
  - backend/unit_tests/test_data_quality_service.py
  - backend/unit_tests/test_finance_service.py
  - backend/unit_tests/test_integration_service.py
  - backend/unit_tests/test_messaging_service.py
  - backend/unit_tests/test_registration_concurrency.py
  - backend/unit_tests/test_review_service.py
- Modules covered:
  - Services: auth, review, finance, data-quality, integration, messaging
  - Core/config: config validation
  - Audit utility behavior
  - Registration concurrency behavior
- Important backend modules not unit-tested directly:
  - Router/controller modules in backend/app/routers/\*.py
  - Authorization policy layer in backend/app/core/authz.py (no direct unit test file found)
  - Middleware behavior in backend/app/main.py (partly exercised by HTTP tests, not unit-only)

Frontend unit tests (STRICT REQUIREMENT):

- Frontend unit tests: PRESENT
- Evidence files:
  - frontend/src/App.test.tsx
  - frontend/src/components/AppShell.test.tsx
  - frontend/src/components/NotificationsDrawer.test.tsx
  - frontend/src/components/StateBlock.test.tsx
  - frontend/src/contexts/AuthContext.test.tsx
  - frontend/src/pages/AppPortal.test.tsx
  - frontend/src/pages/LoginPage.test.tsx
  - frontend/src/api/admin.test.ts
  - frontend/src/api/auth.test.ts
  - frontend/src/api/dataQuality.test.ts
  - frontend/src/api/finance.test.ts
  - frontend/src/api/messaging.test.ts
  - frontend/src/api/registration.test.ts
  - frontend/src/api/reviews.test.ts
- Frameworks/tools detected:
  - Vitest (frontend/package.json scripts/devDependencies)
  - @testing-library/react
  - @testing-library/jest-dom via frontend/src/test/setup.ts
- Components/modules covered:
  - App routing/auth guard behavior
  - AppShell, NotificationsDrawer, StateBlock components
  - AuthContext provider lifecycle
  - LoginPage and AppPortal role-dependent behavior
  - Frontend API wrappers under frontend/src/api/\*.ts
- Important frontend components/modules not directly tested:
  - frontend/src/hooks/useAsyncResource.ts
  - frontend/src/pages/dashboard/AdminDashboard.tsx
  - frontend/src/pages/dashboard/DataQualityDashboard.tsx
  - frontend/src/pages/dashboard/FinanceDashboard.tsx
  - frontend/src/pages/dashboard/ReviewerDashboard.tsx
  - frontend/src/pages/dashboard/StudentDashboard.tsx
  - frontend/src/main.tsx
  - frontend/src/theme.ts

Cross-layer observation:

- Both backend and frontend have unit-level tests.
- Backend API coverage depth is materially stronger than frontend component-level depth, but frontend is not untested.
- Fullstack E2E files exist (frontend/e2e/\*.spec.js), partially balancing layer integration checks.

### API Observability Check

Result: mostly strong

- Strong evidence:
  - API tests generally show method/path, request body/headers, and response assertions (status and selected fields).
  - Integration tests include lifecycle assertions and RBAC checks.
- Weak spots:
  - Some checks are status-only for specific probes (for example basic health assertions).
  - Some endpoint coverage in integration suite is indirect via helper cleanup methods (still valid endpoint hits, but less explicit request/response intent in the test body).

### Test Quality & Sufficiency

- Success paths: broadly covered across auth/admin/registration/reviews/finance/messaging/integrations.
- Failure cases: present (RBAC denies, validation errors, conflicts, malformed input, lockout/session cases).
- Edge cases: present (idempotency behavior, reconciliation false-positive prevention, COI assignment blocks, semi-blind identity behavior, lockout/session expiry).
- Validation depth: moderate-to-strong.
- Auth/permissions: strong coverage in both API and integration tests.
- Integration boundaries: strong true no-mock coverage via backend/integration HTTP tests.
- Over-mocking risk: limited in integration suite; present by design in backend/API_tests and frontend unit tests.

run_tests.sh check:

- Docker-based orchestration and execution only.
- Verdict: OK (no local package-install dependency required by test runner itself).

### End-to-End Expectations (Fullstack)

Expectation: fullstack should have FE<->BE E2E tests.
Observed:

- Present: frontend/e2e/\*.spec.js (Playwright), including cross-role workflow and API authorization checks.
- Compensation status: strong API and unit coverage plus available E2E suite.

### Tests Check

- HTTP endpoint coverage breadth: complete (100%).
- True no-mock API coverage: high but not complete (93.9%).
- Remaining no-mock gaps are concentrated in 5 endpoints listed above.

### Test Coverage Score (0-100)

Score: 92

### Score Rationale

- - High endpoint breadth (82/82 with HTTP tests).
- - High true no-mock coverage (77/82).
- - Strong auth/RBAC and business-flow test depth.
- - Backend and frontend unit test presence confirmed.
- - Five endpoints are only covered in HTTP-with-mocking mode.
- - Some frontend feature modules (dashboard pages/hook/bootstrap/theme) have no direct tests.

### Key Gaps

1. True no-mock gap: POST /api/v1/data-quality/validate-write
2. True no-mock gap: POST /api/v1/finance/reconciliation/import
3. True no-mock gap: GET /api/v1/finance/reconciliation/{import_id}/report
4. True no-mock gap: POST /api/v1/integrations/sis/students
5. True no-mock gap: POST /api/v1/reviews/rounds/{round_id}/outliers/{flag_id}/resolve
6. Frontend unit gap: dashboard components/hook/main bootstrap are not directly tested.

### Confidence & Assumptions

- Confidence: high for route inventory and test-file classification.
- Confidence: medium-high for endpoint-to-test mapping because analysis is static and dynamic IDs/paths are normalized by textual evidence.
- Assumption: helper-based DELETE calls in integration tests are counted as valid endpoint hits because they issue concrete HTTP requests to exact method/path templates.

Test Coverage Audit Verdict: PASS (strong coverage, with explicit true no-mock gaps)

---

## 2. README Audit

Target file: repo/README.md
Found: yes

### Hard Gate Evaluation

1. Formatting/readability

- Pass: clean markdown structure with sections, tables, commands.

2. Startup instructions (backend/fullstack requires docker-compose up)

- Pass: includes docker-compose up in Quick Start.

3. Access method

- Pass: includes URL + port for API and Web services.

4. Verification method

- Pass: includes web verification flow and API curl probes.

5. Environment rules (no runtime installs/manual DB setup)

- Pass: README explicitly states Docker-contained workflow and does not instruct pip install/npm install/apt-get/manual DB setup.

6. Demo credentials (auth exists -> must include username/password/all roles)

- Pass: role table includes credentials for Admin, Student, Instructor, Reviewer, Finance Clerk.
- Note: README explicitly states only Admin and Student are created by bootstrap snippet; remaining roles require admin user creation commands.

### High Priority Issues

- None.

### Medium Priority Issues

1. Verification snippets depend on jq on host (curl ... | jq), which is an undeclared host tool assumption.
2. Demo credentials for non-bootstrap roles are documented but not automatically provisioned by the shown bootstrap sequence; this can confuse first-run validation.

### Low Priority Issues

1. Duplicate verification intent appears in both "Web Verification Flow" and "Verification" sections; could be consolidated for brevity.

### Hard Gate Failures

- None detected.

### Engineering Quality

- Tech stack clarity: strong (FastAPI, React/MUI, PostgreSQL, Docker).
- Architecture explanation: strong (diagram and router coverage).
- Testing instructions: strong (single run_tests.sh flow documented).
- Security/roles: strong (roles and scope grants described).
- Workflows/presentation quality: strong and operationally actionable.

README Verdict: PASS

---

## Final Verdicts

- Test Coverage Audit: PASS
- README Audit: PASS
