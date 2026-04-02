from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User, UserRole


def _create_user(db: Session, username: str, role: UserRole, password: str = "AdminPassword1!") -> User:
    user = User(username=username, password_hash=hash_password(password), role=role, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth_headers(client, username: str, password: str) -> dict[str, str]:
    login = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200
    token = login.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_admin_crud_and_audit_log(client, db_session: Session) -> None:
    _create_user(db_session, "admin1", UserRole.admin)
    headers = _auth_headers(client, "admin1", "AdminPassword1!")

    org = client.post("/api/v1/admin/organizations", json={"name": "North Campus", "code": "NC", "is_active": True}, headers=headers)
    assert org.status_code == 200
    org_id = org.json()["id"]

    org_list = client.get("/api/v1/admin/organizations", headers=headers)
    assert org_list.status_code == 200
    assert len(org_list.json()) == 1

    upd_org = client.put(
        f"/api/v1/admin/organizations/{org_id}",
        json={"name": "North Campus Updated", "code": "NCU", "is_active": True},
        headers=headers,
    )
    assert upd_org.status_code == 200

    term = client.post(
        "/api/v1/admin/terms",
        json={"organization_id": org_id, "name": "Fall 2026", "starts_on": "2026-09-01", "ends_on": "2026-12-20", "is_active": True},
        headers=headers,
    )
    assert term.status_code == 200
    term_id = term.json()["id"]

    course = client.post(
        "/api/v1/admin/courses",
        json={"organization_id": org_id, "code": "CS101", "title": "Intro CS", "credits": 3, "prerequisites": []},
        headers=headers,
    )
    assert course.status_code == 200
    course_id = course.json()["id"]
    assert client.get("/api/v1/admin/courses", headers=headers).status_code == 200
    assert (
        client.put(
            f"/api/v1/admin/courses/{course_id}",
            json={"organization_id": org_id, "code": "CS101", "title": "Intro to Computer Science", "credits": 4, "prerequisites": []},
            headers=headers,
        ).status_code
        == 200
    )

    section = client.post(
        "/api/v1/admin/sections",
        json={"course_id": course_id, "term_id": term_id, "code": "A", "capacity": 30, "instructor_id": None},
        headers=headers,
    )
    assert section.status_code == 200
    section_id = section.json()["id"]
    assert client.get("/api/v1/admin/sections", headers=headers).status_code == 200
    assert (
        client.put(
            f"/api/v1/admin/sections/{section_id}",
            json={"course_id": course_id, "term_id": term_id, "code": "B", "capacity": 35, "instructor_id": None},
            headers=headers,
        ).status_code
        == 200
    )

    round_response = client.post(
        "/api/v1/admin/registration-rounds",
        json={
            "term_id": term_id,
            "name": "Primary",
            "starts_at": datetime.now(timezone.utc).isoformat(),
            "ends_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
            "is_active": True,
        },
        headers=headers,
    )
    assert round_response.status_code == 200
    round_id = round_response.json()["id"]
    assert client.get("/api/v1/admin/registration-rounds", headers=headers).status_code == 200
    assert (
        client.put(
            f"/api/v1/admin/registration-rounds/{round_id}",
            json={
                "term_id": term_id,
                "name": "Primary Updated",
                "starts_at": datetime.now(timezone.utc).isoformat(),
                "ends_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                "is_active": True,
            },
            headers=headers,
        ).status_code
        == 200
    )

    logs = client.get("/api/v1/admin/audit-log", headers=headers)
    assert logs.status_code == 200
    assert len(logs.json()) >= 6

    assert client.delete(f"/api/v1/admin/registration-rounds/{round_id}", headers=headers).status_code == 200
    assert client.delete(f"/api/v1/admin/sections/{section_id}", headers=headers).status_code == 200
    assert client.delete(f"/api/v1/admin/courses/{course_id}", headers=headers).status_code == 200
    delete_term = client.delete(f"/api/v1/admin/terms/{term_id}", headers=headers)
    assert delete_term.status_code == 200
    assert client.delete(f"/api/v1/admin/organizations/{org_id}", headers=headers).status_code == 200


def test_rbac_denies_non_admin(client, db_session: Session) -> None:
    _create_user(db_session, "student1", UserRole.student, "StudentPassword1!")
    headers = _auth_headers(client, "student1", "StudentPassword1!")

    response = client.get("/api/v1/admin/organizations", headers=headers)
    assert response.status_code == 403


def test_user_deactivation_revokes_sessions(client, db_session: Session) -> None:
    _create_user(db_session, "admin1", UserRole.admin)
    _create_user(db_session, "reviewer1", UserRole.reviewer, "ReviewerPassword1!")
    admin_headers = _auth_headers(client, "admin1", "AdminPassword1!")

    reviewer_login = client.post("/api/v1/auth/login", json={"username": "reviewer1", "password": "ReviewerPassword1!"})
    reviewer_token = reviewer_login.json()["token"]
    reviewer_headers = {"Authorization": f"Bearer {reviewer_token}"}

    users = client.get("/api/v1/admin/users", headers=admin_headers)
    reviewer_id = [row["id"] for row in users.json() if row["username"] == "reviewer1"][0]

    deactivate = client.put(f"/api/v1/admin/users/{reviewer_id}", json={"is_active": False}, headers=admin_headers)
    assert deactivate.status_code == 200

    me = client.get("/api/v1/auth/me", headers=reviewer_headers)
    assert me.status_code == 401


def test_admin_user_crud(client, db_session: Session) -> None:
    _create_user(db_session, "admin1", UserRole.admin)
    headers = _auth_headers(client, "admin1", "AdminPassword1!")

    create = client.post(
        "/api/v1/admin/users",
        json={"username": "finance1", "password": "FinancePassword1!", "role": "FINANCE_CLERK", "is_active": True},
        headers=headers,
    )
    assert create.status_code == 200
    user_id = create.json()["id"]

    update = client.put(f"/api/v1/admin/users/{user_id}", json={"role": "REVIEWER"}, headers=headers)
    assert update.status_code == 200
    assert update.json()["role"] == "REVIEWER"

    delete = client.delete(f"/api/v1/admin/users/{user_id}", headers=headers)
    assert delete.status_code == 200
