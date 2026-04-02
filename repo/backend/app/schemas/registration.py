from datetime import datetime

from pydantic import BaseModel


class CourseListItem(BaseModel):
    id: int
    code: str
    title: str
    credits: int
    available_seats: int


class CourseDetail(BaseModel):
    id: int
    code: str
    title: str
    credits: int
    prerequisites: list[str]
    sections: list[dict]


class EligibilityResponse(BaseModel):
    eligible: bool
    reasons: list[str]


class EnrollRequest(BaseModel):
    section_id: int


class WaitlistRequest(BaseModel):
    section_id: int


class DropRequest(BaseModel):
    section_id: int


class RegistrationStatusItem(BaseModel):
    section_id: int
    course_code: str
    status: str


class HistoryItem(BaseModel):
    id: int
    section_id: int
    event_type: str
    details: str | None
    created_at: datetime
