from datetime import datetime, timezone
import csv
import hashlib
import io
from statistics import median

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.authz import can_access_section
from app.core.config import settings
from app.models.admin import Course, Section
from app.models.registration import Enrollment, EnrollmentStatus
from app.models.review import (
    IdentityMode,
    OutlierFlag,
    RecheckRequest,
    RecheckStatus,
    ReviewRound,
    ReviewRoundStatus,
    ReviewerAssignment,
    Score,
    ScoringForm,
)
from app.models.user import User, UserRole
from app.services import registration_service


def _get_round(db: Session, round_id: int) -> ReviewRound:
    round_obj = db.query(ReviewRound).filter(ReviewRound.id == round_id).first()
    if round_obj is None:
        raise HTTPException(status_code=404, detail="Review round not found.")
    return round_obj


def _section_organization_id(db: Session, section_id: int) -> int | None:
    row = (
        db.query(Course.organization_id)
        .join(Section, Section.course_id == Course.id)
        .filter(Section.id == section_id)
        .first()
    )
    return int(row[0]) if row is not None else None


def get_scoring_form(db: Session, form_id: int) -> ScoringForm:
    form = db.query(ScoringForm).filter(ScoringForm.id == form_id).first()
    if form is None:
        raise HTTPException(status_code=404, detail="Scoring form not found.")
    return form


def ensure_form_matches_section_org(db: Session, form: ScoringForm, section_id: int) -> None:
    section_org_id = _section_organization_id(db, section_id)
    if section_org_id is None:
        raise HTTPException(status_code=404, detail="Section not found.")
    if form.organization_id is None or int(form.organization_id) != section_org_id:
        raise HTTPException(status_code=403, detail="Scoring form is outside the section organization scope.")


def ensure_round_form_scope(db: Session, round_obj: ReviewRound) -> ScoringForm:
    form = get_scoring_form(db, round_obj.scoring_form_id)
    ensure_form_matches_section_org(db, form, round_obj.section_id)
    return form


def _is_reporting_line_conflict(reviewer: User, student: User) -> bool:
    return reviewer.reports_to == student.id or student.reports_to == reviewer.id


def _check_coi(db: Session, round_obj: ReviewRound, reviewer_id: int, student_id: int) -> None:
    reviewer = db.query(User).filter(User.id == reviewer_id).first()
    student = db.query(User).filter(User.id == student_id).first()
    if reviewer is None or student is None:
        raise HTTPException(status_code=404, detail="Reviewer or student not found.")
    section = db.query(Section).filter(Section.id == round_obj.section_id).first()
    if section and section.instructor_id == reviewer_id:
        raise HTTPException(status_code=409, detail="Conflict of interest: same section instructor.")
    if _is_reporting_line_conflict(reviewer, student) or registration_service._has_management_conflict(db, reviewer_id, student_id):
        raise HTTPException(status_code=409, detail="Conflict of interest: reporting line conflict.")
    if reviewer_id == student_id:
        raise HTTPException(status_code=409, detail="Conflict of interest: self review is not allowed.")
    same_section_enrollment = (
        db.query(Enrollment.id)
        .filter(
            Enrollment.section_id == round_obj.section_id,
            Enrollment.student_id.in_([reviewer_id, student_id]),
            Enrollment.status.in_([EnrollmentStatus.enrolled, EnrollmentStatus.completed]),
        )
        .count()
    )
    if same_section_enrollment >= 2:
        raise HTTPException(status_code=409, detail="Conflict of interest: reviewer and student are in the same section.")


def _get_assignment_reviewer(db: Session, reviewer_id: int) -> User:
    reviewer = db.query(User).filter(User.id == reviewer_id).first()
    if reviewer is None:
        raise HTTPException(status_code=404, detail="Reviewer not found.")
    if reviewer.role != UserRole.reviewer:
        raise HTTPException(status_code=422, detail="Assigned reviewer must have REVIEWER role.")
    if not reviewer.is_active:
        raise HTTPException(status_code=422, detail="Assigned reviewer must be active.")
    return reviewer


