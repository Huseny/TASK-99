from datetime import datetime, timezone
import hashlib
import json

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.admin import Course, RegistrationRound, Section, Term
from app.models.registration import AddDropRequest, Enrollment, EnrollmentStatus, RegistrationHistory, WaitlistEntry
from app.models.user import User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _request_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _record_history(db: Session, student_id: int, section_id: int, event_type: str, details: str | None = None) -> None:
    db.add(RegistrationHistory(student_id=student_id, section_id=section_id, event_type=event_type, details=details))


def active_round_for_term(db: Session, term_id: int) -> RegistrationRound | None:
    now = _utcnow()
    rounds = db.query(RegistrationRound).filter(RegistrationRound.term_id == term_id, RegistrationRound.is_active.is_(True)).all()
    for round_item in rounds:
        starts = round_item.starts_at if round_item.starts_at.tzinfo else round_item.starts_at.replace(tzinfo=timezone.utc)
        ends = round_item.ends_at if round_item.ends_at.tzinfo else round_item.ends_at.replace(tzinfo=timezone.utc)
        if starts <= now <= ends:
            return round_item
    return None


def check_eligibility(db: Session, student: User, course_id: int, section_id: int) -> list[str]:
    reasons: list[str] = []
    course = db.query(Course).filter(Course.id == course_id).first()
    section = db.query(Section).filter(Section.id == section_id, Section.course_id == course_id).first()
    if course is None or section is None:
        return ["Course or section not found."]

    term = db.query(Term).filter(Term.id == section.term_id).first()
    if term is None:
        reasons.append("Section term is invalid.")
    else:
        if active_round_for_term(db, term.id) is None:
            reasons.append("No active registration round for this section.")

    for prereq_code in course.prerequisites or []:
        completed = (
            db.query(Enrollment)
            .join(Section, Enrollment.section_id == Section.id)
            .join(Course, Section.course_id == Course.id)
            .filter(Enrollment.student_id == student.id, Enrollment.status == EnrollmentStatus.completed, Course.code == prereq_code)
            .first()
        )
        if completed is None:
            reasons.append(f"Missing prerequisite: {prereq_code}.")

    return reasons


def _current_enrolled_count(db: Session, section_id: int) -> int:
    return (
        db.query(func.count(Enrollment.id))
        .filter(Enrollment.section_id == section_id, Enrollment.status == EnrollmentStatus.enrolled)
        .scalar()
    )


def _consume_waitlist_if_seat_available(db: Session, section_id: int) -> None:
    section = db.query(Section).filter(Section.id == section_id).first()
    if section is None:
        return
    while _current_enrolled_count(db, section_id) < section.capacity:
        next_wait = db.query(WaitlistEntry).filter(WaitlistEntry.section_id == section_id).order_by(WaitlistEntry.priority.asc()).first()
        if next_wait is None:
            break
        enrollment = (
            db.query(Enrollment)
            .filter(Enrollment.student_id == next_wait.student_id, Enrollment.section_id == section_id)
            .first()
        )
        if enrollment is None:
            enrollment = Enrollment(student_id=next_wait.student_id, section_id=section_id, status=EnrollmentStatus.enrolled)
            db.add(enrollment)
        else:
            enrollment.status = EnrollmentStatus.enrolled
        _record_history(db, next_wait.student_id, section_id, "WAITLIST_BACKFILLED", "Auto promoted from waitlist")
        db.delete(next_wait)


