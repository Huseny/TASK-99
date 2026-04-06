from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.security import token_hash
from app.models.user import SessionToken, User, UserRole
from app.services import auth_service

bearer_scheme = HTTPBearer(auto_error=False)
logger = get_logger("app.auth")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> SessionToken:
    if credentials is None:
        logger.info("missing_auth_credentials", extra={"event": "auth.session.missing_credentials"})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    session = db.query(SessionToken).filter(SessionToken.token_hash == token_hash(credentials.credentials)).first()
    if session is None or session.revoked:
        logger.info("invalid_or_revoked_session", extra={"event": "auth.session.invalid_or_revoked"})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session.")

    now = _utcnow()
    last_active = session.last_active_at
    if last_active.tzinfo is None:
        last_active = last_active.replace(tzinfo=timezone.utc)

    absolute_expiry = session.absolute_expires_at
    if absolute_expiry.tzinfo is None:
        absolute_expiry = absolute_expiry.replace(tzinfo=timezone.utc)

    if now > absolute_expiry:
        auth_service.revoke_session(db, session, at=now)
        logger.info(
            "session_expired_absolute",
            extra={"event": "auth.session.expired_absolute", "fields": {"session_id": session.id, "user_id": session.user_id}},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired.")

    idle_delta = timedelta(seconds=settings.session_idle_timeout)
    if now > (last_active + idle_delta):
        auth_service.revoke_session(db, session, at=now)
        logger.info(
            "session_expired_idle",
            extra={"event": "auth.session.expired_idle", "fields": {"session_id": session.id, "user_id": session.user_id}},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired.")

    session.last_active_at = now
    db.commit()
    db.refresh(session)
    return session


def get_current_user(current_session: SessionToken = Depends(get_current_session)) -> User:
    user = current_session.user
    if user is None:
        logger.info("invalid_session_user", extra={"event": "auth.session.invalid_user", "fields": {"session_id": current_session.id}})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session user.")
    if not user.is_active:
        logger.info("inactive_account", extra={"event": "auth.user.inactive", "fields": {"user_id": user.id}})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is inactive.")
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    return current_user