def _get_assignment_student(db: Session, round_obj: ReviewRound, student_id: int) -> User:
    student = db.query(User).filter(User.id == student_id).first()
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found.")
    if student.role != UserRole.student:
        raise HTTPException(status_code=422, detail="Assigned student must have STUDENT role.")
    enrollment = (
        db.query(Enrollment.id)
        .filter(
            Enrollment.student_id == student_id,
            Enrollment.section_id == round_obj.section_id,
            Enrollment.status.in_([EnrollmentStatus.enrolled, EnrollmentStatus.completed]),
        )
        .first()
    )
    if enrollment is None:
        raise HTTPException(status_code=422, detail="Assigned student is not enrolled in the review round section.")
    return student


def _reviewer_is_eligible_for_round(db: Session, reviewer: User, round_obj: ReviewRound) -> bool:
    if can_access_section(db, reviewer, round_obj.section_id):
        return True
    same_section_membership = (
        db.query(Enrollment.id)
        .filter(
            Enrollment.student_id == reviewer.id,
            Enrollment.section_id == round_obj.section_id,
            Enrollment.status.in_([EnrollmentStatus.enrolled, EnrollmentStatus.completed]),
        )
        .first()
    )
    return same_section_membership is not None


def validate_assignment_participants(db: Session, round_obj: ReviewRound, reviewer_id: int, student_id: int) -> tuple[User, User]:
    reviewer = _get_assignment_reviewer(db, reviewer_id)
    if not _reviewer_is_eligible_for_round(db, reviewer, round_obj):
        raise HTTPException(status_code=403, detail="Assigned reviewer is outside the review round scope.")
    student = _get_assignment_student(db, round_obj, student_id)
    return reviewer, student


