from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.security import hash_password, token_hash
from app.models.user import SessionToken, User, UserRole


def _create_user(db: Session, username: str = "student1", password: str = "ValidPassword1!") -> User:
    user = User(username=username, password_hash=hash_password(password), role=UserRole.student, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_login_success(client, db_session: Session) -> None:
    _create_user(db_session)
    response = client.post("/api/v1/auth/login", json={"username": "student1", "password": "ValidPassword1!"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["token"]
    assert payload["idle_expires_at"]
    assert payload["absolute_expires_at"]


def test_login_failure_and_lockout(client, db_session: Session) -> None:
    _create_user(db_session, username="locked")
    for _ in range(5):
        response = client.post("/api/v1/auth/login", json={"username": "locked", "password": "wrong"})
        assert response.status_code == 401

    locked_response = client.post("/api/v1/auth/login", json={"username": "locked", "password": "ValidPassword1!"})
    assert locked_response.status_code == 423


def test_me_requires_auth(client) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_me_and_logout(client, db_session: Session) -> None:
    _create_user(db_session)
    login = client.post("/api/v1/auth/login", json={"username": "student1", "password": "ValidPassword1!"})
    token = login.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["username"] == "student1"

    logout = client.post("/api/v1/auth/logout", headers=headers)
    assert logout.status_code == 200

    me_after_logout = client.get("/api/v1/auth/me", headers=headers)
    assert me_after_logout.status_code == 401


def test_password_change(client, db_session: Session) -> None:
    _create_user(db_session)
    login = client.post("/api/v1/auth/login", json={"username": "student1", "password": "ValidPassword1!"})
    token = login.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": "ValidPassword1!", "new_password": "N3wPassword!321"},
        headers=headers,
    )
    assert response.status_code == 200

    old_login = client.post("/api/v1/auth/login", json={"username": "student1", "password": "ValidPassword1!"})
    assert old_login.status_code == 401
    new_login = client.post("/api/v1/auth/login", json={"username": "student1", "password": "N3wPassword!321"})
    assert new_login.status_code == 200


def test_expired_session_rejected(client, db_session: Session) -> None:
    user = _create_user(db_session)
    raw_token = "expired-token"
    session = SessionToken(
        user_id=user.id,
        token_hash=token_hash(raw_token),
        last_active_at=datetime.now(timezone.utc) - timedelta(hours=9),
        absolute_expires_at=datetime.now(timezone.utc) + timedelta(hours=3),
    )
    db_session.add(session)
    db_session.commit()

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {raw_token}"})
    assert response.status_code == 401
