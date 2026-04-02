from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import generate_session_token, hash_password, token_hash, validate_password_complexity, verify_password
from app.models.user import LoginAttempt, SessionToken, User, UserRole

LOCKOUT_ATTEMPTS = 5
LOCKOUT_WINDOW_MINUTES = 15
LOCKOUT_COOLDOWN_MINUTES = 30


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _record_attempt(db: Session, username: str, success: bool) -> None:
    db.add(LoginAttempt(username=username, success=success))
    db.commit()


def is_locked_out(db: Session, username: str) -> tuple[bool, datetime | None]:
    now = _utcnow()
    window_start = now - timedelta(minutes=LOCKOUT_WINDOW_MINUTES)
    failed_attempts = (
        db.query(LoginAttempt)
        .filter(LoginAttempt.username == username, LoginAttempt.success.is_(False), LoginAttempt.attempted_at >= window_start)
        .order_by(desc(LoginAttempt.attempted_at))
        .all()
    )
    if len(failed_attempts) < LOCKOUT_ATTEMPTS:
        return False, None

    latest_failure = failed_attempts[0].attempted_at
    if latest_failure.tzinfo is None:
        latest_failure = latest_failure.replace(tzinfo=timezone.utc)
    locked_until = latest_failure + timedelta(minutes=LOCKOUT_COOLDOWN_MINUTES)
    if now < locked_until:
        return True, locked_until
    return False, None


def login(db: Session, username: str, password: str) -> tuple[str, SessionToken]:
    locked, locked_until = is_locked_out(db, username)
    if locked:
        assert locked_until is not None
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Account locked due to failed attempts. Try again after {locked_until.isoformat()}.",
        )

    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        _record_attempt(db, username, False)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")

    _record_attempt(db, username, True)

    raw_token = generate_session_token()
    now = _utcnow()
    absolute_expires = now + timedelta(seconds=settings.session_absolute_timeout)
    session = SessionToken(
        user_id=user.id,
        token_hash=token_hash(raw_token),
        last_active_at=now,
        absolute_expires_at=absolute_expires,
        revoked=False,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return raw_token, session


def logout(db: Session, session: SessionToken) -> None:
    if not session.revoked:
        session.revoked = True
        session.revoked_at = _utcnow()
        db.commit()


def change_password(db: Session, user: User, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect.")

    valid, reason = validate_password_complexity(new_password)
    if not valid:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=reason)

    if verify_password(new_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="New password must be different from current password.",
        )

    user.password_hash = hash_password(new_password)
    db.commit()


def create_seed_admin(db: Session) -> None:
    existing = db.query(User).filter(User.username == "admin").first()
    if existing is not None:
        return
    db.add(
        User(
            username="admin",
            password_hash=hash_password("Admin1234!@#$"),
            role=UserRole.admin,
            is_active=True,
        )
    )
    db.commit()
