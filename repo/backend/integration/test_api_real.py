"""
Real HTTP integration tests – comprehensive endpoint coverage.

Every test in this module hits the live Dockerised CEMS API over the network.
There is NO TestClient, NO dependency-injection override, and NO SQLite substitute.
All state is created via the API and cleaned up in finally-blocks.

Run via:  ./run_tests.sh   (or docker compose exec api pytest integration/ -v)

Coverage target: raise true no-mock endpoint coverage from ~27 % to ≥ 60 %.
Together with test_api_external.py this file covers 55+ of the 82 endpoints.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uid() -> str:
    """Eight-char hex suffix – prevents name collisions across runs."""
    return uuid.uuid4().hex[:8]


def _cleanup(base_url: str, path: str, res_id: int | str | None, headers: dict) -> None:
    """Assert-aware teardown DELETE.

    Accepts 200 (deleted) and 404 (already gone – test may have deleted it
    intentionally).  Any other status is surfaced as a test failure.
    """
    if res_id is None:
        return
    r = httpx.delete(
        f"{base_url}/api/v1/admin/{path}/{res_id}", headers=headers, timeout=10
    )
    assert r.status_code in (200, 404), (
        f"Unexpected {r.status_code} cleaning up /admin/{path}/{res_id}: {r.text[:200]}"
    )


def _login_as(base_url: str, username: str, password: str) -> dict[str, str]:
    r = httpx.post(
        f"{base_url}/api/v1/auth/login",
        json={"username": username, "password": password},
        timeout=10,
    )
    assert r.status_code == 200, f"Login failed for {username}: {r.status_code} {r.text[:200]}"
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _sign_hmac(
    secret: str, method: str, path: str, timestamp: str, nonce: str, body: bytes
) -> str:
    body_hash = hashlib.sha256(body).hexdigest()
    canonical = f"{method.upper()}\n{path}\n{timestamp}\n{nonce}\n{body_hash}"
    return hmac.new(
        secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _signed_headers(
    secret: str, client_id: str, path: str, body: bytes, nonce: str
) -> dict:
    ts = str(int(datetime.now(timezone.utc).timestamp()))
    return {
        "X-Client-ID": client_id,
        "X-Signature-256": _sign_hmac(secret, "POST", path, ts, nonce, body),
        "X-Nonce": nonce,
        "X-Timestamp": ts,
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# 1. Auth – password change + bootstrap rejection
# ---------------------------------------------------------------------------


def test_password_change_lifecycle(base_url: str, auth_headers: dict) -> None:
    """POST /auth/password/change: old cred rejected, new cred accepted."""
    uid = _uid()
    username = f"pwc_{uid}"
    old_pw, new_pw = "OldPass@2026!", "NewPass@2026!"
    user_id = None
    try:
        create = httpx.post(
            f"{base_url}/api/v1/admin/users",
            json={"username": username, "password": old_pw, "role": "STUDENT", "is_active": True},
            headers=auth_headers,
            timeout=10,
        )
        assert create.status_code == 200, create.text
        user_id = create.json()["id"]

        user_hdrs = _login_as(base_url, username, old_pw)

        change = httpx.post(
            f"{base_url}/api/v1/auth/password/change",
            json={"current_password": old_pw, "new_password": new_pw},
            headers=user_hdrs,
            timeout=10,
        )
        assert change.status_code == 200, change.text

        old_attempt = httpx.post(
            f"{base_url}/api/v1/auth/login",
            json={"username": username, "password": old_pw},
            timeout=5,
        )
        assert old_attempt.status_code == 401

        new_attempt = httpx.post(
            f"{base_url}/api/v1/auth/login",
            json={"username": username, "password": new_pw},
            timeout=5,
        )
        assert new_attempt.status_code == 200
    finally:
        _cleanup(base_url, "users", user_id, auth_headers)


def test_bootstrap_admin_rejected_after_initial_setup(base_url: str) -> None:
    """POST /auth/bootstrap-admin returns 409 (admin exists) or auth-error on repeat call."""
    r = httpx.post(
        f"{base_url}/api/v1/auth/bootstrap-admin",
        json={
            "username": "any_user",
            "password": "AnyPass@2026!",
            "bootstrap_token": "integration-test-bootstrap-2026",
        },
        timeout=10,
    )
    # 409 = admin already exists; 401/403 = token mismatch – never 200 after initial bootstrap
    assert r.status_code in (409, 401, 403), (
        f"Expected 409/401/403 but got {r.status_code}: {r.text[:200]}"
    )


# ---------------------------------------------------------------------------
# 2. Admin – terms list/update, rounds list/update, users list/update
# ---------------------------------------------------------------------------


def test_admin_terms_list_and_update(base_url: str, auth_headers: dict) -> None:
    """GET /admin/terms and PUT /admin/terms/{id}."""
    uid = _uid()
    org_id = term_id = term2_id = None
    try:
        org = httpx.post(
            f"{base_url}/api/v1/admin/organizations",
            json={"name": f"TermsOrg {uid}", "code": f"TR{uid[:6].upper()}", "is_active": True},
            headers=auth_headers,
            timeout=10,
        )
        assert org.status_code == 200, org.text
        org_id = org.json()["id"]

        t1 = httpx.post(
            f"{base_url}/api/v1/admin/terms",
            json={
                "organization_id": org_id,
                "name": f"Fall {uid}",
                "starts_on": "2026-09-01",
                "ends_on": "2026-12-20",
                "is_active": True,
            },
            headers=auth_headers,
            timeout=10,
        )
        assert t1.status_code == 200, t1.text
        term_id = t1.json()["id"]

        t2 = httpx.post(
            f"{base_url}/api/v1/admin/terms",
            json={
                "organization_id": org_id,
                "name": f"Spring {uid}",
                "starts_on": "2027-01-15",
                "ends_on": "2027-05-15",
                "is_active": False,
            },
            headers=auth_headers,
            timeout=10,
        )
        assert t2.status_code == 200, t2.text
        term2_id = t2.json()["id"]

        # GET /admin/terms
        listing = httpx.get(
            f"{base_url}/api/v1/admin/terms", headers=auth_headers, timeout=10
        )
        assert listing.status_code == 200, listing.text
        ids_in_list = [t["id"] for t in listing.json()]
        assert term_id in ids_in_list
        assert term2_id in ids_in_list
        term_data = next(t for t in listing.json() if t["id"] == term_id)
        assert term_data["organization_id"] == org_id
        assert term_data["is_active"] is True
        assert term_data["starts_on"] == "2026-09-01"

        # PUT /admin/terms/{id}
        update = httpx.put(
            f"{base_url}/api/v1/admin/terms/{term_id}",
            json={
                "organization_id": org_id,
                "name": f"Fall {uid} Revised",
                "starts_on": "2026-09-01",
                "ends_on": "2026-12-31",
                "is_active": True,
            },
            headers=auth_headers,
            timeout=10,
        )
        assert update.status_code == 200, update.text
        assert update.json()["name"].endswith("Revised")
        assert update.json()["ends_on"] == "2026-12-31"
    finally:
        _cleanup(base_url, "terms", term2_id, auth_headers)
        _cleanup(base_url, "terms", term_id, auth_headers)
        _cleanup(base_url, "organizations", org_id, auth_headers)


def test_admin_registration_rounds_list_and_update(base_url: str, auth_headers: dict) -> None:
    """GET /admin/registration-rounds and PUT /admin/registration-rounds/{id}."""
    uid = _uid()
    now = datetime.now(timezone.utc)
    org_id = term_id = round_id = None
    try:
        org = httpx.post(
            f"{base_url}/api/v1/admin/organizations",
            json={"name": f"RndOrg {uid}", "code": f"RO{uid[:6].upper()}", "is_active": True},
            headers=auth_headers,
            timeout=10,
        )
        assert org.status_code == 200
        org_id = org.json()["id"]

        term = httpx.post(
            f"{base_url}/api/v1/admin/terms",
            json={
                "organization_id": org_id,
                "name": f"Term {uid}",
                "starts_on": "2026-09-01",
                "ends_on": "2026-12-20",
                "is_active": True,
            },
            headers=auth_headers,
            timeout=10,
        )
        assert term.status_code == 200
        term_id = term.json()["id"]

        create_rnd = httpx.post(
            f"{base_url}/api/v1/admin/registration-rounds",
            json={
                "term_id": term_id,
                "name": f"Round {uid}",
                "starts_at": (now - timedelta(hours=1)).isoformat(),
                "ends_at": (now + timedelta(hours=3)).isoformat(),
                "is_active": True,
            },
            headers=auth_headers,
            timeout=10,
        )
        assert create_rnd.status_code == 200
        round_id = create_rnd.json()["id"]

        # GET /admin/registration-rounds
        listing = httpx.get(
            f"{base_url}/api/v1/admin/registration-rounds",
            headers=auth_headers,
            timeout=10,
        )
        assert listing.status_code == 200
        assert any(r["id"] == round_id for r in listing.json())

        # PUT /admin/registration-rounds/{id}
        upd = httpx.put(
            f"{base_url}/api/v1/admin/registration-rounds/{round_id}",
            json={
                "term_id": term_id,
                "name": f"Round {uid} v2",
                "starts_at": (now - timedelta(hours=1)).isoformat(),
                "ends_at": (now + timedelta(hours=2)).isoformat(),
                "is_active": True,
            },
            headers=auth_headers,
            timeout=10,
        )
        assert upd.status_code == 200
        assert upd.json()["name"].endswith("v2")
    finally:
        _cleanup(base_url, "registration-rounds", round_id, auth_headers)
        _cleanup(base_url, "terms", term_id, auth_headers)
        _cleanup(base_url, "organizations", org_id, auth_headers)


def test_admin_users_list_and_update(base_url: str, auth_headers: dict) -> None:
    """GET /admin/users and PUT /admin/users/{id}."""
    uid = _uid()
    user_id = None
    try:
        create = httpx.post(
            f"{base_url}/api/v1/admin/users",
            json={
                "username": f"usrmgmt_{uid}",
                "password": "UserMgmt@2026!",
                "role": "REVIEWER",
                "is_active": True,
            },
            headers=auth_headers,
            timeout=10,
        )
        assert create.status_code == 200, create.text
        user_id = create.json()["id"]
        assert create.json()["role"] == "REVIEWER"

        # GET /admin/users
        listing = httpx.get(
            f"{base_url}/api/v1/admin/users", headers=auth_headers, timeout=10
        )
        assert listing.status_code == 200
        assert any(u["id"] == user_id for u in listing.json())

        # PUT /admin/users/{id}
        update = httpx.put(
            f"{base_url}/api/v1/admin/users/{user_id}",
            json={"role": "INSTRUCTOR"},
            headers=auth_headers,
            timeout=10,
        )
        assert update.status_code == 200
        assert update.json()["role"] == "INSTRUCTOR"
    finally:
        _cleanup(base_url, "users", user_id, auth_headers)


# ---------------------------------------------------------------------------
# 3. Admin – audit log + scope grants + catalog updates
# ---------------------------------------------------------------------------


def test_admin_audit_log_and_retention(base_url: str, auth_headers: dict) -> None:
    """GET /admin/audit-log and POST /admin/audit-log/retention."""
    uid = _uid()
    org_id = None
    try:
        org = httpx.post(
            f"{base_url}/api/v1/admin/organizations",
            json={"name": f"AuditOrg {uid}", "code": f"AU{uid[:6].upper()}", "is_active": True},
            headers=auth_headers,
            timeout=10,
        )
        assert org.status_code == 200
        org_id = org.json()["id"]

        # GET /admin/audit-log
        logs = httpx.get(
            f"{base_url}/api/v1/admin/audit-log", headers=auth_headers, timeout=10
        )
        assert logs.status_code == 200
        log_list = logs.json()
        assert isinstance(log_list, list)
        assert len(log_list) >= 1
        assert all("action" in entry and "entity_name" in entry for entry in log_list[:3])

        # POST /admin/audit-log/retention
        retention = httpx.post(
            f"{base_url}/api/v1/admin/audit-log/retention",
            headers=auth_headers,
            timeout=30,
        )
        assert retention.status_code == 200
        result = retention.json()
        assert "archived_count" in result
        assert "purged_count" in result
        assert isinstance(result["archived_count"], int)
    finally:
        _cleanup(base_url, "organizations", org_id, auth_headers)


def test_admin_scope_grants_create_list_delete(base_url: str, auth_headers: dict) -> None:
    """POST /admin/scope-grants, GET /admin/scope-grants, DELETE /admin/scope-grants/{id}."""
    uid = _uid()
    org_id = user_id = scope_id = None
    try:
        org = httpx.post(
            f"{base_url}/api/v1/admin/organizations",
            json={"name": f"ScopeOrg {uid}", "code": f"SG{uid[:6].upper()}", "is_active": True},
            headers=auth_headers,
            timeout=10,
        )
        assert org.status_code == 200
        org_id = org.json()["id"]

        user = httpx.post(
            f"{base_url}/api/v1/admin/users",
            json={
                "username": f"scopeusr_{uid}",
                "password": "ScopeUsr@2026!",
                "role": "INSTRUCTOR",
                "is_active": True,
            },
            headers=auth_headers,
            timeout=10,
        )
        assert user.status_code == 200, user.text
        user_id = user.json()["id"]

        # POST /admin/scope-grants
        scope = httpx.post(
            f"{base_url}/api/v1/admin/scope-grants",
            json={"user_id": user_id, "scope_type": "ORGANIZATION", "scope_id": org_id},
            headers=auth_headers,
            timeout=10,
        )
        assert scope.status_code == 200, scope.text
        scope_id = scope.json()["id"]
        assert scope.json()["user_id"] == user_id
        assert scope.json()["scope_type"] == "ORGANIZATION"

        # GET /admin/scope-grants
        listing = httpx.get(
            f"{base_url}/api/v1/admin/scope-grants?user_id={user_id}",
            headers=auth_headers,
            timeout=10,
        )
        assert listing.status_code == 200
        assert any(s["id"] == scope_id for s in listing.json())

        # DELETE /admin/scope-grants/{id}
        delete_scope = httpx.delete(
            f"{base_url}/api/v1/admin/scope-grants/{scope_id}",
            headers=auth_headers,
            timeout=10,
        )
        assert delete_scope.status_code == 200
        scope_id = None  # already deleted

        after_del = httpx.get(
            f"{base_url}/api/v1/admin/scope-grants?user_id={user_id}",
            headers=auth_headers,
            timeout=10,
        )
        assert after_del.status_code == 200
        assert len(after_del.json()) == 0
    finally:
        if scope_id is not None:
            _cleanup(base_url, "scope-grants", scope_id, auth_headers)
        _cleanup(base_url, "users", user_id, auth_headers)
        _cleanup(base_url, "organizations", org_id, auth_headers)


def test_admin_catalog_update_endpoints(base_url: str, auth_headers: dict) -> None:
    """PUT /admin/courses/{id} and PUT /admin/sections/{id}."""
    uid = _uid()
    org_id = term_id = course_id = section_id = None
    try:
        org = httpx.post(
            f"{base_url}/api/v1/admin/organizations",
            json={"name": f"UpdOrg {uid}", "code": f"UO{uid[:6].upper()}", "is_active": True},
            headers=auth_headers,
            timeout=10,
        )
        assert org.status_code == 200
        org_id = org.json()["id"]

        term = httpx.post(
            f"{base_url}/api/v1/admin/terms",
            json={
                "organization_id": org_id,
                "name": f"Term {uid}",
                "starts_on": "2026-09-01",
                "ends_on": "2026-12-20",
                "is_active": True,
            },
            headers=auth_headers,
            timeout=10,
        )
        assert term.status_code == 200
        term_id = term.json()["id"]

        course = httpx.post(
            f"{base_url}/api/v1/admin/courses",
            json={
                "organization_id": org_id,
                "code": f"UP{uid[:6].upper()}",
                "title": f"Update Course {uid}",
                "credits": 3,
                "prerequisites": [],
            },
            headers=auth_headers,
            timeout=10,
        )
        assert course.status_code == 200, course.text
        course_id = course.json()["id"]

        section = httpx.post(
            f"{base_url}/api/v1/admin/sections",
            json={
                "course_id": course_id,
                "term_id": term_id,
                "code": "A",
                "capacity": 25,
                "instructor_id": None,
            },
            headers=auth_headers,
            timeout=10,
        )
        assert section.status_code == 200
        section_id = section.json()["id"]

        # PUT /admin/courses/{id}
        course_upd = httpx.put(
            f"{base_url}/api/v1/admin/courses/{course_id}",
            json={
                "organization_id": org_id,
                "code": f"UP{uid[:6].upper()}",
                "title": f"Update Course {uid} v2",
                "credits": 4,
                "prerequisites": [],
            },
            headers=auth_headers,
            timeout=10,
        )
        assert course_upd.status_code == 200
        assert course_upd.json()["credits"] == 4
        assert course_upd.json()["title"].endswith("v2")

        # PUT /admin/sections/{id}
        section_upd = httpx.put(
            f"{base_url}/api/v1/admin/sections/{section_id}",
            json={
                "course_id": course_id,
                "term_id": term_id,
                "code": "B",
                "capacity": 40,
                "instructor_id": None,
            },
            headers=auth_headers,
            timeout=10,
        )
        assert section_upd.status_code == 200
        assert section_upd.json()["capacity"] == 40
        assert section_upd.json()["code"] == "B"
    finally:
        for res_id, path in [
            (section_id, "sections"),
            (course_id, "courses"),
            (term_id, "terms"),
            (org_id, "organizations"),
        ]:
            _cleanup(base_url, path, res_id, auth_headers)


# ---------------------------------------------------------------------------
# 4. Integration clients – create + rotate secret
# ---------------------------------------------------------------------------


def test_integration_client_create_and_rotate_secret(
    base_url: str, auth_headers: dict
) -> None:
    """POST /integrations/clients and POST /integrations/clients/{id}/rotate-secret."""
    uid = _uid()
    org_id = None
    try:
        org = httpx.post(
            f"{base_url}/api/v1/admin/organizations",
            json={"name": f"IntOrg {uid}", "code": f"IC{uid[:6].upper()}", "is_active": True},
            headers=auth_headers,
            timeout=10,
        )
        assert org.status_code == 200
        org_id = org.json()["id"]

        # POST /integrations/clients
        create = httpx.post(
            f"{base_url}/api/v1/integrations/clients",
            json={"name": f"Client {uid}", "organization_id": org_id, "rate_limit_rpm": 10},
            headers=auth_headers,
            timeout=10,
        )
        assert create.status_code == 200, create.text
        client_id = create.json()["client_id"]
        original_secret = create.json()["client_secret"]
        assert client_id.startswith("cli_")
        assert original_secret

        path = "/api/v1/integrations/qbank/forms"
        body = json.dumps(
            {
                "import_id": f"init-{uid}",
                "forms": [
                    {
                        "external_id": "F1",
                        "name": "Init Form",
                        "criteria": [{"name": "Q", "weight": 1, "min": 0, "max": 5}],
                    }
                ],
            }
        ).encode()
        ok = httpx.post(
            f"{base_url}{path}",
            data=body,
            headers=_signed_headers(original_secret, client_id, path, body, f"n-{uid}-0"),
            timeout=10,
        )
        assert ok.status_code == 200, ok.text

        # POST /integrations/clients/{client_id}/rotate-secret
        rotate = httpx.post(
            f"{base_url}/api/v1/integrations/clients/{client_id}/rotate-secret",
            headers=auth_headers,
            timeout=10,
        )
        assert rotate.status_code == 200, rotate.text
        assert rotate.json()["client_id"] == client_id
        new_secret = rotate.json()["client_secret"]
        assert new_secret != original_secret

        # Old secret rejected
        old_body = json.dumps(
            {
                "import_id": f"old-{uid}",
                "forms": [
                    {
                        "external_id": "F2",
                        "name": "Old Secret Form",
                        "criteria": [{"name": "Q", "weight": 1, "min": 0, "max": 5}],
                    }
                ],
            }
        ).encode()
        old_req = httpx.post(
            f"{base_url}{path}",
            data=old_body,
            headers=_signed_headers(original_secret, client_id, path, old_body, f"n-{uid}-1"),
            timeout=10,
        )
        assert old_req.status_code == 401

        # New secret accepted
        new_body = json.dumps(
            {
                "import_id": f"new-{uid}",
                "forms": [
                    {
                        "external_id": "F3",
                        "name": "New Secret Form",
                        "criteria": [{"name": "Q", "weight": 1, "min": 0, "max": 5}],
                    }
                ],
            }
        ).encode()
        new_req = httpx.post(
            f"{base_url}{path}",
            data=new_body,
            headers=_signed_headers(new_secret, client_id, path, new_body, f"n-{uid}-2"),
            timeout=10,
        )
        assert new_req.status_code == 200, new_req.text

        # Non-existent client → 404
        missing = httpx.post(
            f"{base_url}/api/v1/integrations/clients/nonexistent-xyz/rotate-secret",
            headers=auth_headers,
            timeout=10,
        )
        assert missing.status_code == 404
    finally:
        _cleanup(base_url, "organizations", org_id, auth_headers)


# ---------------------------------------------------------------------------
# 5. Messaging – dispatch, triggers, notifications
# ---------------------------------------------------------------------------


def test_messaging_dispatch_triggers_and_notification_lifecycle(
    base_url: str, auth_headers: dict
) -> None:
    """Covers dispatch, trigger config, process-due, notifications list, mark-read."""
    uid = _uid()
    student_id = None
    try:
        stu = httpx.post(
            f"{base_url}/api/v1/admin/users",
            json={
                "username": f"msgstu_{uid}",
                "password": "MsgStu@2026!",
                "role": "STUDENT",
                "is_active": True,
            },
            headers=auth_headers,
            timeout=10,
        )
        assert stu.status_code == 200, stu.text
        student_id = stu.json()["id"]

        # GET /messaging/triggers
        triggers = httpx.get(
            f"{base_url}/api/v1/messaging/triggers", headers=auth_headers, timeout=10
        )
        assert triggers.status_code == 200
        trigger_list = triggers.json()
        assert len(trigger_list) >= 1
        assert all("trigger_type" in t and "enabled" in t for t in trigger_list)

        # PUT /messaging/triggers/{trigger_type}
        upd_trigger = httpx.put(
            f"{base_url}/api/v1/messaging/triggers/DEADLINE_72H",
            json={"enabled": True, "lead_hours": 72},
            headers=auth_headers,
            timeout=10,
        )
        assert upd_trigger.status_code == 200
        assert upd_trigger.json()["trigger_type"] == "DEADLINE_72H"
        assert upd_trigger.json()["enabled"] is True

        # POST /messaging/dispatch
        dispatch = httpx.post(
            f"{base_url}/api/v1/messaging/dispatch",
            json={
                "trigger_type": "ASSIGNMENT_POSTED",
                "title": f"Notice {uid}",
                "message": f"Test notification {uid}",
                "recipient_ids": [student_id],
            },
            headers=auth_headers,
            timeout=10,
        )
        assert dispatch.status_code == 200, dispatch.text
        assert dispatch.json()["created"] >= 1

        # POST /messaging/triggers/process-due
        process = httpx.post(
            f"{base_url}/api/v1/messaging/triggers/process-due",
            headers=auth_headers,
            timeout=10,
        )
        assert process.status_code == 200
        assert "processed" in process.json()

        # GET /messaging/notifications (as student)
        stu_hdrs = _login_as(base_url, f"msgstu_{uid}", "MsgStu@2026!")
        notifs = httpx.get(
            f"{base_url}/api/v1/messaging/notifications",
            headers=stu_hdrs,
            timeout=10,
        )
        assert notifs.status_code == 200
        body = notifs.json()
        assert "unread_count" in body and "notifications" in body
        assert body["unread_count"] >= 1
        notif_id = next(
            n["id"] for n in body["notifications"] if n["title"] == f"Notice {uid}"
        )

        # PATCH /messaging/notifications/{id}/read
        mark = httpx.patch(
            f"{base_url}/api/v1/messaging/notifications/{notif_id}/read",
            headers=stu_hdrs,
            timeout=10,
        )
        assert mark.status_code == 200
        assert mark.json()["id"] == notif_id
        assert mark.json()["read"] is True

        # Verify count decreased
        after = httpx.get(
            f"{base_url}/api/v1/messaging/notifications",
            headers=stu_hdrs,
            timeout=10,
        )
        assert after.status_code == 200
        # At least the one we dispatched is now read
        read_notif = next(
            (n for n in after.json()["notifications"] if n["id"] == notif_id), None
        )
        assert read_notif is not None
        assert read_notif["read"] is True
    finally:
        _cleanup(base_url, "users", student_id, auth_headers)


# ---------------------------------------------------------------------------
# 6. Registration – course discovery, eligibility, enroll, status, history, roster, drop
# ---------------------------------------------------------------------------


def test_registration_full_workflow(base_url: str, auth_headers: dict) -> None:
    """
    Covers: GET /courses, GET /courses/{id}, eligibility, enroll,
    GET /registration/status, GET /registration/history, drop,
    GET /sections/{id}/roster, POST /sections/{id}/roster,
    DELETE /sections/{id}/roster/{student_id}.
    """
    uid = _uid()
    now = datetime.now(timezone.utc)
    org_id = term_id = course_id = section_id = round_id = student_id = None
    try:
        org = httpx.post(
            f"{base_url}/api/v1/admin/organizations",
            json={"name": f"RegOrg {uid}", "code": f"RG{uid[:6].upper()}", "is_active": True},
            headers=auth_headers,
            timeout=10,
        )
        assert org.status_code == 200
        org_id = org.json()["id"]

        term = httpx.post(
            f"{base_url}/api/v1/admin/terms",
            json={
                "organization_id": org_id,
                "name": f"Term {uid}",
                "starts_on": "2026-09-01",
                "ends_on": "2026-12-20",
                "is_active": True,
            },
            headers=auth_headers,
            timeout=10,
        )
        assert term.status_code == 200
        term_id = term.json()["id"]

        course = httpx.post(
            f"{base_url}/api/v1/admin/courses",
            json={
                "organization_id": org_id,
                "code": f"RC{uid[:6].upper()}",
                "title": f"Reg Course {uid}",
                "credits": 3,
                "prerequisites": [],
            },
            headers=auth_headers,
            timeout=10,
        )
        assert course.status_code == 200, course.text
        course_id = course.json()["id"]

        section = httpx.post(
            f"{base_url}/api/v1/admin/sections",
            json={
                "course_id": course_id,
                "term_id": term_id,
                "code": "A",
                "capacity": 30,
                "instructor_id": None,
            },
            headers=auth_headers,
            timeout=10,
        )
        assert section.status_code == 200
        section_id = section.json()["id"]

        reg_round = httpx.post(
            f"{base_url}/api/v1/admin/registration-rounds",
            json={
                "term_id": term_id,
                "name": f"Round {uid}",
                "starts_at": (now - timedelta(hours=1)).isoformat(),
                "ends_at": (now + timedelta(hours=3)).isoformat(),
                "is_active": True,
            },
            headers=auth_headers,
            timeout=10,
        )
        assert reg_round.status_code == 200
        round_id = reg_round.json()["id"]

        stu = httpx.post(
            f"{base_url}/api/v1/admin/users",
            json={
                "username": f"rstu_{uid}",
                "password": "RegStu@2026!",
                "role": "STUDENT",
                "is_active": True,
                "org_id": org_id,
            },
            headers=auth_headers,
            timeout=10,
        )
        assert stu.status_code == 200, stu.text
        student_id = stu.json()["id"]

        stu_hdrs = _login_as(base_url, f"rstu_{uid}", "RegStu@2026!")

        # GET /courses
        courses = httpx.get(
            f"{base_url}/api/v1/courses", headers=stu_hdrs, timeout=10
        )
        assert courses.status_code == 200
        assert course_id in [c["id"] for c in courses.json()]

        # GET /courses/{id}
        detail = httpx.get(
            f"{base_url}/api/v1/courses/{course_id}", headers=stu_hdrs, timeout=10
        )
        assert detail.status_code == 200
        assert detail.json()["code"] == f"RC{uid[:6].upper()}"

        # GET /courses/{id}/sections/{section_id}/eligibility
        elig = httpx.get(
            f"{base_url}/api/v1/courses/{course_id}/sections/{section_id}/eligibility",
            headers=stu_hdrs,
            timeout=10,
        )
        assert elig.status_code == 200
        assert elig.json()["eligible"] is True

        # GET /registration/status (initially empty for this student)
        status_before = httpx.get(
            f"{base_url}/api/v1/registration/status", headers=stu_hdrs, timeout=10
        )
        assert status_before.status_code == 200

        # POST /registration/enroll
        enroll = httpx.post(
            f"{base_url}/api/v1/registration/enroll",
            json={"section_id": section_id},
            headers={**stu_hdrs, "Idempotency-Key": f"enr-{uid}"},
            timeout=10,
        )
        assert enroll.status_code == 200, enroll.text
        assert enroll.json()["status"] in {"enrolled", "already_enrolled"}

        # GET /registration/status – now shows enrollment
        status_after = httpx.get(
            f"{base_url}/api/v1/registration/status", headers=stu_hdrs, timeout=10
        )
        assert status_after.status_code == 200
        active_section_ids = [e["section_id"] for e in status_after.json()]
        assert section_id in active_section_ids

        # GET /sections/{id}/roster (admin)
        roster = httpx.get(
            f"{base_url}/api/v1/sections/{section_id}/roster",
            headers=auth_headers,
            timeout=10,
        )
        assert roster.status_code == 200
        enrolled_ids = [r["student_id"] for r in roster.json()]
        assert student_id in enrolled_ids

        # POST /registration/drop
        drop = httpx.post(
            f"{base_url}/api/v1/registration/drop",
            json={"section_id": section_id},
            headers=stu_hdrs,
            timeout=10,
        )
        assert drop.status_code == 200, drop.text

        # GET /registration/history – shows the dropped record
        history = httpx.get(
            f"{base_url}/api/v1/registration/history", headers=stu_hdrs, timeout=10
        )
        assert history.status_code == 200
        assert isinstance(history.json(), list)

        # Admin: POST /sections/{id}/roster – re-add student
        add_roster = httpx.post(
            f"{base_url}/api/v1/sections/{section_id}/roster",
            json={"student_id": student_id},
            headers=auth_headers,
            timeout=10,
        )
        assert add_roster.status_code in (200, 409), add_roster.text

        # Admin: DELETE /sections/{id}/roster/{student_id}
        rm_roster = httpx.delete(
            f"{base_url}/api/v1/sections/{section_id}/roster/{student_id}",
            headers=auth_headers,
            timeout=10,
        )
        assert rm_roster.status_code in (200, 404), rm_roster.text
    finally:
        for res_id, path in [
            (student_id, "users"),
            (round_id, "registration-rounds"),
            (section_id, "sections"),
            (course_id, "courses"),
            (term_id, "terms"),
            (org_id, "organizations"),
        ]:
            _cleanup(base_url, path, res_id, auth_headers)


def test_registration_waitlist(base_url: str, auth_headers: dict) -> None:
    """POST /registration/waitlist on a capacity-1 section that is already full."""
    uid = _uid()
    now = datetime.now(timezone.utc)
    org_id = term_id = course_id = section_id = round_id = None
    stu1_id = stu2_id = None
    try:
        org = httpx.post(
            f"{base_url}/api/v1/admin/organizations",
            json={"name": f"WLOrg {uid}", "code": f"WL{uid[:6].upper()}", "is_active": True},
            headers=auth_headers,
            timeout=10,
        )
        assert org.status_code == 200
        org_id = org.json()["id"]

        term = httpx.post(
            f"{base_url}/api/v1/admin/terms",
            json={"organization_id": org_id, "name": f"Term {uid}", "starts_on": "2026-09-01", "ends_on": "2026-12-20", "is_active": True},
            headers=auth_headers,
            timeout=10,
        )
        assert term.status_code == 200
        term_id = term.json()["id"]

        course = httpx.post(
            f"{base_url}/api/v1/admin/courses",
            json={"organization_id": org_id, "code": f"WC{uid[:6].upper()}", "title": f"WL Course {uid}", "credits": 3, "prerequisites": []},
            headers=auth_headers,
            timeout=10,
        )
        assert course.status_code == 200, course.text
        course_id = course.json()["id"]

        section = httpx.post(
            f"{base_url}/api/v1/admin/sections",
            json={"course_id": course_id, "term_id": term_id, "code": "W", "capacity": 1, "instructor_id": None},
            headers=auth_headers,
            timeout=10,
        )
        assert section.status_code == 200
        section_id = section.json()["id"]

        reg_round = httpx.post(
            f"{base_url}/api/v1/admin/registration-rounds",
            json={"term_id": term_id, "name": f"WL Round {uid}", "starts_at": (now - timedelta(hours=1)).isoformat(), "ends_at": (now + timedelta(hours=3)).isoformat(), "is_active": True},
            headers=auth_headers,
            timeout=10,
        )
        assert reg_round.status_code == 200
        round_id = reg_round.json()["id"]

        s1 = httpx.post(
            f"{base_url}/api/v1/admin/users",
            json={"username": f"wls1_{uid}", "password": "WLStu@2026!", "role": "STUDENT", "is_active": True, "org_id": org_id},
            headers=auth_headers,
            timeout=10,
        )
        assert s1.status_code == 200, s1.text
        stu1_id = s1.json()["id"]

        s2 = httpx.post(
            f"{base_url}/api/v1/admin/users",
            json={"username": f"wls2_{uid}", "password": "WLStu@2026!", "role": "STUDENT", "is_active": True, "org_id": org_id},
            headers=auth_headers,
            timeout=10,
        )
        assert s2.status_code == 200, s2.text
        stu2_id = s2.json()["id"]

        stu1_hdrs = _login_as(base_url, f"wls1_{uid}", "WLStu@2026!")
        stu2_hdrs = _login_as(base_url, f"wls2_{uid}", "WLStu@2026!")

        # Student 1 fills the seat
        enr1 = httpx.post(
            f"{base_url}/api/v1/registration/enroll",
            json={"section_id": section_id},
            headers={**stu1_hdrs, "Idempotency-Key": f"wl-e1-{uid}"},
            timeout=10,
        )
        assert enr1.status_code == 200, enr1.text

        # Student 2 joins waitlist – POST /registration/waitlist
        wl = httpx.post(
            f"{base_url}/api/v1/registration/waitlist",
            json={"section_id": section_id},
            headers={**stu2_hdrs, "Idempotency-Key": f"wl-e2-{uid}"},
            timeout=10,
        )
        assert wl.status_code == 200, wl.text
        assert wl.json()["status"] in {"waitlisted", "already_waitlisted", "enrolled"}
    finally:
        for res_id, path in [
            (stu2_id, "users"),
            (stu1_id, "users"),
            (round_id, "registration-rounds"),
            (section_id, "sections"),
            (course_id, "courses"),
            (term_id, "terms"),
            (org_id, "organizations"),
        ]:
            _cleanup(base_url, path, res_id, auth_headers)


# ---------------------------------------------------------------------------
# 7. Finance – payments, prepayments, deposits, refunds, accounts, billing, arrears
# ---------------------------------------------------------------------------


def test_finance_payment_lifecycle(base_url: str, auth_headers: dict) -> None:
    """
    Admin (bypasses scope check) exercises all finance write endpoints
    plus GET /finance/accounts/{id} and GET /finance/arrears.
    """
    uid = _uid()
    today = date.today().isoformat()
    past_date = (date.today() - timedelta(days=20)).isoformat()
    student_id = None
    try:
        stu = httpx.post(
            f"{base_url}/api/v1/admin/users",
            json={
                "username": f"finstu_{uid}",
                "password": "FinStu@2026!",
                "role": "STUDENT",
                "is_active": True,
            },
            headers=auth_headers,
            timeout=10,
        )
        assert stu.status_code == 200, stu.text
        student_id = stu.json()["id"]

        # GET /finance/accounts/{student_id}
        account_empty = httpx.get(
            f"{base_url}/api/v1/finance/accounts/{student_id}",
            headers=auth_headers,
            timeout=10,
        )
        assert account_empty.status_code == 200
        assert account_empty.json()["student_id"] == student_id
        assert "balance" in account_empty.json()
        assert isinstance(account_empty.json()["entries"], list)

        # POST /finance/prepayments
        prepay = httpx.post(
            f"{base_url}/api/v1/finance/prepayments",
            json={
                "student_id": student_id,
                "amount": 500.0,
                "instrument": "CASH",
                "reference_id": f"pre-{uid}",
                "description": "Prepayment",
                "entry_date": today,
            },
            headers=auth_headers,
            timeout=10,
        )
        assert prepay.status_code == 200, prepay.text

        # POST /finance/deposits
        deposit = httpx.post(
            f"{base_url}/api/v1/finance/deposits",
            json={
                "student_id": student_id,
                "amount": 100.0,
                "instrument": "CHECK",
                "reference_id": f"dep-{uid}",
                "description": "Lab deposit",
                "entry_date": today,
            },
            headers=auth_headers,
            timeout=10,
        )
        assert deposit.status_code == 200, deposit.text

        # POST /finance/payments
        payment = httpx.post(
            f"{base_url}/api/v1/finance/payments",
            json={
                "student_id": student_id,
                "amount": 200.0,
                "instrument": "CASH",
                "reference_id": f"pay-{uid}",
                "description": "Tuition",
                "entry_date": today,
            },
            headers=auth_headers,
            timeout=10,
        )
        assert payment.status_code == 200, payment.text
        payment_id = payment.json()["id"]

        # POST /finance/refunds
        refund = httpx.post(
            f"{base_url}/api/v1/finance/refunds",
            json={
                "student_id": student_id,
                "amount": 50.0,
                "reference_entry_id": payment_id,
                "description": "Partial refund",
                "entry_date": today,
            },
            headers=auth_headers,
            timeout=10,
        )
        assert refund.status_code == 200, refund.text

        # GET /finance/accounts/{id} – verify ledger now has entries
        account_full = httpx.get(
            f"{base_url}/api/v1/finance/accounts/{student_id}",
            headers=auth_headers,
            timeout=10,
        )
        assert account_full.status_code == 200
        assert len(account_full.json()["entries"]) >= 4

        # POST /finance/month-end-billing
        billing = httpx.post(
            f"{base_url}/api/v1/finance/month-end-billing",
            json={
                "student_id": student_id,
                "amount": 900.0,
                "description": "Monthly tuition charge",
                "entry_date": past_date,
            },
            headers=auth_headers,
            timeout=10,
        )
        assert billing.status_code == 200, billing.text

        # GET /finance/arrears
        arrears = httpx.get(
            f"{base_url}/api/v1/finance/arrears", headers=auth_headers, timeout=10
        )
        assert arrears.status_code == 200
        assert isinstance(arrears.json(), list)
    finally:
        _cleanup(base_url, "users", student_id, auth_headers)


# ---------------------------------------------------------------------------
# 8. Data quality – quarantine + report
# ---------------------------------------------------------------------------


def test_data_quality_quarantine_and_report(base_url: str, auth_headers: dict) -> None:
    """Trigger a quarantine entry, list it, resolve it, then fetch report."""
    uid = _uid()
    org_id = quarantine_id = None
    try:
        org = httpx.post(
            f"{base_url}/api/v1/admin/organizations",
            json={"name": f"DQOrg {uid}", "code": f"DQ{uid[:6].upper()}", "is_active": True},
            headers=auth_headers,
            timeout=10,
        )
        assert org.status_code == 200
        org_id = org.json()["id"]

        # Submitting an invalid course triggers data-quality rejection + quarantine
        bad = httpx.post(
            f"{base_url}/api/v1/admin/courses",
            json={
                "organization_id": org_id,
                "code": "",
                "title": "",
                "credits": 0,
                "prerequisites": [],
            },
            headers=auth_headers,
            timeout=10,
        )
        assert bad.status_code == 422
        quarantine_id = bad.json()["detail"]["quarantine_id"]
        assert quarantine_id is not None

        # GET /data-quality/quarantine
        q_list = httpx.get(
            f"{base_url}/api/v1/data-quality/quarantine",
            headers=auth_headers,
            timeout=10,
        )
        assert q_list.status_code == 200
        assert any(e["id"] == quarantine_id for e in q_list.json())
        entry = next(e for e in q_list.json() if e["id"] == quarantine_id)
        assert entry["entity_type"] == "AdminCourseWrite"

        # PATCH /data-quality/quarantine/{id}/resolve
        resolve = httpx.patch(
            f"{base_url}/api/v1/data-quality/quarantine/{quarantine_id}/resolve",
            json={"resolution": "Rejected – validation failure"},
            headers=auth_headers,
            timeout=10,
        )
        assert resolve.status_code == 200

        # GET /data-quality/report
        report = httpx.get(
            f"{base_url}/api/v1/data-quality/report",
            headers=auth_headers,
            timeout=10,
        )
        assert report.status_code == 200
    finally:
        _cleanup(base_url, "organizations", org_id, auth_headers)


# ---------------------------------------------------------------------------
# 9. Reviews – forms, rounds, manual assignment, scores, outliers, close, export
# ---------------------------------------------------------------------------


def test_review_round_lifecycle(base_url: str, auth_headers: dict) -> None:
    """
    Full review workflow:
      forms → rounds → manual assignment → GET assignments →
      scores → outliers → close → export.
    """
    uid = _uid()
    now = datetime.now(timezone.utc)

    org_id = term_id = course_id = section_id = round_id = None
    inst_id = rev_id = stu_id = inst_scope_id = rev_scope_id = None

    try:
        # Catalog
        org = httpx.post(f"{base_url}/api/v1/admin/organizations", json={"name": f"RvOrg {uid}", "code": f"RV{uid[:6].upper()}", "is_active": True}, headers=auth_headers, timeout=10)
        assert org.status_code == 200
        org_id = org.json()["id"]

        term = httpx.post(f"{base_url}/api/v1/admin/terms", json={"organization_id": org_id, "name": f"Term {uid}", "starts_on": "2026-09-01", "ends_on": "2026-12-20", "is_active": True}, headers=auth_headers, timeout=10)
        assert term.status_code == 200
        term_id = term.json()["id"]

        course = httpx.post(f"{base_url}/api/v1/admin/courses", json={"organization_id": org_id, "code": f"RVC{uid[:5].upper()}", "title": f"Review Course {uid}", "credits": 3, "prerequisites": []}, headers=auth_headers, timeout=10)
        assert course.status_code == 200, course.text
        course_id = course.json()["id"]

        section = httpx.post(f"{base_url}/api/v1/admin/sections", json={"course_id": course_id, "term_id": term_id, "code": "R1", "capacity": 30, "instructor_id": None}, headers=auth_headers, timeout=10)
        assert section.status_code == 200
        section_id = section.json()["id"]

        reg_round = httpx.post(f"{base_url}/api/v1/admin/registration-rounds", json={"term_id": term_id, "name": f"RvRound {uid}", "starts_at": (now - timedelta(hours=1)).isoformat(), "ends_at": (now + timedelta(hours=3)).isoformat(), "is_active": True}, headers=auth_headers, timeout=10)
        assert reg_round.status_code == 200
        round_id = reg_round.json()["id"]

        # Users
        inst = httpx.post(f"{base_url}/api/v1/admin/users", json={"username": f"rv_inst_{uid}", "password": "RvInst@2026!", "role": "INSTRUCTOR", "is_active": True}, headers=auth_headers, timeout=10)
        assert inst.status_code == 200, inst.text
        inst_id = inst.json()["id"]

        rev = httpx.post(f"{base_url}/api/v1/admin/users", json={"username": f"rv_rev_{uid}", "password": "RvRev@2026!", "role": "REVIEWER", "is_active": True}, headers=auth_headers, timeout=10)
        assert rev.status_code == 200, rev.text
        rev_id = rev.json()["id"]

        stu = httpx.post(f"{base_url}/api/v1/admin/users", json={"username": f"rv_stu_{uid}", "password": "RvStu@2026!", "role": "STUDENT", "is_active": True, "org_id": org_id}, headers=auth_headers, timeout=10)
        assert stu.status_code == 200, stu.text
        stu_id = stu.json()["id"]

        # Scope grants
        inst_scope = httpx.post(f"{base_url}/api/v1/admin/scope-grants", json={"user_id": inst_id, "scope_type": "SECTION", "scope_id": section_id}, headers=auth_headers, timeout=10)
        assert inst_scope.status_code == 200
        inst_scope_id = inst_scope.json()["id"]

        rev_scope = httpx.post(f"{base_url}/api/v1/admin/scope-grants", json={"user_id": rev_id, "scope_type": "SECTION", "scope_id": section_id}, headers=auth_headers, timeout=10)
        assert rev_scope.status_code == 200
        rev_scope_id = rev_scope.json()["id"]

        # Enroll student
        stu_hdrs = _login_as(base_url, f"rv_stu_{uid}", "RvStu@2026!")
        enr = httpx.post(f"{base_url}/api/v1/registration/enroll", json={"section_id": section_id}, headers={**stu_hdrs, "Idempotency-Key": f"rv-enr-{uid}"}, timeout=10)
        assert enr.status_code == 200, enr.text

        inst_hdrs = _login_as(base_url, f"rv_inst_{uid}", "RvInst@2026!")
        rev_hdrs = _login_as(base_url, f"rv_rev_{uid}", "RvRev@2026!")

        # POST /reviews/forms
        form = httpx.post(
            f"{base_url}/api/v1/reviews/forms",
            json={
                "name": f"Form {uid}",
                "organization_id": org_id,
                "criteria": [
                    {"name": "Quality", "weight": 0.6, "min": 0, "max": 5},
                    {"name": "Clarity", "weight": 0.4, "min": 0, "max": 5},
                ],
            },
            headers=inst_hdrs,
            timeout=10,
        )
        assert form.status_code == 200, form.text
        form_id = form.json()["id"]

        # POST /reviews/rounds
        review_round = httpx.post(
            f"{base_url}/api/v1/reviews/rounds",
            json={
                "name": f"Round {uid}",
                "term_id": term_id,
                "section_id": section_id,
                "scoring_form_id": form_id,
                "identity_mode": "OPEN",
            },
            headers=inst_hdrs,
            timeout=10,
        )
        assert review_round.status_code == 200, review_round.text
        review_round_id = review_round.json()["id"]

        # POST /reviews/rounds/{id}/assignments/manual
        assignment = httpx.post(
            f"{base_url}/api/v1/reviews/rounds/{review_round_id}/assignments/manual",
            json={"reviewer_id": rev_id, "student_id": stu_id},
            headers=inst_hdrs,
            timeout=10,
        )
        assert assignment.status_code == 200, assignment.text
        assignment_id = assignment.json()["id"]

        # GET /reviews/rounds/{id}/assignments
        assignments = httpx.get(
            f"{base_url}/api/v1/reviews/rounds/{review_round_id}/assignments",
            headers=inst_hdrs,
            timeout=10,
        )
        assert assignments.status_code == 200
        assert any(a["id"] == assignment_id for a in assignments.json())

        # POST /reviews/scores
        score = httpx.post(
            f"{base_url}/api/v1/reviews/scores",
            json={
                "assignment_id": assignment_id,
                "criterion_scores": {"Quality": 4, "Clarity": 5},
                "comment": "Well done",
            },
            headers=rev_hdrs,
            timeout=10,
        )
        assert score.status_code == 200, score.text

        # GET /reviews/rounds/{id}/outliers
        outliers = httpx.get(
            f"{base_url}/api/v1/reviews/rounds/{review_round_id}/outliers",
            headers=inst_hdrs,
            timeout=10,
        )
        assert outliers.status_code == 200

        # POST /reviews/rounds/{id}/close
        close = httpx.post(
            f"{base_url}/api/v1/reviews/rounds/{review_round_id}/close",
            headers=inst_hdrs,
            timeout=10,
        )
        assert close.status_code == 200, close.text

        # GET /reviews/rounds/{id}/export
        export = httpx.get(
            f"{base_url}/api/v1/reviews/rounds/{review_round_id}/export",
            headers=inst_hdrs,
            timeout=10,
        )
        assert export.status_code == 200

    finally:
        for res_id, path in [
            (inst_scope_id, "scope-grants"),
            (rev_scope_id, "scope-grants"),
            (stu_id, "users"),
            (rev_id, "users"),
            (inst_id, "users"),
            (round_id, "registration-rounds"),
            (section_id, "sections"),
            (course_id, "courses"),
            (term_id, "terms"),
            (org_id, "organizations"),
        ]:
            _cleanup(base_url, path, res_id, auth_headers)


# ---------------------------------------------------------------------------
# 16. Review – auto-assignment, rechecks, and recheck-assign  (PART 1 gap fill)
# ---------------------------------------------------------------------------


def test_review_auto_assign_and_recheck_lifecycle(base_url: str, auth_headers: dict) -> None:
    """
    Covers three review endpoints absent from test_review_round_lifecycle:

      POST /reviews/rounds/{round_id}/assignments/auto
      POST /reviews/rechecks
      POST /reviews/rechecks/{recheck_id}/assign

    Flow:
      admin seeds catalog + reg round + users
      → instructor creates form + round
      → auto-assigns 2 reviewers to the enrolled student  (endpoint 1)
      → student submits a recheck request  (endpoint 2, status=REQUESTED)
      → instructor assigns a reviewer to the recheck  (endpoint 3, status→ASSIGNED)
    """
    uid = _uid()
    now = datetime.now(timezone.utc)

    org_id = term_id = course_id = section_id = reg_round_id = None
    inst_id = rev1_id = rev2_id = stu_id = None
    inst_scope_id = rev1_scope_id = rev2_scope_id = None

    try:
        # --- Catalog ---
        org = httpx.post(
            f"{base_url}/api/v1/admin/organizations",
            json={"name": f"AutoOrg {uid}", "code": f"AU{uid[:6].upper()}", "is_active": True},
            headers=auth_headers, timeout=10,
        )
        assert org.status_code == 200, org.text
        org_id = org.json()["id"]

        term = httpx.post(
            f"{base_url}/api/v1/admin/terms",
            json={"organization_id": org_id, "name": f"Term {uid}",
                  "starts_on": "2026-09-01", "ends_on": "2026-12-20", "is_active": True},
            headers=auth_headers, timeout=10,
        )
        assert term.status_code == 200, term.text
        term_id = term.json()["id"]

        course = httpx.post(
            f"{base_url}/api/v1/admin/courses",
            json={"organization_id": org_id, "code": f"AUC{uid[:5].upper()}",
                  "title": f"Auto Course {uid}", "credits": 3, "prerequisites": []},
            headers=auth_headers, timeout=10,
        )
        assert course.status_code == 200, course.text
        course_id = course.json()["id"]

        section = httpx.post(
            f"{base_url}/api/v1/admin/sections",
            json={"course_id": course_id, "term_id": term_id,
                  "code": "A1", "capacity": 30, "instructor_id": None},
            headers=auth_headers, timeout=10,
        )
        assert section.status_code == 200, section.text
        section_id = section.json()["id"]

        reg_round = httpx.post(
            f"{base_url}/api/v1/admin/registration-rounds",
            json={
                "term_id": term_id,
                "name": f"Reg {uid}",
                "starts_at": (now - timedelta(hours=1)).isoformat(),
                "ends_at": (now + timedelta(hours=3)).isoformat(),
                "is_active": True,
            },
            headers=auth_headers, timeout=10,
        )
        assert reg_round.status_code == 200, reg_round.text
        reg_round_id = reg_round.json()["id"]

        # --- Users ---
        inst = httpx.post(
            f"{base_url}/api/v1/admin/users",
            json={"username": f"au_inst_{uid}", "password": "AuInst@2026!",
                  "role": "INSTRUCTOR", "is_active": True},
            headers=auth_headers, timeout=10,
        )
        assert inst.status_code == 200, inst.text
        inst_id = inst.json()["id"]

        rev1 = httpx.post(
            f"{base_url}/api/v1/admin/users",
            json={"username": f"au_rv1_{uid}", "password": "AuRev1@2026!",
                  "role": "REVIEWER", "is_active": True},
            headers=auth_headers, timeout=10,
        )
        assert rev1.status_code == 200, rev1.text
        rev1_id = rev1.json()["id"]

        rev2 = httpx.post(
            f"{base_url}/api/v1/admin/users",
            json={"username": f"au_rv2_{uid}", "password": "AuRev2@2026!",
                  "role": "REVIEWER", "is_active": True},
            headers=auth_headers, timeout=10,
        )
        assert rev2.status_code == 200, rev2.text
        rev2_id = rev2.json()["id"]

        stu = httpx.post(
            f"{base_url}/api/v1/admin/users",
            json={"username": f"au_stu_{uid}", "password": "AuStu@2026!",
                  "role": "STUDENT", "is_active": True, "org_id": org_id},
            headers=auth_headers, timeout=10,
        )
        assert stu.status_code == 200, stu.text
        stu_id = stu.json()["id"]

        # --- Scope grants ---
        inst_scope = httpx.post(
            f"{base_url}/api/v1/admin/scope-grants",
            json={"user_id": inst_id, "scope_type": "SECTION", "scope_id": section_id},
            headers=auth_headers, timeout=10,
        )
        assert inst_scope.status_code == 200
        inst_scope_id = inst_scope.json()["id"]

        rev1_scope = httpx.post(
            f"{base_url}/api/v1/admin/scope-grants",
            json={"user_id": rev1_id, "scope_type": "SECTION", "scope_id": section_id},
            headers=auth_headers, timeout=10,
        )
        assert rev1_scope.status_code == 200
        rev1_scope_id = rev1_scope.json()["id"]

        rev2_scope = httpx.post(
            f"{base_url}/api/v1/admin/scope-grants",
            json={"user_id": rev2_id, "scope_type": "SECTION", "scope_id": section_id},
            headers=auth_headers, timeout=10,
        )
        assert rev2_scope.status_code == 200
        rev2_scope_id = rev2_scope.json()["id"]

        # Enrol student (required for assignment eligibility and recheck creation)
        stu_hdrs = _login_as(base_url, f"au_stu_{uid}", "AuStu@2026!")
        enroll = httpx.post(
            f"{base_url}/api/v1/registration/enroll",
            json={"section_id": section_id},
            headers={**stu_hdrs, "Idempotency-Key": f"au-enr-{uid}"},
            timeout=10,
        )
        assert enroll.status_code == 200, enroll.text

        inst_hdrs = _login_as(base_url, f"au_inst_{uid}", "AuInst@2026!")

        # --- Scoring form + review round ---
        form = httpx.post(
            f"{base_url}/api/v1/reviews/forms",
            json={
                "name": f"AutoForm {uid}",
                "organization_id": org_id,
                "criteria": [{"name": "Quality", "weight": 1, "min": 0, "max": 5}],
            },
            headers=inst_hdrs, timeout=10,
        )
        assert form.status_code == 200, form.text
        form_id = form.json()["id"]

        review_round = httpx.post(
            f"{base_url}/api/v1/reviews/rounds",
            json={
                "name": f"AutoRound {uid}",
                "term_id": term_id,
                "section_id": section_id,
                "scoring_form_id": form_id,
                "identity_mode": "OPEN",
            },
            headers=inst_hdrs, timeout=10,
        )
        assert review_round.status_code == 200, review_round.text
        review_round_id = review_round.json()["id"]

        # ---------------------------------------------------------------
        # ENDPOINT 1: POST /reviews/rounds/{round_id}/assignments/auto
        # ---------------------------------------------------------------
        auto_resp = httpx.post(
            f"{base_url}/api/v1/reviews/rounds/{review_round_id}/assignments/auto",
            json={"student_ids": [stu_id], "reviewers_per_student": 2},
            headers=inst_hdrs, timeout=10,
        )
        assert auto_resp.status_code == 200, auto_resp.text
        assert auto_resp.json()["created_assignments"] == 2

        # Verify both reviewers appear in the assignment list
        listed = httpx.get(
            f"{base_url}/api/v1/reviews/rounds/{review_round_id}/assignments",
            headers=inst_hdrs, timeout=10,
        )
        assert listed.status_code == 200
        assigned_reviewer_ids = {a["reviewer_id"] for a in listed.json()}
        assert rev1_id in assigned_reviewer_ids
        assert rev2_id in assigned_reviewer_ids

        # ---------------------------------------------------------------
        # ENDPOINT 2: POST /reviews/rechecks
        # ---------------------------------------------------------------
        recheck_resp = httpx.post(
            f"{base_url}/api/v1/reviews/rechecks",
            json={
                "round_id": review_round_id,
                "student_id": stu_id,
                "section_id": section_id,
                "reason": "Please re-evaluate the Quality criterion.",
            },
            headers=stu_hdrs, timeout=10,
        )
        assert recheck_resp.status_code == 200, recheck_resp.text
        recheck_id = recheck_resp.json()["id"]
        assert recheck_resp.json()["status"] == "REQUESTED"

        # ---------------------------------------------------------------
        # ENDPOINT 3: POST /reviews/rechecks/{recheck_id}/assign
        # ---------------------------------------------------------------
        assign_resp = httpx.post(
            f"{base_url}/api/v1/reviews/rechecks/{recheck_id}/assign",
            json={"reviewer_id": rev1_id},
            headers=inst_hdrs, timeout=10,
        )
        assert assign_resp.status_code == 200, assign_resp.text
        assert assign_resp.json()["message"] == "Assigned."

        # Re-assigning to a different reviewer is also idempotent (existing
        # assignment for rev1 is reused; rev2 gets a new assignment)
        reassign = httpx.post(
            f"{base_url}/api/v1/reviews/rechecks/{recheck_id}/assign",
            json={"reviewer_id": rev2_id},
            headers=inst_hdrs, timeout=10,
        )
        assert reassign.status_code == 200, reassign.text

    finally:
        for res_id, path in [
            (inst_scope_id, "scope-grants"),
            (rev1_scope_id, "scope-grants"),
            (rev2_scope_id, "scope-grants"),
            (stu_id, "users"),
            (rev2_id, "users"),
            (rev1_id, "users"),
            (inst_id, "users"),
            (reg_round_id, "registration-rounds"),
            (section_id, "sections"),
            (course_id, "courses"),
            (term_id, "terms"),
            (org_id, "organizations"),
        ]:
            _cleanup(base_url, path, res_id, auth_headers)
