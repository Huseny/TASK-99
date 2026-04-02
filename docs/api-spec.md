# API Specification — Collegiate Enrollment & Assessment Management System (CEAMS)

**Base URL:** `http://localhost:8000`
**Auth:** All endpoints (except `/auth/login`) require `Authorization: Bearer <session_token>` header.
**Content-Type:** `application/json` unless otherwise noted.

---

## Conventions

### Error Response Body
```json
{
  "code": 422,
  "msg": "Descriptive error message",
  "detail": [{ "field": "password", "issue": "must be at least 12 characters" }]
}
```

### Pagination
List endpoints accept `?page=1&page_size=20`. Responses include:
```json
{ "items": [...], "total": 150, "page": 1, "page_size": 20 }
```

### HTTP Status Codes Used
| Code | Meaning |
|------|---------|
| 200  | OK |
| 201  | Created |
| 202  | Accepted (async / quarantined) |
| 204  | No Content (delete/revoke) |
| 400  | Bad Request (malformed payload) |
| 401  | Unauthorized (missing/invalid/expired session) |
| 403  | Forbidden (account locked, RBAC denied) |
| 404  | Not Found |
| 409  | Conflict (capacity, duplicate, COI, unresolved flag) |
| 422  | Unprocessable Entity (validation failure) |
| 429  | Too Many Requests (rate limit) |

---

## 1. Authentication / Accounts — `/auth`

### POST /auth/login
Sign in with local credentials.

**Auth required:** No

**Request:**
```json
{ "username": "STU00123", "password": "SecureP@ss1234" }
```

**Response 200:**
```json
{ "session_token": "<opaque_256bit_hex>", "expires_at": "2026-04-03T08:04:00Z" }
```

**Response 401:** Invalid credentials.
**Response 403:** `{ "code": 403, "msg": "Account locked", "locked_until": "2026-04-02T12:30:00Z" }`

---

### POST /auth/logout
Revoke the current session.

**Response 204:** No content.

---

### GET /auth/me
Return current user profile and session expiry.

**Response 200:**
```json
{
  "user_id": "usr_abc123",
  "username": "STU00123",
  "role": "STUDENT",
  "status": "ACTIVE",
  "session_expires_at": "2026-04-03T08:04:00Z"
}
```

---

### POST /auth/password/change
Change the authenticated user's password.

**Request:**
```json
{ "current_password": "old", "new_password": "NewP@ss5678XY" }
```

**Response 204:** Success.
**Response 422:** Complexity rules not met.

---

## 2. Admin / Governance — `/admin`

**RBAC required:** `ADMIN` role for all endpoints in this group.

### POST /admin/organisations
Create an organisation.

**Request:**
```json
{ "name": "City University", "code": "CU" }
```

**Response 201:** `{ "org_id": "org_001", "name": "City University", "code": "CU" }`

---

### POST /admin/terms
Create a term within an organisation.

**Request:**
```json
{ "org_id": "org_001", "name": "Spring 2026", "start_date": "2026-01-15", "end_date": "2026-05-31" }
```

**Response 201:** Term object.

---

### POST /admin/courses
Create a course with optional prerequisites.

**Request:**
```json
{
  "org_id": "org_001",
  "code": "CS301",
  "title": "Algorithms",
  "credits": 3,
  "prerequisite_course_ids": ["crs_001"]
}
```

**Response 201:** Course object.

---

### POST /admin/sections
Create a section (course offering in a term).

**Request:**
```json
{
  "course_id": "crs_002",
  "term_id": "trm_001",
  "instructor_id": "usr_inst01",
  "capacity": 30,
  "location": "Room 204"
}
```

**Response 201:** Section object.

---

### POST /admin/registration-rounds
Create a registration round for a term.

**Request:**
```json
{ "term_id": "trm_001", "opens_at": "2026-01-01T08:00:00Z", "closes_at": "2026-01-10T23:59:59Z" }
```

**Response 201:** RegistrationRound object.
**Response 422:** `opens_at` not before `closes_at`, or dates outside term window.