def create_manual_assignment(db: Session, round_obj: ReviewRound, reviewer_id: int, student_id: int) -> ReviewerAssignment:
    ensure_round_form_scope(db, round_obj)
    validate_assignment_participants(db, round_obj, reviewer_id, student_id)
    _check_coi(db, round_obj, reviewer_id, student_id)
    existing = (
        db.query(ReviewerAssignment)
        .filter(
            ReviewerAssignment.round_id == round_obj.id,
            ReviewerAssignment.reviewer_id == reviewer_id,
            ReviewerAssignment.student_id == student_id,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Assignment already exists.")
    assignment = ReviewerAssignment(
        round_id=round_obj.id,
        reviewer_id=reviewer_id,
        student_id=student_id,
        section_id=round_obj.section_id,
        assigned_manually=True,
    )
    db.add(assignment)
    db.flush()
    return assignment


def auto_assign_reviewers(db: Session, round_obj: ReviewRound, student_ids: list[int], reviewers_per_student: int) -> list[ReviewerAssignment]:
    ensure_round_form_scope(db, round_obj)
    all_reviewers = db.query(User).filter(User.role == UserRole.reviewer, User.is_active.is_(True)).all()
    if not all_reviewers:
        raise HTTPException(status_code=422, detail="No active reviewers available.")
    reviewers = [row for row in all_reviewers if _reviewer_is_eligible_for_round(db, row, round_obj)]
    if not reviewers:
        raise HTTPException(status_code=403, detail="No reviewers are authorized for the review round scope.")

    validated_students = []
    for student_id in student_ids:
        _get_assignment_student(db, round_obj, student_id)
        validated_students.append(student_id)

    created_assignments: list[ReviewerAssignment] = []
    pointer = 0
    for student_id in validated_students:
        assigned_for_student = 0
        tried = 0
        while assigned_for_student < reviewers_per_student and tried < len(reviewers) * 3:
            reviewer = reviewers[pointer % len(reviewers)]
            pointer += 1
            tried += 1
            try:
                validate_assignment_participants(db, round_obj, reviewer.id, student_id)
                _check_coi(db, round_obj, reviewer.id, student_id)
            except HTTPException:
                continue
            exists = (
                db.query(ReviewerAssignment)
                .filter(
                    ReviewerAssignment.round_id == round_obj.id,
                    ReviewerAssignment.reviewer_id == reviewer.id,
                    ReviewerAssignment.student_id == student_id,
                )
                .first()
            )
            if exists:
                continue
            assignment = ReviewerAssignment(
                round_id=round_obj.id,
                reviewer_id=reviewer.id,
                student_id=student_id,
                section_id=round_obj.section_id,
                assigned_manually=False,
            )
            db.add(assignment)
            db.flush()
            created_assignments.append(assignment)
            assigned_for_student += 1
        if assigned_for_student < reviewers_per_student:
            raise HTTPException(status_code=409, detail=f"Insufficient eligible reviewers for student {student_id} due to conflicts.")
    return created_assignments


def _calculate_total_score(form: ScoringForm, criterion_scores: dict[str, float]) -> float:
    criteria = form.criteria or []
    if not criteria:
        raise HTTPException(status_code=422, detail="Scoring form has no criteria.")
    total_weight = sum(float(item.get("weight", 0)) for item in criteria)
    if total_weight <= 0:
        raise HTTPException(status_code=422, detail="Scoring form weights must be positive.")

    aggregate = 0.0
    for item in criteria:
        name = item.get("name")
        weight = float(item.get("weight", 0))
        min_value = float(item.get("min", 0))
        max_value = float(item.get("max", 5))
        if name not in criterion_scores:
            raise HTTPException(status_code=422, detail=f"Missing criterion score: {name}")
        value = float(criterion_scores[name])
        if value < min_value or value > max_value:
            raise HTTPException(status_code=422, detail=f"Score out of range for criterion: {name}")
        aggregate += value * weight

    return round(aggregate / total_weight, 4)


def _evaluate_outliers(db: Session, round_id: int, student_id: int) -> None:
    score_rows = (
        db.query(Score)
        .join(ReviewerAssignment, Score.assignment_id == ReviewerAssignment.id)
        .filter(ReviewerAssignment.round_id == round_id, ReviewerAssignment.student_id == student_id)
        .all()
    )
    if len(score_rows) < 2:
        return
    totals = [row.total_score for row in score_rows]
    med = float(median(totals))
    for score_row in score_rows:
        deviation = abs(score_row.total_score - med)
        if deviation >= 2.0:
            exists = db.query(OutlierFlag).filter(OutlierFlag.score_id == score_row.id, OutlierFlag.resolved.is_(False)).first()
            if exists is None:
                db.add(
                    OutlierFlag(
                        round_id=round_id,
                        student_id=student_id,
                        score_id=score_row.id,
                        median_score=med,
                        deviation=deviation,
                        resolved=False,
                    )
                )


def mask_assignment_for_view(mode: IdentityMode, assignment: ReviewerAssignment, requester: User) -> dict:
    student_id = assignment.student_id
    student_ref = None
    if requester.role == UserRole.reviewer:
        if mode == IdentityMode.blind:
            student_id = None
        elif mode == IdentityMode.semi_blind:
            student_id = None
            canonical = f"{assignment.round_id}:{assignment.student_id}:{settings.secret_key}"
            student_ref = f"SR-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:8].upper()}"
    return {
        "id": assignment.id,
        "round_id": assignment.round_id,
        "reviewer_id": assignment.reviewer_id,
        "student_id": student_id,
        "student_ref": student_ref,
        "section_id": assignment.section_id,
        "assigned_manually": assignment.assigned_manually,
    }


def export_round_scores(db: Session, round_id: int, export_format: str) -> str:
    rows = (
        db.query(Score, ReviewerAssignment)
        .join(ReviewerAssignment, Score.assignment_id == ReviewerAssignment.id)
        .filter(ReviewerAssignment.round_id == round_id)
        .all()
    )
    payload = [
        {
            "score_id": score.id,
            "assignment_id": assignment.id,
            "reviewer_id": assignment.reviewer_id,
            "student_id": assignment.student_id,
            "total_score": score.total_score,
            "submitted_at": score.submitted_at.isoformat() if score.submitted_at else None,
            "criterion_scores": score.criterion_scores,
            "comment": score.comment,
        }
        for score, assignment in rows
    ]
    if export_format == "json":
        import json

        return json.dumps(payload, default=str)
    if export_format == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(
            buf,
            fieldnames=["score_id", "assignment_id", "reviewer_id", "student_id", "total_score", "submitted_at", "comment"],
        )
        writer.writeheader()
        for item in payload:
            writer.writerow({k: item[k] for k in writer.fieldnames})
        return buf.getvalue()
    raise HTTPException(status_code=422, detail="Unsupported export format.")


def ensure_round_closable(db: Session, round_obj: ReviewRound) -> None:
    unresolved = db.query(OutlierFlag).filter(OutlierFlag.round_id == round_obj.id, OutlierFlag.resolved.is_(False)).count()
    if unresolved > 0:
        raise HTTPException(status_code=409, detail="Cannot close round with unresolved outlier flags.")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