def enroll(db: Session, student: User, section_id: int, idempotency_key: str) -> tuple[int, dict]:
    payload = {"section_id": section_id}
    hash_value = _request_hash(payload)
    existing_request = (
        db.query(AddDropRequest)
        .filter(AddDropRequest.actor_id == student.id, AddDropRequest.operation == "ENROLL", AddDropRequest.idempotency_key == idempotency_key)
        .first()
    )
    if existing_request is not None:
        if existing_request.request_hash != hash_value:
            raise HTTPException(status_code=409, detail="Idempotency key conflict for different request payload.")
        return existing_request.response_code, json.loads(existing_request.response_body)

    section = db.query(Section).filter(Section.id == section_id).with_for_update().first()
    if section is None:
        raise HTTPException(status_code=404, detail="Section not found.")
    reasons = check_eligibility(db, student, section.course_id, section_id)
    if reasons:
        raise HTTPException(status_code=422, detail={"eligible": False, "reasons": reasons})

    existing = db.query(Enrollment).filter(Enrollment.student_id == student.id, Enrollment.section_id == section_id).first()
    if existing and existing.status == EnrollmentStatus.enrolled:
        response = {"status": "already_enrolled", "section_id": section_id}
        code = 200
    elif _current_enrolled_count(db, section_id) >= section.capacity:
        code = 409
        response = {"status": "full", "section_id": section_id}
    else:
        if existing is None:
            db.add(Enrollment(student_id=student.id, section_id=section_id, status=EnrollmentStatus.enrolled))
        else:
            existing.status = EnrollmentStatus.enrolled
        _record_history(db, student.id, section_id, "ENROLLED")
        code = 200
        response = {"status": "enrolled", "section_id": section_id}

    db.add(
        AddDropRequest(
            actor_id=student.id,
            operation="ENROLL",
            idempotency_key=idempotency_key,
            request_hash=hash_value,
            response_code=code,
            response_body=json.dumps(response),
        )
    )
    db.commit()
    return code, response


def join_waitlist(db: Session, student: User, section_id: int) -> dict:
    section = db.query(Section).filter(Section.id == section_id).first()
    if section is None:
        raise HTTPException(status_code=404, detail="Section not found.")
    existing = db.query(WaitlistEntry).filter(WaitlistEntry.student_id == student.id, WaitlistEntry.section_id == section_id).first()
    if existing is not None:
        return {"status": "already_waitlisted", "section_id": section_id, "priority": existing.priority}
    max_priority = db.query(func.max(WaitlistEntry.priority)).filter(WaitlistEntry.section_id == section_id).scalar()
    priority = int(max_priority or 0) + 1
    db.add(WaitlistEntry(student_id=student.id, section_id=section_id, priority=priority))
    _record_history(db, student.id, section_id, "WAITLIST_JOINED", f"priority={priority}")
    db.commit()
    return {"status": "waitlisted", "section_id": section_id, "priority": priority}


def drop(db: Session, student: User, section_id: int, idempotency_key: str) -> tuple[int, dict]:
    payload = {"section_id": section_id}
    hash_value = _request_hash(payload)
    existing_request = (
        db.query(AddDropRequest)
        .filter(AddDropRequest.actor_id == student.id, AddDropRequest.operation == "DROP", AddDropRequest.idempotency_key == idempotency_key)
        .first()
    )
    if existing_request is not None:
        if existing_request.request_hash != hash_value:
            raise HTTPException(status_code=409, detail="Idempotency key conflict for different request payload.")
        return existing_request.response_code, json.loads(existing_request.response_body)

    enrollment = (
        db.query(Enrollment)
        .filter(Enrollment.student_id == student.id, Enrollment.section_id == section_id, Enrollment.status == EnrollmentStatus.enrolled)
        .first()
    )
    if enrollment is None:
        code = 404
        response = {"status": "not_enrolled", "section_id": section_id}
    else:
        enrollment.status = EnrollmentStatus.dropped
        _record_history(db, student.id, section_id, "DROPPED")
        db.flush()
        _consume_waitlist_if_seat_available(db, section_id)
        code = 200
        response = {"status": "dropped", "section_id": section_id}

    db.add(
        AddDropRequest(
            actor_id=student.id,
            operation="DROP",
            idempotency_key=idempotency_key,
            request_hash=hash_value,
            response_code=code,
            response_body=json.dumps(response),
        )
    )
    db.commit()
    return code, response
