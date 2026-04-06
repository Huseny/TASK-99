from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.auth import get_current_user
from app.core.authz import require_form_access, require_organization_access, require_section_access
from app.core.database import get_db
from app.core.logging import get_logger
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
from app.schemas.review import (
    AssignmentOut,
    AutoAssignmentIn,
    ManualAssignmentIn,
    OutlierOut,
    RecheckAssignIn,
    RecheckCreateIn,
    ReviewRoundCreate,
    ReviewRoundOut,
    ScoreOut,
    ScoreSubmitIn,
    ScoringFormCreate,
)
from app.services import data_quality_service, messaging_service, review_service

router = APIRouter(prefix="/reviews", tags=["reviews"])
logger = get_logger("app.reviews")


def _ensure_instructor_or_admin(user: User) -> None:
    if user.role not in {UserRole.instructor, UserRole.admin}:
        raise HTTPException(status_code=403, detail="Instructor or admin access required.")


def _ensure_round_scope(db: Session, user: User, round_obj: ReviewRound) -> None:
    if user.role == UserRole.admin:
        return
    require_section_access(db, user, round_obj.section_id)


def _enforce_review_write_quality(entity_type: str, payload: dict, db: Session) -> None:
    rules: dict[str, dict] = {
        "ReviewFormWrite": {
            "required_fields": ["name", "criteria_count"],
            "ranges": {"criteria_count": {"min": 1, "max": 50}},
            "unique_keys": ["name"],
        },
        "ReviewRoundWrite": {
            "required_fields": ["name", "term_id", "section_id", "scoring_form_id", "identity_mode"],
            "ranges": {},
            "unique_keys": ["name"],
        },
    }
    spec = rules[entity_type]
    data_quality_service.enforce_write_quality(
        db,
        entity_type=entity_type,
        payload=payload,
        required_fields=spec["required_fields"],
        ranges=spec["ranges"],
        unique_keys=spec["unique_keys"],
    )


