from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_current_session, get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.user import SessionToken, User
from app.schemas.auth import ChangePasswordRequest, LoginRequest, LoginResponse, MeResponse, MessageResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    raw_token, session = auth_service.login(db, payload.username, payload.password)
    idle_expiry = session.last_active_at + timedelta(seconds=settings.session_idle_timeout)
    return LoginResponse(token=raw_token, idle_expires_at=idle_expiry, absolute_expires_at=session.absolute_expires_at)


@router.post("/logout", response_model=MessageResponse)
def logout(current_session: SessionToken = Depends(get_current_session), db: Session = Depends(get_db)) -> MessageResponse:
    auth_service.logout(db, current_session)
    return MessageResponse(message="Logged out.")


@router.get("/me", response_model=MeResponse)
def me(current_session: SessionToken = Depends(get_current_session), current_user: User = Depends(get_current_user)) -> MeResponse:
    idle_expires_at = current_session.last_active_at + timedelta(seconds=settings.session_idle_timeout)
    return MeResponse(
        id=current_user.id,
        username=current_user.username,
        role=current_user.role.value,
        session_idle_expires_at=idle_expires_at,
        session_absolute_expires_at=current_session.absolute_expires_at,
    )


@router.post("/password/change", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    auth_service.change_password(db, current_user, payload.current_password, payload.new_password)
    return MessageResponse(message="Password updated.")
