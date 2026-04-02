# questions.md

Ambiguities identified during prompt analysis, resolved before implementation began. Each entry follows the required format: **Question → Assumption → Solution**.

---

## Q1: Waitlist Priority Order

**Question:** The prompt states waitlists "backfill automatically in priority order" but does not define what constitutes priority — is it time-of-request (FIFO), GPA, or a configurable weighting?

**Assumption:** Priority is determined by the timestamp at which the student joined the waitlist (FIFO), which is the fairest and most operationally transparent default for an academic environment.

**Solution:** Waitlist entries record `queued_at` as a UTC timestamp. When a seat opens, the system selects the next eligible student by `queued_at ASC`, checks current prerequisite and financial-hold status, and promotes them. Administrators may not reorder the waitlist manually; the order is immutable after the student joins.

---

## Q2: Conflict-of-Interest Scope for Reviewers

**Question:** The prompt says a reviewer cannot review a student "from the same section or reporting line" but does not specify how deep the reporting line goes or who defines it.

**Assumption:** "Reporting line" means a direct supervisory relationship one level up or down (e.g., the reviewer is the student's academic advisor, or the student is a teaching assistant working under the reviewer). Organisational hierarchy is maintained by the System Administrator when creating user accounts.

**Solution:** A `reports_to` field on the user record captures the direct supervisor. The conflict-of-interest check at reviewer assignment time compares the reviewer's `user_id` against the student's `section_id` enrollments and the `reports_to` chain (immediate level only). Assignments that would violate this constraint are blocked with a structured error; forced overrides require an escalated RBAC role and produce an audit log entry.

---

## Q3: Blind vs. Semi-Blind Review Identity Visibility

**Question:** "Blind" and "semi-blind" review modes are mentioned but the exact information visible to each party in each mode is not specified.

**Assumption:** In **blind** mode, the reviewer sees no identifying information about the student (no name, no ID, no section). In **semi-blind** mode, the reviewer sees the student's section but not their name or personal ID. Instructors configuring a review round choose the mode per round, not per reviewer.

**Solution:** The review round record stores a `visibility_mode` enum (`blind | semi_blind | open`). The Scoring Workbench API filters the submission payload server-side before returning it to the reviewer: blind strips all PII, semi-blind strips name/ID but includes the section code, open returns full information.

---

## Q4: Outlier Handling — Flag vs. Block

**Question:** The prompt specifies a flag when a score deviates ≥ 2.0 points from the median on a 5-point scale, but it is unclear whether the submission is blocked or simply flagged for human follow-up.

**Assumption:** The score is accepted but flagged; it is not automatically rejected. A human reviewer or the round coordinator must explicitly resolve (accept or override) the flag before the round can be closed.

**Solution:** On score submission, the system computes the rolling median of scores for that criterion across reviewers in the same round. If `abs(submitted_score - median) >= 2.0`, the entry is marked `flagged = true` and a `OutlierFlag` record is written. The round-close endpoint fails if any unresolved `OutlierFlag` records exist; a coordinator with the appropriate RBAC grant may dismiss or escalate each flag individually.

---

## Q5: Idempotency Key Scope and Lifespan

**Question:** The prompt says the idempotency key is "unique per actor+operation for 24 hours" but does not clarify whether the key is a client-provided value or a server-generated nonce.

**Assumption:** The idempotency key is provided by the client in a request header (`Idempotency-Key`). This is the industry-standard pattern and allows clients to safely retry requests without guessing.

**Solution:** Clients include `Idempotency-Key: <uuid>` in add/drop request headers. The server stores `(actor_id, operation_code, idempotency_key, result_payload, created_at)` in a deduplications table with a 24-hour TTL index. A duplicate key within 24 hours returns the stored result immediately without re-executing the operation. Expired keys are cleaned by a scheduled background task.

---

## Q6: Finance — Scope of Reconciliation Input

**Question:** "Reconciliation compares ledger totals to imported local bank statement files" but the format of that file is not specified.

**Assumption:** Given the air-gapped constraint, the import format is a CSV following a simple header schema (`date, reference, amount, type`) consistent with common local banking exports. More complex formats (ISO 20022, OFX) are out of scope unless a future integration is added.

**Solution:** The Finance API exposes a `POST /finance/reconciliation/import` endpoint that accepts a multipart `CSV` file upload. It parses the file, validates headers and row schema, writes entries to a `bank_statement_line` table, then runs a reconciliation job comparing each line to the internal ledger by reference number and date ± 1 day. Discrepancies are flagged in a reconciliation report accessible to Finance Clerks.

---

## Q7: Late Fee — "After Grace Period" Calculation Base

**Question:** The 10-day grace period and 1.5% monthly late fee are described, but it is unclear whether the fee is applied to the full original balance or only the overdue portion, and whether it compounds.

**Assumption:** The fee is applied to the outstanding balance at the time the grace period expires. It does not compound — it is recalculated fresh at each month-end cycle against the then-current overdue balance.

**Solution:** A scheduled month-end job queries all ledger accounts where `balance_due > 0` and `overdue_since` is more than 10 days past. It calculates `fee = current_overdue_balance * 0.015` and posts a `LATE_FEE` ledger entry with a structured description including the computation date and rate. The rate and grace days are stored as configuration parameters editable by System Administrators.

---

## Q8: In-App Notification Delivery Tracking

**Question:** The prompt specifies "delivery/read tracking logs" for in-app notifications but does not define what "delivered" means in an offline-capable system.

**Assumption:** "Delivered" means the notification record was successfully written to the database and is available for the recipient to fetch on next login. "Read" means the user's client explicitly called the mark-read endpoint. There is no push delivery layer.

**Solution:** Each `Notification` record has `status` (`pending | delivered | read`) and `delivered_at`, `read_at` timestamps. Status transitions from `pending` to `delivered` when the record is successfully persisted. The client marks messages `read` by calling `PATCH /messaging/notifications/{id}/read`. All status transitions are written to a `notification_log` table for audit purposes.

---

## Q9: HMAC Signature Verification — Algorithm and Header Location

**Question:** Open API integrations use "HMAC signature verification" but the algorithm (SHA-256, SHA-512) and header conventions are not specified.

**Assumption:** `HMAC-SHA256` is used, consistent with the de facto standard for webhook and local API authentication. The signature is passed in the `X-Signature-256` header as `sha256=<hex_digest>`, mirroring the GitHub webhook convention which is widely understood.

**Solution:** The integration layer validates incoming requests by recomputing `HMAC-SHA256(secret_key, raw_request_body)` and comparing to the header value using a constant-time comparison. Mismatches return `401 Unauthorized`. Per-client secrets are stored hashed in the database; the plaintext is shown once at client registration time via a one-time reveal endpoint. Replay protection checks the `X-Nonce` header against a 5-minute in-memory nonce cache with a database fallback.

---

## Q10: Session Token Storage and Revocation Propagation

**Question:** The prompt states sessions expire after 8 hours idle and 24 hours absolute, and are revoked on deactivation, but does not specify whether tokens are stateless (JWT) or stateful (DB-stored).

**Assumption:** Stateful server-side sessions are used. Given the air-gapped and security-critical environment, stateless JWTs make immediate revocation difficult; a database-backed session store enables instant revocation on deactivation without waiting for token expiry.

**Solution:** On login, the server creates a session record (`session_id`, `user_id`, `created_at`, `last_active_at`, `absolute_expires_at`, `revoked`). The client receives an opaque session token (random 256-bit value). Each authenticated request looks up the session, checks `revoked = false`, `last_active_at > now - 8h`, and `absolute_expires_at > now`, then updates `last_active_at`. Deactivating a user sets `revoked = true` on all their active sessions immediately.
