"""External HTTP integration tests against the Dockerised CEMS API.

These tests make real HTTP calls over the network (not via FastAPI TestClient)
against the service running inside Docker.  They therefore exercise layers that
in-process tests skip: middleware (X-Request-ID, CORS), real PostgreSQL
persistence, actual HTTP serialisation, and networking.

Run via:
    ./run_tests.sh
or directly:
    docker compose exec api pytest integration/ -v --tb=short
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _uid() -> str:
    """Eight-char hex suffix – keeps resource names unique across runs."""
    return uuid.uuid4().hex[:8]


def _delete(base_url: str, path: str, resource_id: int | None, headers: dict) -> None:
    """Teardown DELETE that asserts a sensible status code.

    Accepts 200 (deleted) and 404 (already gone – the test itself may have
    deleted it as part of its assertions).  Any other code is surfaced as a
    test failure so silent mis-configurations cannot hide problems.
    """
    if resource_id is None:
        return
    r = httpx.delete(f"{base_url}/api/v1/admin/{path}/{resource_id}", headers=headers, timeout=10)
    assert r.status_code in (200, 404), (
        f"Unexpected {r.status_code} when cleaning up /admin/{path}/{resource_id}: {r.text[:200]}"
    )


# ---------------------------------------------------------------------------
# 1. Service health & infrastructure
# ---------------------------------------------------------------------------


def test_health_live_returns_ok(base_url: str) -> None:
    """Live probe must return 200 with expected payload."""
    r = httpx.get(f"{base_url}/api/v1/health/live", timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "api"


def test_health_ready_performs_db_check(base_url: str) -> None:
    """Ready probe must confirm database connectivity."""
    r = httpx.get(f"{base_url}/api/v1/health/ready", timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_server_generates_request_id(base_url: str) -> None:
    """Middleware must inject X-Request-ID when the client does not supply one."""
    r = httpx.get(f"{base_url}/api/v1/health/live", timeout=5)
    assert r.status_code == 200
    assert r.headers.get("x-request-id"), "Server must inject X-Request-ID into every response"


def test_client_request_id_echoed_unchanged(base_url: str) -> None:
    """Middleware must echo a client-supplied X-Request-ID back verbatim."""
    rid = f"ext-{_uid()}"
    r = httpx.get(f"{base_url}/api/v1/health/live", headers={"X-Request-ID": rid}, timeout=5)
    assert r.status_code == 200
    assert r.headers.get("x-request-id") == rid


# ---------------------------------------------------------------------------
# 2. Auth lifecycle
# ---------------------------------------------------------------------------


def test_unauthenticated_request_returns_401(base_url: str) -> None:
    """Protected endpoints must reject requests that carry no bearer token."""
    r = httpx.get(f"{base_url}/api/v1/auth/me", timeout=5)
    assert r.status_code == 401


def test_invalid_credentials_rejected(base_url: str) -> None:
    """Login with a non-existent username must return 401."""
    r = httpx.post(
        f"{base_url}/api/v1/auth/login",
        json={"username": f"ghost_{_uid()}", "password": "WrongPass1!"},
        timeout=5,
    )
    assert r.status_code == 401


def test_full_auth_lifecycle(base_url: str, auth_headers: dict) -> None:
    """
    Full auth roundtrip over real HTTP:
      admin creates user → user logs in → /me succeeds →
      user logs out → /me returns 401.
    """
    username = f"ext_auth_{_uid()}"
    password = "AuthTest@2026!"
    user_id: int | None = None

    try:
        # Admin creates user
        create = httpx.post(
            f"{base_url}/api/v1/admin/users",
            json={"username": username, "password": password, "role": "STUDENT", "is_active": True},
            headers=auth_headers,
            timeout=10,
        )
        assert create.status_code == 200, create.text
        user_id = create.json()["id"]

        # User logs in
        login = httpx.post(
            f"{base_url}/api/v1/auth/login",
            json={"username": username, "password": password},
            timeout=10,
        )
        assert login.status_code == 200, login.text
        token = login.json()["token"]
        assert token
        assert login.json()["idle_expires_at"]
        assert login.json()["absolute_expires_at"]

        user_headers = {"Authorization": f"Bearer {token}"}

        # Authenticated /me
        me = httpx.get(f"{base_url}/api/v1/auth/me", headers=user_headers, timeout=5)
        assert me.status_code == 200
        assert me.json()["username"] == username
        assert me.json()["role"] == "STUDENT"

        # Logout
        logout = httpx.post(f"{base_url}/api/v1/auth/logout", headers=user_headers, timeout=5)
        assert logout.status_code == 200

        # Token is now revoked
        me_after = httpx.get(f"{base_url}/api/v1/auth/me", headers=user_headers, timeout=5)
        assert me_after.status_code == 401

    finally:
        _delete(base_url, "users", user_id, auth_headers)


# ---------------------------------------------------------------------------
# 3. Admin catalog CRUD lifecycle
# ---------------------------------------------------------------------------


def test_org_create_update_delete_lifecycle(base_url: str, auth_headers: dict) -> None:
    """Create → list → update → delete an organisation via real HTTP."""
    uid = _uid()
    org_id: int | None = None
    deleted = False

    try:
        # Create
        create = httpx.post(
            f"{base_url}/api/v1/admin/organizations",
            json={"name": f"Ext Org {uid}", "code": f"EXT{uid[:4].upper()}", "is_active": True},
            headers=auth_headers,
            timeout=10,
        )
        assert create.status_code == 200, create.text
        org_id = create.json()["id"]
        assert create.json()["name"] == f"Ext Org {uid}"

        # Appears in listing
        listing = httpx.get(f"{base_url}/api/v1/admin/organizations", headers=auth_headers, timeout=10)
        assert listing.status_code == 200
        assert any(o["id"] == org_id for o in listing.json())

        # Update
        update = httpx.put(
            f"{base_url}/api/v1/admin/organizations/{org_id}",
            json={"name": f"Ext Org {uid} v2", "code": f"EXT{uid[:4].upper()}", "is_active": True},
            headers=auth_headers,
            timeout=10,
        )
        assert update.status_code == 200
        assert update.json()["name"].endswith("v2")

        # Delete
        delete = httpx.delete(
            f"{base_url}/api/v1/admin/organizations/{org_id}",
            headers=auth_headers,
            timeout=10,
        )
        assert delete.status_code == 200
        deleted = True

    finally:
        if not deleted:
            _delete(base_url, "organizations", org_id, auth_headers)


def test_full_catalog_crud_lifecycle(base_url: str, auth_headers: dict) -> None:
    """
    Create org → term → course → section in order, assert each step,
    then delete in reverse order.
    """
    uid = _uid()
    org_id = term_id = course_id = section_id = None

    try:
        org = httpx.post(
            f"{base_url}/api/v1/admin/organizations",
            json={"name": f"Catalog {uid}", "code": f"CAT{uid[:5].upper()}", "is_active": True},
            headers=auth_headers, timeout=10,
        )
        assert org.status_code == 200, org.text
        org_id = org.json()["id"]

        term = httpx.post(
            f"{base_url}/api/v1/admin/terms",
            json={
                "organization_id": org_id, "name": f"Term {uid}",
                "starts_on": "2026-09-01", "ends_on": "2026-12-20", "is_active": True,
            },
            headers=auth_headers, timeout=10,
        )
        assert term.status_code == 200, term.text
        term_id = term.json()["id"]

        course = httpx.post(
            f"{base_url}/api/v1/admin/courses",
            json={
                "organization_id": org_id, "code": f"C{uid[:5].upper()}",
                "title": f"Ext Course {uid}", "credits": 3, "prerequisites": [],
            },
            headers=auth_headers, timeout=10,
        )
        assert course.status_code == 200, course.text
        course_id = course.json()["id"]
        assert course.json()["credits"] == 3

        section = httpx.post(
            f"{base_url}/api/v1/admin/sections",
            json={"course_id": course_id, "term_id": term_id, "code": "A", "capacity": 30, "instructor_id": None},
            headers=auth_headers, timeout=10,
        )
        assert section.status_code == 200, section.text
        section_id = section.json()["id"]
        assert section.json()["capacity"] == 30

        # Listing endpoints must succeed with resources present
        assert httpx.get(f"{base_url}/api/v1/admin/courses", headers=auth_headers, timeout=10).status_code == 200
        assert httpx.get(f"{base_url}/api/v1/admin/sections", headers=auth_headers, timeout=10).status_code == 200

    finally:
        for res_id, path in [
            (section_id, "sections"),
            (course_id, "courses"),
            (term_id, "terms"),
            (org_id, "organizations"),
        ]:
            _delete(base_url, path, res_id, auth_headers)


# ---------------------------------------------------------------------------
# 4. RBAC enforcement
# ---------------------------------------------------------------------------


def test_student_cannot_access_admin_routes(base_url: str, auth_headers: dict) -> None:
    """A student token must receive 403 on admin-only endpoints."""
    username = f"ext_rbac_{_uid()}"
    password = "RbacTest@2026!"
    user_id: int | None = None

    try:
        create = httpx.post(
            f"{base_url}/api/v1/admin/users",
            json={"username": username, "password": password, "role": "STUDENT", "is_active": True},
            headers=auth_headers, timeout=10,
        )
        assert create.status_code == 200, create.text
        user_id = create.json()["id"]

        login = httpx.post(
            f"{base_url}/api/v1/auth/login",
            json={"username": username, "password": password},
            timeout=10,
        )
        assert login.status_code == 200
        student_headers = {"Authorization": f"Bearer {login.json()['token']}"}

        r = httpx.get(f"{base_url}/api/v1/admin/organizations", headers=student_headers, timeout=5)
        assert r.status_code == 403

    finally:
        _delete(base_url, "users", user_id, auth_headers)


# ---------------------------------------------------------------------------
# 5. Registration workflow
# ---------------------------------------------------------------------------


def test_enrollment_workflow(base_url: str, auth_headers: dict) -> None:
    """
    End-to-end enrollment over real HTTP:
      admin seeds catalog + creates student → student logs in →
      student enrolls → idempotent replay returns same status.
    """
    uid = _uid()
    now = datetime.now(timezone.utc)
    org_id = term_id = course_id = section_id = round_id = student_id = None

    try:
        # --- Seed catalog ---
        org = httpx.post(
            f"{base_url}/api/v1/admin/organizations",
            json={"name": f"Enroll Org {uid}", "code": f"ENR{uid[:5].upper()}", "is_active": True},
            headers=auth_headers, timeout=10,
        )
        assert org.status_code == 200, org.text
        org_id = org.json()["id"]

        term = httpx.post(
            f"{base_url}/api/v1/admin/terms",
            json={
                "organization_id": org_id, "name": f"Term {uid}",
                "starts_on": "2026-09-01", "ends_on": "2026-12-20", "is_active": True,
            },
            headers=auth_headers, timeout=10,
        )
        assert term.status_code == 200, term.text
        term_id = term.json()["id"]

        course = httpx.post(
            f"{base_url}/api/v1/admin/courses",
            json={
                "organization_id": org_id, "code": f"E{uid[:5].upper()}",
                "title": f"Enroll Course {uid}", "credits": 3, "prerequisites": [],
            },
            headers=auth_headers, timeout=10,
        )
        assert course.status_code == 200, course.text
        course_id = course.json()["id"]

        section = httpx.post(
            f"{base_url}/api/v1/admin/sections",
            json={"course_id": course_id, "term_id": term_id, "code": "A", "capacity": 30, "instructor_id": None},
            headers=auth_headers, timeout=10,
        )
        assert section.status_code == 200, section.text
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
            headers=auth_headers, timeout=10,
        )
        assert reg_round.status_code == 200, reg_round.text
        round_id = reg_round.json()["id"]

        # --- Create student in this org ---
        username = f"ext_stu_{uid}"
        password = "EnrollTest@2026!"
        stu = httpx.post(
            f"{base_url}/api/v1/admin/users",
            json={"username": username, "password": password, "role": "STUDENT", "is_active": True, "org_id": org_id},
            headers=auth_headers, timeout=10,
        )
        assert stu.status_code == 200, stu.text
        student_id = stu.json()["id"]

        # --- Student logs in and enrolls ---
        login = httpx.post(
            f"{base_url}/api/v1/auth/login",
            json={"username": username, "password": password},
            timeout=10,
        )
        assert login.status_code == 200
        student_headers = {
            "Authorization": f"Bearer {login.json()['token']}",
            "Idempotency-Key": f"enroll-{uid}",
        }

        enroll = httpx.post(
            f"{base_url}/api/v1/registration/enroll",
            json={"section_id": section_id},
            headers=student_headers,
            timeout=10,
        )
        assert enroll.status_code == 200, enroll.text
        assert enroll.json()["status"] in {"enrolled", "already_enrolled"}

        # Replay with the same Idempotency-Key must return the same status
        replay = httpx.post(
            f"{base_url}/api/v1/registration/enroll",
            json={"section_id": section_id},
            headers=student_headers,
            timeout=10,
        )
        assert replay.status_code == 200
        assert replay.json()["status"] in {"enrolled", "already_enrolled"}

    finally:
        # Delete student first (cascades enrollments), then catalog in reverse order.
        for res_id, path in [
            (student_id, "users"),
            (round_id, "registration-rounds"),
            (section_id, "sections"),
            (course_id, "courses"),
            (term_id, "terms"),
            (org_id, "organizations"),
        ]:
            _delete(base_url, path, res_id, auth_headers)
