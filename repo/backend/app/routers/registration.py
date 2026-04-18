import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.authz import can_access_section, require_section_access
from app.core.database import get_db
from app.models.admin import Course, Section
from app.models.registration import Enrollment, EnrollmentStatus, RegistrationHistory
from app.models.user import User, UserRole
from app.schemas.registration import (
    CourseDetail,
    CourseListItem,
    DropRequest,
    EligibilityResponse,
    EnrollRequest,
    HistoryItem,
    RegistrationStatusItem,
    RosterAddRequest,
    RosterItem,
    RosterRemoveRequest,
    WaitlistRequest,
)
from app.services import registration_service

router = APIRouter(tags=["courses-registration"])


def _require_student(user: User) -> None:
    if user.role != UserRole.student:
        raise HTTPException(status_code=403, detail="Student access required.")


@router.get("/courses", response_model=list[CourseListItem])
def list_courses(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Course).order_by(Course.id.asc()).all()
    result: list[CourseListItem] = []
    for course in rows:
        sections = [section for section in db.query(Section).filter(Section.course_id == course.id).all() if can_access_section(db, user, section.id)]
        if not sections:
            continue
        capacity_total = sum(section.capacity for section in sections)
        enrolled = (
            db.query(Enrollment)
            .join(Section, Enrollment.section_id == Section.id)
            .filter(
                Section.id.in_([section.id for section in sections]),
                Enrollment.status == EnrollmentStatus.enrolled,
            )
            .count()
        )
        result.append(
            CourseListItem(
                id=course.id,
                code=course.code,
                title=course.title,
                credits=course.credits,
                available_seats=max(0, capacity_total - enrolled),
            )
        )
    return result


@router.get("/courses/{course_id}", response_model=CourseDetail)
def get_course(course_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found.")
    sections = [section for section in db.query(Section).filter(Section.course_id == course.id).all() if can_access_section(db, user, section.id)]
    if not sections:
        raise HTTPException(status_code=403, detail="Access denied for requested course.")
    return CourseDetail(
        id=course.id,
        code=course.code,
        title=course.title,
        credits=course.credits,
        prerequisites=course.prerequisites or [],
        sections=[{"id": s.id, "code": s.code, "capacity": s.capacity, "term_id": s.term_id} for s in sections],
    )


@router.get("/courses/{course_id}/sections/{section_id}/eligibility", response_model=EligibilityResponse)
def eligibility(course_id: int, section_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_section_access(db, user, section_id)
    reasons = registration_service.check_eligibility(db, user, course_id, section_id)
    return EligibilityResponse(eligible=len(reasons) == 0, reasons=reasons)


@router.post("/registration/enroll")
def enroll(
    payload: EnrollRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    _require_student(user)
    # Idempotency-Key is optional: when a client provides one they get
    # at-most-once semantics via cached-response replay; when they don't, we
    # mint a fresh key so the request can still proceed. Race-safety still
    # relies on row-level locking inside `registration_service.enroll`.
    key = idempotency_key or f"auto-{uuid.uuid4().hex}"
    require_section_access(db, user, payload.section_id)
    code, response = registration_service.enroll(db, user, payload.section_id, key)
    return JSONResponse(content=response, status_code=code)


@router.post("/registration/waitlist")
def waitlist(payload: WaitlistRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_student(user)
    require_section_access(db, user, payload.section_id)
    return registration_service.join_waitlist(db, user, payload.section_id)


@router.post("/registration/drop")
def drop(
    payload: DropRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    _require_student(user)
    key = idempotency_key or f"auto-{uuid.uuid4().hex}"
    require_section_access(db, user, payload.section_id)
    code, response = registration_service.drop(db, user, payload.section_id, key)
    return JSONResponse(content=response, status_code=code)


@router.get("/registration/status", response_model=list[RegistrationStatusItem])
def registration_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (
        db.query(Enrollment, Section, Course)
        .join(Section, Enrollment.section_id == Section.id)
        .join(Course, Section.course_id == Course.id)
        .filter(Enrollment.student_id == user.id)
        .all()
    )
    return [
        RegistrationStatusItem(section_id=section.id, course_code=course.code, status=enrollment.status.value)
        for enrollment, section, course in rows
    ]


@router.get("/registration/history", response_model=list[HistoryItem])
def registration_history(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (
        db.query(RegistrationHistory)
        .filter(RegistrationHistory.student_id == user.id)
        .order_by(RegistrationHistory.id.desc())
        .all()
    )
    return [
        HistoryItem(id=row.id, section_id=row.section_id, event_type=row.event_type, details=row.details, created_at=row.created_at)
        for row in rows
    ]


@router.get("/sections/{section_id}/roster", response_model=list[RosterItem])
def section_roster(section_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [RosterItem(**row) for row in registration_service.list_roster(db, user, section_id)]


@router.post("/sections/{section_id}/roster")
def add_roster_student(
    section_id: int,
    payload: RosterAddRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if payload.student_id <= 0:
        raise HTTPException(status_code=422, detail="student_id must be positive.")
    return registration_service.add_student_to_roster(db, user, section_id, payload.student_id)


@router.delete("/sections/{section_id}/roster/{student_id}")
def remove_roster_student(section_id: int, student_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if student_id <= 0:
        raise HTTPException(status_code=422, detail="student_id must be positive.")
    return registration_service.remove_student_from_roster(db, user, section_id, student_id)
