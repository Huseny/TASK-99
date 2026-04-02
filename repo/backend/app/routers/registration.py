from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.admin import Course, Section
from app.models.registration import Enrollment, EnrollmentStatus, RegistrationHistory
from app.models.user import User
from app.schemas.registration import (
    CourseDetail,
    CourseListItem,
    DropRequest,
    EligibilityResponse,
    EnrollRequest,
    HistoryItem,
    RegistrationStatusItem,
    WaitlistRequest,
)
from app.services import registration_service

router = APIRouter(tags=["courses-registration"])


@router.get("/courses", response_model=list[CourseListItem])
def list_courses(db: Session = Depends(get_db)):
    rows = db.query(Course).order_by(Course.id.asc()).all()
    result: list[CourseListItem] = []
    for course in rows:
        sections = db.query(Section).filter(Section.course_id == course.id).all()
        capacity_total = sum(section.capacity for section in sections)
        enrolled = (
            db.query(Enrollment)
            .join(Section, Enrollment.section_id == Section.id)
            .filter(Section.course_id == course.id, Enrollment.status == EnrollmentStatus.enrolled)
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
def get_course(course_id: int, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found.")
    sections = db.query(Section).filter(Section.course_id == course.id).all()
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
    reasons = registration_service.check_eligibility(db, user, course_id, section_id)
    return EligibilityResponse(eligible=len(reasons) == 0, reasons=reasons)


@router.post("/registration/enroll")
def enroll(
    payload: EnrollRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required.")
    code, response = registration_service.enroll(db, user, payload.section_id, idempotency_key)
    return JSONResponse(content=response, status_code=code)


@router.post("/registration/waitlist")
def waitlist(payload: WaitlistRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return registration_service.join_waitlist(db, user, payload.section_id)


@router.post("/registration/drop")
def drop(
    payload: DropRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required.")
    code, response = registration_service.drop(db, user, payload.section_id, idempotency_key)
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