---

### POST /admin/users
Create a user account.

**Request:**
```json
{
  "username": "EMP00045",
  "password": "TempP@ss1234",
  "role": "INSTRUCTOR",
  "reports_to": "usr_mgr01"
}
```

**Response 201:** User object (no password hash returned).

---

### PATCH /admin/users/{user_id}/deactivate
Deactivate a user; immediately revokes all active sessions.

**Response 204:** Success.

---

### GET /admin/audit-log
Query the immutable audit log.

**Query params:** `actor_id`, `entity_type`, `from_date`, `to_date`, `page`, `page_size`

**Auth required:** `ADMIN` role.

**Response 200:** Paginated list of audit entries.
```json
{
  "items": [{
    "log_id": "alog_001",
    "actor_id": "usr_admin01",
    "action": "ENROLLMENT_DROP",
    "entity_type": "Enrollment",
    "entity_id": "enr_123",
    "before_hash": "sha256:abc...",
    "after_hash": "sha256:def...",
    "timestamp": "2026-04-02T09:00:00Z"
  }],
  "total": 500, "page": 1, "page_size": 20
}
```

---

## 3. Course Discovery — `/courses`

**RBAC:** Any authenticated user.

### GET /courses
List available courses with optional filtering.

**Query params:** `org_id`, `term_id`, `search` (title/code prefix), `page`, `page_size`

**Response 200:** Paginated course list with section availability counts.

---

### GET /courses/{course_id}
Get full course detail including prerequisite list and available sections.

**Response 200:** Course + sections array.

---

### GET /courses/{course_id}/sections/{section_id}/eligibility
Check whether the current student is eligible to enroll in a section.

**Response 200:**
```json
{
  "eligible": false,
  "reasons": [
    { "type": "MISSING_PREREQUISITE", "course_code": "CS201" },
    { "type": "REGISTRATION_ROUND_CLOSED" }
  ]
}
```

---

## 4. Registration — `/registration`

### POST /registration/enroll
Enroll the authenticated student in a section.

**Headers:** `Idempotency-Key: <uuid>`

**Request:**
```json
{ "section_id": "sec_042" }
```

**Response 201:** `{ "enrollment_id": "enr_001", "status": "ENROLLED" }`
**Response 409:** Section full → `{ "code": 409, "msg": "Section at capacity", "waitlist_available": true }`
**Response 409:** Round closed.
**Response 422:** Missing prerequisite.
**Response 200:** Duplicate idempotency key → cached original response.

---

### POST /registration/waitlist
Join the waitlist for a full section.

**Headers:** `Idempotency-Key: <uuid>`

**Request:**
```json
{ "section_id": "sec_042" }
```

**Response 201:** `{ "waitlist_id": "wl_007", "position": 3, "queued_at": "2026-04-02T10:00:00Z" }`

---

### POST /registration/drop
Drop an enrollment.

**Headers:** `Idempotency-Key: <uuid>`

**Request:**
```json
{ "enrollment_id": "enr_001" }
```

**Response 200:** `{ "enrollment_id": "enr_001", "status": "DROPPED" }`

---

### GET /registration/status
Get the current student's active enrollments and waitlist positions.

**Response 200:**
```json
{
  "enrollments": [{ "enrollment_id": "enr_001", "section_id": "sec_042", "status": "ENROLLED" }],
  "waitlist": [{ "waitlist_id": "wl_007", "section_id": "sec_099", "position": 2 }]
}
```

---

### GET /registration/history
Enrollment change history for the current student.

**Query params:** `term_id`, `page`, `page_size`

**Response 200:** Paginated list of enrollment state transitions.

---

## 5. Reviews / Scoring — `/reviews`

### POST /reviews/rounds
Create a review round. **RBAC:** `INSTRUCTOR` or `ADMIN`.

**Request:**
```json
{
  "section_id": "sec_042",
  "visibility_mode": "blind",
  "scoring_form_id": "form_01",
  "opens_at": "2026-04-10T08:00:00Z",
  "closes_at": "2026-04-20T23:59:59Z"
}
```

