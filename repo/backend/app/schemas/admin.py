from datetime import datetime

from pydantic import BaseModel, Field


class OrganizationIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    code: str = Field(min_length=2, max_length=30)
    is_active: bool = True


class OrganizationOut(OrganizationIn):
    id: int


class TermIn(BaseModel):
    organization_id: int
    name: str
    starts_on: str
    ends_on: str
    is_active: bool = True


class TermOut(TermIn):
    id: int


class CourseIn(BaseModel):
    organization_id: int
    code: str
    title: str
    credits: int = Field(ge=0, le=12)
    prerequisites: list[str] = Field(default_factory=list)


class CourseOut(CourseIn):
    id: int


class SectionIn(BaseModel):
    course_id: int
    term_id: int
    code: str
    instructor_id: int | None = None
    capacity: int = Field(ge=1, le=5000)


class SectionOut(SectionIn):
    id: int


class RegistrationRoundIn(BaseModel):
    term_id: int
    name: str
    starts_at: datetime
    ends_at: datetime
    is_active: bool = True


class RegistrationRoundOut(RegistrationRoundIn):
    id: int


class UserCreateIn(BaseModel):
    username: str
    password: str
    role: str
    is_active: bool = True
    org_id: int | None = None
    reports_to: int | None = None


class UserUpdateIn(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    org_id: int | None = None
    reports_to: int | None = None


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    org_id: int | None
    reports_to: int | None


class AuditLogOut(BaseModel):
    id: int
    actor_id: int | None
    action: str
    entity_name: str
    entity_id: int | None
    before_hash: str | None
    after_hash: str | None
    created_at: datetime


class ScopeGrantIn(BaseModel):
    user_id: int
    scope_type: str
    scope_id: int


class ScopeGrantOut(BaseModel):
    id: int
    user_id: int
    scope_type: str
    scope_id: int
    created_at: datetime


class AuditRetentionRunOut(BaseModel):
    archived_count: int
    purged_count: int
    cutoff_iso: str
