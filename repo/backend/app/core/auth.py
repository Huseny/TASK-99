from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import token_hash
from app.models.user import SessionToken, User, UserRole

bearer_scheme = HTTPBearer(auto_error=False)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> SessionToken:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    session = db.query(SessionToken).filter(SessionToken.token_hash == token_hash(credentials.credentials)).first()
    if session is None or session.revoked:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session.")

    now = _utcnow()
    last_active = session.last_active_at
    if last_active.tzinfo is None:
        last_active = last_active.replace(tzinfo=timezone.utc)

    absolute_expiry = session.absolute_expires_at
    if absolute_expiry.tzinfo is None:
        absolute_expiry = absolute_expiry.replace(tzinfo=timezone.utc)

    if now > absolute_expiry:
        session.revoked = True
        session.revoked_at = now
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired.")

    idle_delta = timedelta(seconds=settings.session_idle_timeout)
    if now > (last_active + idle_delta):
        session.revoked = True
        session.revoked_at = now
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired.")

    session.last_active_at = now
    db.commit()
    db.refresh(session)
    return session


def get_current_user(current_session: SessionToken = Depends(get_current_session)) -> User:
    user = current_session.user
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is inactive.")
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    return current_user
