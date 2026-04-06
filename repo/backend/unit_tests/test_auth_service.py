from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.config import settings
from app.core.security import hash_password, validate_password_complexity
from app.models.user import LoginAttempt, User, UserRole
from app.services.auth_service import bootstrap_admin, is_locked_out


def _make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def test_password_complexity_rules() -> None:
    valid, reason = validate_password_complexity("StrongPass123!")
    assert valid is True
    assert reason is None

    valid, reason = validate_password_complexity("weak")
    assert valid is False
    assert reason is not None


def test_lockout_after_five_failures() -> None:
    db = _make_db()
    username = "lock_user"
    now = datetime.now(timezone.utc)
    for _ in range(5):
        db.add(LoginAttempt(username=username, success=False, attempted_at=now - timedelta(minutes=2)))
    db.commit()

    locked, _ = is_locked_out(db, username)
    assert locked is True


def test_not_locked_after_cooldown() -> None:
    db = _make_db()
    username = "lock_user_old"
    old = datetime.now(timezone.utc) - timedelta(minutes=50)
    for _ in range(5):
        db.add(LoginAttempt(username=username, success=False, attempted_at=old))
    db.commit()

    locked, _ = is_locked_out(db, username)
    assert locked is False


def test_user_password_hash() -> None:
    db = _make_db()
    user = User(username="u1", password_hash=hash_password("StrongPass123!"), role=UserRole.student, is_active=True)
    db.add(user)
    db.commit()
    assert user.id is not None


def test_bootstrap_admin_hashes_password() -> None:
    db = _make_db()
    original_token = settings.bootstrap_admin_token
    settings.bootstrap_admin_token = "unit-bootstrap"
    try:
        admin = bootstrap_admin(db, username="root_admin", password="StrongPass123!", bootstrap_token="unit-bootstrap")
        assert admin.role == UserRole.admin
        assert admin.password_hash != "StrongPass123!"
    finally:
        settings.bootstrap_admin_token = original_token