**Response 201:** ReviewRound object.

---

### POST /reviews/rounds/{round_id}/assign
Assign a reviewer to a submission. **RBAC:** `INSTRUCTOR` or `ADMIN`.

**Request:**
```json
{ "reviewer_id": "usr_rev01", "submission_id": "sub_001", "assignment_type": "manual" }
```

**Response 201:** ReviewerAssignment object.
**Response 409:** `{ "code": 409, "msg": "Conflict of interest detected", "reason": "SAME_SECTION" }`

---

### POST /reviews/rounds/{round_id}/assign/auto
Rules-based automatic assignment for all unassigned submissions in the round.

**Response 202:** `{ "assigned": 12, "skipped_coi": 2 }`

---

### GET /reviews/assignments/my
Fetch submissions assigned to the authenticated reviewer (identity filtered by visibility mode).

**Response 200:** List of assigned submissions with sanitised metadata.

---

### POST /reviews/scores
Submit scores for a reviewer assignment.

**Request:**
```json
{
  "assignment_id": "asn_001",
  "scores": [
    { "criterion_id": "crit_01", "value": 4.5, "comment": "Strong methodology" },
    { "criterion_id": "crit_02", "value": 2.0, "comment": "Needs improvement" }
  ]
}
```

**Response 201:** `{ "score_ids": [...], "outlier_flags": [{ "criterion_id": "crit_02", "flag_id": "flg_001", "deviation": 2.3 }] }`
**Response 422:** Score out of criterion range.

---

### GET /reviews/rounds/{round_id}/flags
List unresolved outlier flags for a round. **RBAC:** `INSTRUCTOR`, `ADMIN`.

**Response 200:** Paginated list of OutlierFlag objects.

---

### PATCH /reviews/flags/{flag_id}/resolve
Resolve or dismiss an outlier flag. **RBAC:** `INSTRUCTOR`, `ADMIN`.

**Request:**
```json
{ "resolution": "accepted", "note": "Deviation justified by context" }
```

**Response 200:** Updated flag.

---

### POST /reviews/rechecks
Request a re-review of a submission. **RBAC:** `STUDENT`, `INSTRUCTOR`.

**Request:**
```json
{ "submission_id": "sub_001", "round_id": "rnd_001", "reason": "Scoring discrepancy in criterion 2" }
```

**Response 201:** RecheckRequest object.

---

### POST /reviews/rounds/{round_id}/close
Close the round and finalize scores. **RBAC:** `INSTRUCTOR`, `ADMIN`.

**Response 200:** `{ "status": "CLOSED", "aggregate_scores": [...] }`
**Response 409:** `{ "code": 409, "msg": "Unresolved outlier flags", "flag_ids": ["flg_001"] }`

---

### GET /reviews/rounds/{round_id}/export
Export scores and comments as structured JSON. **RBAC:** `INSTRUCTOR`, `ADMIN`.

**Query params:** `format=json|csv`

**Response 200:** File download or JSON body with full score and comment records.

---

## 6. Finance / Settlement — `/finance`

**RBAC:** `FINANCE_CLERK` or `ADMIN` for write operations. Students can read their own ledger.

### GET /finance/accounts/{student_id}
Get a student's ledger account summary.

**Response 200:**
```json
{ "account_id": "acc_001", "student_id": "usr_stu01", "balance": 1500.00, "overdue_since": null }
```

---

### POST /finance/payments
Record a payment. **RBAC:** `FINANCE_CLERK`.

**Request:**
```json
{
  "account_id": "acc_001",
  "amount": 500.00,
  "type": "PREPAYMENT",
  "instrument": "CHECK",
  "reference": "CHK-2026-0445"
}
```

**Response 201:** LedgerEntry object.

---

### POST /finance/refunds
Issue a refund (creates a reversing ledger entry).

**Request:**
```json
{ "original_entry_id": "led_001", "amount": 250.00, "reason": "Course dropped" }
```