@router.post("/forms")
def create_scoring_form(payload: ScoringFormCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _ensure_instructor_or_admin(user)
    if user.role != UserRole.admin:
        require_organization_access(db, user, payload.organization_id)
    _enforce_review_write_quality(
        "ReviewFormWrite",
        {"name": payload.name, "criteria_count": len(payload.criteria), "organization_id": payload.organization_id},
        db,
    )
    form = ScoringForm(name=payload.name, criteria=payload.criteria, organization_id=payload.organization_id)
    db.add(form)
    db.flush()
    write_audit_log(
        db,
        actor_id=user.id,
        action="review.form.create",
        entity_name="ScoringForm",
        entity_id=form.id,
        before=None,
        after={"id": form.id, "name": form.name, "organization_id": form.organization_id},
    )
    db.commit()
    return {"id": form.id, "name": form.name, "organization_id": form.organization_id}


@router.post("/rounds", response_model=ReviewRoundOut)
def create_round(payload: ReviewRoundCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _ensure_instructor_or_admin(user)
    require_section_access(db, user, payload.section_id)
    require_form_access(db, user, payload.scoring_form_id)
    _enforce_review_write_quality("ReviewRoundWrite", payload.model_dump(), db)
    form = review_service.get_scoring_form(db, payload.scoring_form_id)
    review_service.ensure_form_matches_section_org(db, form, payload.section_id)
    mode = IdentityMode(payload.identity_mode)
    round_obj = ReviewRound(
        name=payload.name,
        term_id=payload.term_id,
        section_id=payload.section_id,
        scoring_form_id=payload.scoring_form_id,
        identity_mode=mode,
        status=ReviewRoundStatus.active,
        created_by=user.id,
    )
    db.add(round_obj)
    db.flush()
    write_audit_log(
        db,
        actor_id=user.id,
        action="review.round.create",
        entity_name="ReviewRound",
        entity_id=round_obj.id,
        before=None,
        after={"id": round_obj.id, "name": round_obj.name, "status": round_obj.status.value},
    )
    db.commit()
    return ReviewRoundOut(
        id=round_obj.id,
        name=round_obj.name,
        term_id=round_obj.term_id,
        section_id=round_obj.section_id,
        scoring_form_id=round_obj.scoring_form_id,
        identity_mode=round_obj.identity_mode.value,
        status=round_obj.status.value,
    )


@router.post("/rounds/{round_id}/assignments/manual", response_model=AssignmentOut)
def manual_assign(
    round_id: int,
    payload: ManualAssignmentIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _ensure_instructor_or_admin(user)
    round_obj = review_service._get_round(db, round_id)
    _ensure_round_scope(db, user, round_obj)
    review_service.ensure_round_form_scope(db, round_obj)
    assignment = review_service.create_manual_assignment(db, round_obj, payload.reviewer_id, payload.student_id)
    messaging_service.dispatch_notifications(
        db,
        actor=user,
        trigger_type="ASSIGNMENT_POSTED",
        title=f"Assignment posted: {round_obj.name}",
        message="A new assignment has been posted for your review cycle.",
        recipient_ids=[payload.student_id],
        metadata={"round_id": round_obj.id, "section_id": round_obj.section_id, "assignment_id": assignment.id},
    )
    write_audit_log(
        db,
        actor_id=user.id,
        action="review.assignment.manual.create",
        entity_name="ReviewerAssignment",
        entity_id=assignment.id,
        before=None,
        after={
            "id": assignment.id,
            "round_id": assignment.round_id,
            "reviewer_id": assignment.reviewer_id,
            "student_id": assignment.student_id,
            "section_id": assignment.section_id,
            "assigned_manually": assignment.assigned_manually,
        },
    )
    db.commit()
    return AssignmentOut(
        id=assignment.id,
        round_id=assignment.round_id,
        reviewer_id=assignment.reviewer_id,
        student_id=assignment.student_id,
        section_id=assignment.section_id,
        assigned_manually=assignment.assigned_manually,
    )


@router.post("/rounds/{round_id}/assignments/auto")
def auto_assign(
    round_id: int,
    payload: AutoAssignmentIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _ensure_instructor_or_admin(user)
    round_obj = review_service._get_round(db, round_id)
    _ensure_round_scope(db, user, round_obj)
    review_service.ensure_round_form_scope(db, round_obj)
    assignments = review_service.auto_assign_reviewers(db, round_obj, payload.student_ids, payload.reviewers_per_student)
    created_ids = [assignment.id for assignment in assignments]
    created = len(created_ids)
    write_audit_log(
        db,
        actor_id=user.id,
        action="review.assignment.auto.create",
        entity_name="ReviewerAssignment",
        entity_id=None,
        before=None,
        after={"created_count": created, "assignment_ids": created_ids, "round_id": round_id},
    )
    if created_ids:
        messaging_service.dispatch_notifications(
            db,
            actor=user,
            trigger_type="ASSIGNMENT_POSTED",
            title=f"Assignments posted: {round_obj.name}",
            message="Your assignment queue has been updated.",
            recipient_ids=payload.student_ids,
            metadata={"round_id": round_obj.id, "section_id": round_obj.section_id, "assignment_ids": created_ids},
        )
    db.commit()
    return {"created_assignments": created}


@router.get("/rounds/{round_id}/assignments", response_model=list[AssignmentOut])
def list_assignments(round_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    round_obj = review_service._get_round(db, round_id)
    query = db.query(ReviewerAssignment).filter(ReviewerAssignment.round_id == round_id)
    if user.role == UserRole.reviewer:
        query = query.filter(ReviewerAssignment.reviewer_id == user.id)
    elif user.role in {UserRole.instructor, UserRole.admin}:
        _ensure_round_scope(db, user, round_obj)
    else:
        raise HTTPException(status_code=403, detail="Forbidden")
    rows = query.order_by(ReviewerAssignment.id.asc()).all()
    return [
        AssignmentOut(**review_service.mask_assignment_for_view(round_obj.identity_mode, row, user))
        for row in rows
    ]


@router.post("/scores", response_model=ScoreOut)
def submit_score(payload: ScoreSubmitIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    assignment = db.query(ReviewerAssignment).filter(ReviewerAssignment.id == payload.assignment_id).first()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    if user.role != UserRole.reviewer or assignment.reviewer_id != user.id:
        raise HTTPException(status_code=403, detail="Cannot submit score for unassigned work.")

    round_obj = review_service._get_round(db, assignment.round_id)
    review_service.ensure_round_form_scope(db, round_obj)
    if round_obj.status == ReviewRoundStatus.closed:
        raise HTTPException(status_code=409, detail="Round is closed.")
    form = review_service.get_scoring_form(db, round_obj.scoring_form_id)

    total = review_service._calculate_total_score(form, payload.criterion_scores)
    existing = db.query(Score).filter(Score.assignment_id == assignment.id).first()
    action = "review.score.update" if existing else "review.score.create"
    before_score = None
    if existing:
        before_score = {
            "id": existing.id,
            "assignment_id": existing.assignment_id,
            "total_score": existing.total_score,
            "comment": existing.comment,
        }
    if existing:
        db.query(Score).filter(Score.id == existing.id).update(
            {
                "criterion_scores": payload.criterion_scores,
                "total_score": total,
                "comment": payload.comment if payload.comment is not None else "",
            }
        )
        db.flush()
        db.refresh(existing)
        score = existing
    else:
        score = Score(
            assignment_id=assignment.id,
            criterion_scores=payload.criterion_scores,
            total_score=total,
            comment=payload.comment if payload.comment is not None else "",
        )
        db.add(score)
        db.flush()

    review_service._evaluate_outliers(db, assignment.round_id, assignment.student_id)
    write_audit_log(
        db,
        actor_id=user.id,
        action=action,
        entity_name="Score",
        entity_id=score.id,
        before=before_score,
        after={
            "id": score.id,
            "assignment_id": score.assignment_id,
            "round_id": assignment.round_id,
            "student_id": assignment.student_id,
            "reviewer_id": assignment.reviewer_id,
            "total_score": score.total_score,
        },
    )
    logger.info(
        "review_score_written",
        extra={
            "event": "reviews.score.written",
            "fields": {
                "action": action,
                "score_id": score.id,
                "assignment_id": assignment.id,
                "round_id": assignment.round_id,
                "reviewer_id": assignment.reviewer_id,
            },
        },
    )
    db.commit()
    db.refresh(score)
    return ScoreOut(id=score.id, assignment_id=score.assignment_id, total_score=score.total_score, submitted_at=score.submitted_at)


@router.get("/rounds/{round_id}/outliers", response_model=list[OutlierOut])
def list_outliers(round_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _ensure_instructor_or_admin(user)
    round_obj = review_service._get_round(db, round_id)
    _ensure_round_scope(db, user, round_obj)
    rows = db.query(OutlierFlag).filter(OutlierFlag.round_id == round_id).order_by(OutlierFlag.id.desc()).all()
    return [
        OutlierOut(
            id=row.id,
            round_id=row.round_id,
            student_id=row.student_id,
            score_id=row.score_id,
            median_score=row.median_score,
            deviation=row.deviation,
            resolved=row.resolved,
        )
        for row in rows
    ]


@router.post("/rounds/{round_id}/outliers/{flag_id}/resolve")
def resolve_outlier(round_id: int, flag_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _ensure_instructor_or_admin(user)
    round_obj = review_service._get_round(db, round_id)
    _ensure_round_scope(db, user, round_obj)
    flag = db.query(OutlierFlag).filter(OutlierFlag.round_id == round_id, OutlierFlag.id == flag_id).first()
    if flag is None:
        raise HTTPException(status_code=404, detail="Outlier flag not found.")
    before = {"id": flag.id, "resolved": flag.resolved}
    flag.resolved = True
    write_audit_log(
        db,
        actor_id=user.id,
        action="review.outlier.resolve",
        entity_name="OutlierFlag",
        entity_id=flag.id,
        before=before,
        after={"id": flag.id, "resolved": flag.resolved},
    )
    db.commit()
    return {"message": "Resolved."}


@router.post("/rechecks")
def create_recheck(payload: RecheckCreateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    round_obj = review_service._get_round(db, payload.round_id)
    if payload.section_id != round_obj.section_id:
        raise HTTPException(status_code=422, detail="Section does not match review round.")

    if user.role == UserRole.student:
        if payload.student_id != user.id:
            raise HTTPException(status_code=403, detail="Students can only request recheck for themselves.")
    elif user.role in {UserRole.instructor, UserRole.admin}:
        _ensure_round_scope(db, user, round_obj)
    else:
        raise HTTPException(status_code=403, detail="Forbidden")

    assignment_exists = (
        db.query(ReviewerAssignment.id)
        .filter(ReviewerAssignment.round_id == payload.round_id, ReviewerAssignment.student_id == payload.student_id)
        .first()
    )
    if assignment_exists is None:
        raise HTTPException(status_code=422, detail="Recheck can only be requested for a student with existing review assignment.")

    request = RecheckRequest(
        round_id=payload.round_id,
        student_id=payload.student_id,
        section_id=payload.section_id,
        requested_by=user.id,
        reason=payload.reason,
        status=RecheckStatus.requested,
    )
    db.add(request)
    db.flush()
    write_audit_log(
        db,
        actor_id=user.id,
        action="review.recheck.create",
        entity_name="RecheckRequest",
        entity_id=request.id,
        before=None,
        after={
            "id": request.id,
            "round_id": request.round_id,
            "student_id": request.student_id,
            "section_id": request.section_id,
            "requested_by": request.requested_by,
            "status": request.status.value,
        },
    )
    logger.info(
        "review_recheck_created",
        extra={
            "event": "reviews.recheck.created",
            "fields": {
                "recheck_id": request.id,
                "round_id": request.round_id,
                "student_id": request.student_id,
                "requested_by": request.requested_by,
            },
        },
    )
    db.commit()
    db.refresh(request)
    return {"id": request.id, "status": request.status.value}


@router.post("/rechecks/{recheck_id}/assign")
def assign_recheck(
    recheck_id: int,
    payload: RecheckAssignIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _ensure_instructor_or_admin(user)
    request = db.query(RecheckRequest).filter(RecheckRequest.id == recheck_id).first()
    if request is None:
        raise HTTPException(status_code=404, detail="Recheck request not found.")
    round_obj = review_service._get_round(db, request.round_id)
    _ensure_round_scope(db, user, round_obj)
    review_service._check_coi(db, round_obj, payload.reviewer_id, request.student_id)
    existing_assignment = (
        db.query(ReviewerAssignment)
        .filter(
            ReviewerAssignment.round_id == request.round_id,
            ReviewerAssignment.reviewer_id == payload.reviewer_id,
            ReviewerAssignment.student_id == request.student_id,
        )
        .first()
    )
    if existing_assignment is None:
        existing_assignment = ReviewerAssignment(
            round_id=request.round_id,
            reviewer_id=payload.reviewer_id,
            student_id=request.student_id,
            section_id=request.section_id,
            assigned_manually=True,
        )
        db.add(existing_assignment)
        db.flush()
    before_status = request.status.value
    before_assigned_reviewer_id = request.assigned_reviewer_id
    request.status = RecheckStatus.assigned
    request.assigned_reviewer_id = payload.reviewer_id
    write_audit_log(
        db,
        actor_id=user.id,
        action="review.recheck.assign",
        entity_name="RecheckRequest",
        entity_id=request.id,
        before={"id": request.id, "status": before_status, "assigned_reviewer_id": before_assigned_reviewer_id},
        after={
            "id": request.id,
            "status": request.status.value,
            "assigned_reviewer_id": request.assigned_reviewer_id,
            "assignment_id": existing_assignment.id if existing_assignment else None,
        },
    )
    logger.info(
        "review_recheck_assigned",
        extra={
            "event": "reviews.recheck.assigned",
            "fields": {
                "recheck_id": request.id,
                "reviewer_id": request.assigned_reviewer_id,
                "assignment_id": existing_assignment.id if existing_assignment else None,
            },
        },
    )
    db.commit()
    return {"message": "Assigned."}


@router.post("/rounds/{round_id}/close")
def close_round(round_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _ensure_instructor_or_admin(user)
    round_obj = review_service._get_round(db, round_id)
    _ensure_round_scope(db, user, round_obj)
    review_service.ensure_round_closable(db, round_obj)
    before = {"id": round_obj.id, "status": round_obj.status.value}
    round_obj.status = ReviewRoundStatus.closed
    write_audit_log(
        db,
        actor_id=user.id,
        action="review.round.close",
        entity_name="ReviewRound",
        entity_id=round_obj.id,
        before=before,
        after={"id": round_obj.id, "status": round_obj.status.value},
    )
    logger.info(
        "review_round_closed",
        extra={
            "event": "reviews.round.closed",
            "fields": {
                "round_id": round_obj.id,
                "closed_by": user.id,
            },
        },
    )
    recipients = [row[0] for row in db.query(ReviewerAssignment.student_id).filter(ReviewerAssignment.round_id == round_id).distinct().all()]
    if recipients:
        messaging_service.dispatch_notifications(
            db,
            actor=user,
            trigger_type="GRADING_COMPLETED",
            title=f"Grading completed: {round_obj.name}",
            message="Grading has been completed for your review round.",
            recipient_ids=recipients,
            metadata={"round_id": round_obj.id, "section_id": round_obj.section_id},
        )
    db.commit()
    return {"message": "Round closed."}


@router.get("/rounds/{round_id}/export")
def export_round(
    round_id: int,
    format: str = Query(default="json", pattern="^(json|csv)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _ensure_instructor_or_admin(user)
    round_obj = review_service._get_round(db, round_id)
    _ensure_round_scope(db, user, round_obj)
    content = review_service.export_round_scores(db, round_id, format)
    media = "application/json" if format == "json" else "text/csv"
    return PlainTextResponse(content=content, media_type=media)
