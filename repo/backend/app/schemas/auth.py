from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    token: str
    idle_expires_at: datetime
    absolute_expires_at: datetime


class MeResponse(BaseModel):
    id: int
    username: str
    role: str
    session_idle_expires_at: datetime
    session_absolute_expires_at: datetime


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class MessageResponse(BaseModel):
    message: str