**Response 201:** Reversal LedgerEntry object.
**Response 422:** Refund amount exceeds original entry.

---

### GET /finance/arrears
List accounts with overdue balances. **RBAC:** `FINANCE_CLERK`, `ADMIN`.

**Query params:** `min_overdue_days`, `page`, `page_size`

**Response 200:** Paginated list of overdue accounts with `balance_due` and `overdue_since`.

---

### POST /finance/reconciliation/import
Import a bank statement CSV file for reconciliation. **RBAC:** `FINANCE_CLERK`.

**Content-Type:** `multipart/form-data`

**Form fields:** `file` (CSV), `statement_date` (ISO 8601 date)

**CSV required headers:** `date,reference,amount,type`

**Response 202:** `{ "import_id": "imp_001", "rows_accepted": 45, "rows_rejected": 2, "errors": [...] }`

---

### GET /finance/reconciliation/{import_id}/report
Retrieve the reconciliation report for an import.

**Response 200:** Report with matched/unmatched lines and discrepancy details.

---

## 7. Messaging — `/messaging`

### GET /messaging/notifications
List notifications for the current user.

**Query params:** `status=unread|all`, `page`, `page_size`

**Response 200:**
```json
{
  "unread_count": 3,
  "items": [{
    "notification_id": "ntf_001",
    "type": "DEADLINE_24H",
    "payload": { "round_id": "rnd_001", "closes_at": "2026-04-11T08:00:00Z" },
    "status": "delivered",
    "delivered_at": "2026-04-10T08:00:01Z"
  }]
}
```

---

### PATCH /messaging/notifications/{notification_id}/read
Mark a notification as read.

**Response 200:** `{ "notification_id": "ntf_001", "status": "read", "read_at": "2026-04-10T09:15:00Z" }`

---

## 8. Data Quality — `/data-quality`

**RBAC:** `ADMIN`.

### GET /data-quality/quarantine
List quarantined (rejected) record writes.

**Query params:** `entity_type`, `from_date`, `to_date`, `page`, `page_size`

**Response 200:** Paginated quarantine entries with rejection reasons.

---

### PATCH /data-quality/quarantine/{entry_id}/resolve
Accept or discard a quarantined record.

**Request:**
```json
{ "action": "accept" }
```

**Response 200:** Updated quarantine entry.

---

### GET /data-quality/report
Quality score summary by entity type.

**Response 200:**
```json
{
  "by_entity": [
    { "entity_type": "User", "avg_quality_score": 94.2, "quarantine_count": 3 }
  ],
  "generated_at": "2026-04-02T12:00:00Z"
}
```

---

## 9. Integrations — `/integrations`

Authentication for all integration endpoints uses HMAC-SHA256 in addition to a session or client credential.

**Required headers:**
- `X-Client-ID: <client_id>`
- `X-Signature-256: sha256=<hex_digest>` (HMAC of raw request body with client secret)
- `X-Nonce: <random_uuid>`
- `X-Timestamp: <ISO 8601 UTC>` (rejected if > 5 minutes old)

### POST /integrations/clients
Register a new integration client. **RBAC:** `ADMIN`.

**Request:** `{ "name": "SIS Connector", "rate_limit_rpm": 120, "allowed_scopes": ["sis:read", "sis:write"] }`

**Response 201:** `{ "client_id": "cli_001", "secret_plaintext": "<shown_once>" }`

---

### POST /integrations/sis/students
SIS pushes student records for sync.

**Request:** Array of student objects matching the User schema.

**Response 200:** `{ "synced": 50, "skipped": 2, "errors": [...] }`
**Response 401:** Invalid HMAC signature.
**Response 409:** Nonce already used.
**Response 429:** Rate limit exceeded. `Retry-After` header included.

---

### POST /integrations/qbank/forms
Question bank pushes scoring form templates.

**Request:** Array of ScoringForm objects.

**Response 200:** `{ "imported": 5, "skipped": 1 }`
