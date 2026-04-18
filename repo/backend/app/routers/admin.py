from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.auth import require_admin
from app.core.database import get_db
from app.core.security import hash_password, validate_password_complexity
from app.models.access import ScopeGrant, ScopeType
from app.models.admin import AuditLog, Course, Organization, RegistrationRound, Section, Term
from app.models.finance import BankStatementLine, LedgerAccount, LedgerEntry
from app.models.integration import IntegrationClient
from app.models.messaging import Notification, NotificationLog, NotificationSchedule
from app.models.registration import AddDropRequest, Enrollment, RegistrationHistory, WaitlistEntry
from app.models.review import (
    OutlierFlag,
    RecheckRequest,
    ReviewRound,
    ReviewerAssignment,
    Score,
)
from app.models.user import SessionToken, User, UserRole
from app.schemas.admin import (
    AuditRetentionRunOut,
    AuditLogOut,
    CourseIn,
    CourseOut,
    OrganizationIn,
    OrganizationOut,
    RegistrationRoundIn,
    RegistrationRoundOut,
    SectionIn,
    SectionOut,
    ScopeGrantIn,
    ScopeGrantOut,
    TermIn,
    TermOut,
    UserCreateIn,
    UserOut,
    UserUpdateIn,
)
from app.services import audit_retention_service, auth_service, data_quality_service

router = APIRouter(prefix="/admin", tags=["admin"])


def _to_dict(instance, fields: list[str]) -> dict:
    return {field: getattr(instance, field) for field in fields}


def _parse_role(role_value: str) -> UserRole:
    try:
        return UserRole(role_value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid role.") from exc


def _parse_scope_type(scope_type_value: str) -> ScopeType:
    try:
        return ScopeType(scope_type_value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid scope type.") from exc


def _enforce_admin_write_quality(entity_type: str, payload: dict, db: Session) -> None:
    rules: dict[str, dict] = {
        "AdminCourseWrite": {
            "required_fields": ["organization_id", "code", "title", "credits"],
            "ranges": {"credits": {"min": 1, "max": 12}},
            "unique_keys": ["code", "title"],
        },
        "AdminSectionWrite": {
            "required_fields": ["course_id", "term_id", "code", "capacity"],
            "ranges": {"capacity": {"min": 1, "max": 5000}},
            "unique_keys": ["code"],
        },
        "AdminUserWrite": {
            "required_fields": ["username", "role"],
            "ranges": {},
            "unique_keys": ["username"],
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


@router.post("/organizations", response_model=OrganizationOut)
def create_organization(payload: OrganizationIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    entity = Organization(**payload.model_dump())
    db.add(entity)
    data_quality_service.flush_or_raise_conflict(db, detail="Duplicate organization detected.")
    write_audit_log(
        db,
        actor_id=admin.id,
        action="organization.create",
        entity_name="Organization",
        entity_id=entity.id,
        before=None,
        after=_to_dict(entity, ["id", "name", "code", "is_active"]),
    )
    db.commit()
    db.refresh(entity)
    return OrganizationOut(**_to_dict(entity, ["id", "name", "code", "is_active"]))


@router.get("/organizations", response_model=list[OrganizationOut])
def list_organizations(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.query(Organization).order_by(Organization.id.asc()).all()
    return [OrganizationOut(**_to_dict(row, ["id", "name", "code", "is_active"])) for row in rows]


@router.put("/organizations/{organization_id}", response_model=OrganizationOut)
def update_organization(
    organization_id: int,
    payload: OrganizationIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    entity = db.query(Organization).filter(Organization.id == organization_id).first()
    if entity is None:
        raise HTTPException(status_code=404, detail="Organization not found.")
    before = _to_dict(entity, ["id", "name", "code", "is_active"])
    for key, value in payload.model_dump().items():
        setattr(entity, key, value)
    data_quality_service.flush_or_raise_conflict(db, detail="Duplicate organization detected.")
    after = _to_dict(entity, ["id", "name", "code", "is_active"])
    write_audit_log(
        db,
        actor_id=admin.id,
        action="organization.update",
        entity_name="Organization",
        entity_id=entity.id,
        before=before,
        after=after,
    )
    db.commit()
    return OrganizationOut(**after)


@router.delete("/organizations/{organization_id}")
def delete_organization(organization_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    entity = db.query(Organization).filter(Organization.id == organization_id).first()
    if entity is None:
        raise HTTPException(status_code=404, detail="Organization not found.")
    before = _to_dict(entity, ["id", "name", "code", "is_active"])
    db.delete(entity)
    write_audit_log(
        db,
        actor_id=admin.id,
        action="organization.delete",
        entity_name="Organization",
        entity_id=organization_id,
        before=before,
        after=None,
    )
    db.commit()
    return {"message": "Deleted."}


@router.post("/terms", response_model=TermOut)
def create_term(payload: TermIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    entity = Term(**payload.model_dump())
    db.add(entity)
    data_quality_service.flush_or_raise_conflict(db, detail="Duplicate term detected.")
    write_audit_log(db, actor_id=admin.id, action="term.create", entity_name="Term", entity_id=entity.id, before=None, after=_to_dict(entity, ["id", "organization_id", "name", "starts_on", "ends_on", "is_active"]))
    db.commit()
    return TermOut(**_to_dict(entity, ["id", "organization_id", "name", "starts_on", "ends_on", "is_active"]))


@router.get("/terms", response_model=list[TermOut])
def list_terms(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.query(Term).order_by(Term.id.asc()).all()
    return [TermOut(**_to_dict(row, ["id", "organization_id", "name", "starts_on", "ends_on", "is_active"])) for row in rows]


@router.put("/terms/{term_id}", response_model=TermOut)
def update_term(term_id: int, payload: TermIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    entity = db.query(Term).filter(Term.id == term_id).first()
    if entity is None:
        raise HTTPException(status_code=404, detail="Term not found.")
    before = _to_dict(entity, ["id", "organization_id", "name", "starts_on", "ends_on", "is_active"])
    for key, value in payload.model_dump().items():
        setattr(entity, key, value)
    data_quality_service.flush_or_raise_conflict(db, detail="Duplicate term detected.")
    after = _to_dict(entity, ["id", "organization_id", "name", "starts_on", "ends_on", "is_active"])
    write_audit_log(db, actor_id=admin.id, action="term.update", entity_name="Term", entity_id=entity.id, before=before, after=after)
    db.commit()
    return TermOut(**after)


@router.delete("/terms/{term_id}")
def delete_term(term_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    entity = db.query(Term).filter(Term.id == term_id).first()
    if entity is None:
        raise HTTPException(status_code=404, detail="Term not found.")
    before = _to_dict(entity, ["id", "organization_id", "name", "starts_on", "ends_on", "is_active"])
    db.delete(entity)
    write_audit_log(db, actor_id=admin.id, action="term.delete", entity_name="Term", entity_id=term_id, before=before, after=None)
    db.commit()
    return {"message": "Deleted."}


@router.post("/courses", response_model=CourseOut)
def create_course(payload: CourseIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    _enforce_admin_write_quality("AdminCourseWrite", payload.model_dump(), db)
    entity = Course(**payload.model_dump())
    db.add(entity)
    data_quality_service.flush_or_raise_conflict(db, detail="Duplicate course detected.")
    write_audit_log(db, actor_id=admin.id, action="course.create", entity_name="Course", entity_id=entity.id, before=None, after=_to_dict(entity, ["id", "organization_id", "code", "title", "credits", "prerequisites"]))
    db.commit()
    return CourseOut(**_to_dict(entity, ["id", "organization_id", "code", "title", "credits", "prerequisites"]))


@router.get("/courses", response_model=list[CourseOut])
def list_courses(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.query(Course).order_by(Course.id.asc()).all()
    return [CourseOut(**_to_dict(row, ["id", "organization_id", "code", "title", "credits", "prerequisites"])) for row in rows]


@router.put("/courses/{course_id}", response_model=CourseOut)
def update_course(course_id: int, payload: CourseIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    entity = db.query(Course).filter(Course.id == course_id).first()
    if entity is None:
        raise HTTPException(status_code=404, detail="Course not found.")
    _enforce_admin_write_quality("AdminCourseWrite", {**payload.model_dump(), "existing_entity_id": entity.id}, db)
    before = _to_dict(entity, ["id", "organization_id", "code", "title", "credits", "prerequisites"])
    for key, value in payload.model_dump().items():
        setattr(entity, key, value)
    data_quality_service.flush_or_raise_conflict(db, detail="Duplicate course detected.")
    after = _to_dict(entity, ["id", "organization_id", "code", "title", "credits", "prerequisites"])
    write_audit_log(db, actor_id=admin.id, action="course.update", entity_name="Course", entity_id=entity.id, before=before, after=after)
    db.commit()
    return CourseOut(**after)


@router.delete("/courses/{course_id}")
def delete_course(course_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    entity = db.query(Course).filter(Course.id == course_id).first()
    if entity is None:
        raise HTTPException(status_code=404, detail="Course not found.")
    before = _to_dict(entity, ["id", "organization_id", "code", "title", "credits", "prerequisites"])
    db.delete(entity)
    write_audit_log(db, actor_id=admin.id, action="course.delete", entity_name="Course", entity_id=course_id, before=before, after=None)
    db.commit()
    return {"message": "Deleted."}


@router.post("/sections", response_model=SectionOut)
def create_section(payload: SectionIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    _enforce_admin_write_quality("AdminSectionWrite", payload.model_dump(), db)
    entity = Section(**payload.model_dump())
    db.add(entity)
    data_quality_service.flush_or_raise_conflict(db, detail="Duplicate section detected.")
    write_audit_log(db, actor_id=admin.id, action="section.create", entity_name="Section", entity_id=entity.id, before=None, after=_to_dict(entity, ["id", "course_id", "term_id", "code", "instructor_id", "capacity"]))
    db.commit()
    return SectionOut(**_to_dict(entity, ["id", "course_id", "term_id", "code", "instructor_id", "capacity"]))


@router.get("/sections", response_model=list[SectionOut])
def list_sections(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.query(Section).order_by(Section.id.asc()).all()
    return [SectionOut(**_to_dict(row, ["id", "course_id", "term_id", "code", "instructor_id", "capacity"])) for row in rows]


@router.put("/sections/{section_id}", response_model=SectionOut)
def update_section(section_id: int, payload: SectionIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    entity = db.query(Section).filter(Section.id == section_id).first()
    if entity is None:
        raise HTTPException(status_code=404, detail="Section not found.")
    _enforce_admin_write_quality("AdminSectionWrite", {**payload.model_dump(), "existing_entity_id": entity.id}, db)
    before = _to_dict(entity, ["id", "course_id", "term_id", "code", "instructor_id", "capacity"])
    for key, value in payload.model_dump().items():
        setattr(entity, key, value)
    data_quality_service.flush_or_raise_conflict(db, detail="Duplicate section detected.")
    after = _to_dict(entity, ["id", "course_id", "term_id", "code", "instructor_id", "capacity"])
    write_audit_log(db, actor_id=admin.id, action="section.update", entity_name="Section", entity_id=entity.id, before=before, after=after)
    db.commit()
    return SectionOut(**after)


@router.delete("/sections/{section_id}")
def delete_section(section_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    entity = db.query(Section).filter(Section.id == section_id).first()
    if entity is None:
        raise HTTPException(status_code=404, detail="Section not found.")
    before = _to_dict(entity, ["id", "course_id", "term_id", "code", "instructor_id", "capacity"])
    db.delete(entity)
    write_audit_log(db, actor_id=admin.id, action="section.delete", entity_name="Section", entity_id=section_id, before=before, after=None)
    db.commit()
    return {"message": "Deleted."}


@router.post("/registration-rounds", response_model=RegistrationRoundOut)
def create_round(payload: RegistrationRoundIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    entity = RegistrationRound(**payload.model_dump())
    db.add(entity)
    data_quality_service.flush_or_raise_conflict(db, detail="Duplicate registration round detected.")
    write_audit_log(db, actor_id=admin.id, action="registration_round.create", entity_name="RegistrationRound", entity_id=entity.id, before=None, after=_to_dict(entity, ["id", "term_id", "name", "starts_at", "ends_at", "is_active"]))
    db.commit()
    return RegistrationRoundOut(**_to_dict(entity, ["id", "term_id", "name", "starts_at", "ends_at", "is_active"]))


@router.get("/registration-rounds", response_model=list[RegistrationRoundOut])
def list_rounds(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.query(RegistrationRound).order_by(RegistrationRound.id.asc()).all()
    return [RegistrationRoundOut(**_to_dict(row, ["id", "term_id", "name", "starts_at", "ends_at", "is_active"])) for row in rows]


@router.put("/registration-rounds/{round_id}", response_model=RegistrationRoundOut)
def update_round(
    round_id: int,
    payload: RegistrationRoundIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    entity = db.query(RegistrationRound).filter(RegistrationRound.id == round_id).first()
    if entity is None:
        raise HTTPException(status_code=404, detail="Registration round not found.")
    before = _to_dict(entity, ["id", "term_id", "name", "starts_at", "ends_at", "is_active"])
    for key, value in payload.model_dump().items():
        setattr(entity, key, value)
    data_quality_service.flush_or_raise_conflict(db, detail="Duplicate registration round detected.")
    after = _to_dict(entity, ["id", "term_id", "name", "starts_at", "ends_at", "is_active"])
    write_audit_log(db, actor_id=admin.id, action="registration_round.update", entity_name="RegistrationRound", entity_id=entity.id, before=before, after=after)
    db.commit()
    return RegistrationRoundOut(**after)


@router.delete("/registration-rounds/{round_id}")
def delete_round(round_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    entity = db.query(RegistrationRound).filter(RegistrationRound.id == round_id).first()
    if entity is None:
        raise HTTPException(status_code=404, detail="Registration round not found.")
    before = _to_dict(entity, ["id", "term_id", "name", "starts_at", "ends_at", "is_active"])
    db.delete(entity)
    write_audit_log(db, actor_id=admin.id, action="registration_round.delete", entity_name="RegistrationRound", entity_id=round_id, before=before, after=None)
    db.commit()
    return {"message": "Deleted."}


@router.post("/users", response_model=UserOut)
def create_user(payload: UserCreateIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    valid, reason = validate_password_complexity(payload.password)
    if not valid:
        raise HTTPException(status_code=422, detail=reason)
    role = _parse_role(payload.role)
    _enforce_admin_write_quality(
        "AdminUserWrite",
        {"username": payload.username, "role": role.value, "org_id": payload.org_id, "reports_to": payload.reports_to},
        db,
    )
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=role,
        is_active=payload.is_active,
        org_id=payload.org_id,
        reports_to=payload.reports_to,
    )
    db.add(user)
    data_quality_service.flush_or_raise_conflict(db, detail="Duplicate user detected.")
    write_audit_log(db, actor_id=admin.id, action="user.create", entity_name="User", entity_id=user.id, before=None, after=_to_dict(user, ["id", "username", "is_active", "org_id", "reports_to"]))
    db.commit()
    return UserOut(
        id=user.id,
        username=user.username,
        role=user.role.value,
        is_active=user.is_active,
        org_id=user.org_id,
        reports_to=user.reports_to,
    )


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.query(User).order_by(User.id.asc()).all()
    return [
        UserOut(
            id=row.id,
            username=row.username,
            role=row.role.value,
            is_active=row.is_active,
            org_id=row.org_id,
            reports_to=row.reports_to,
        )
        for row in rows
    ]


def _purge_user_dependencies(db: Session, user_id: int) -> None:
    """Remove or null-out every row that references this user so the
    subsequent ``DELETE FROM users`` does not violate FK constraints.

    - Nullable FK columns (audit trail, org graph) are set to NULL so history
      is preserved with an anonymous actor.
    - User-scoped transactional rows (enrollments, ledger, notifications,
      reviewer assignments, etc.) are hard-deleted, child-first, to avoid
      dangling references.
    """
    sync = {"synchronize_session": False}

    # 1. Null out nullable references so history/structure is preserved.
    db.query(Section).filter(Section.instructor_id == user_id).update(
        {"instructor_id": None}, **sync
    )
    db.query(User).filter(User.reports_to == user_id).update(
        {"reports_to": None}, **sync
    )
    db.query(ReviewRound).filter(ReviewRound.created_by == user_id).update(
        {"created_by": None}, **sync
    )
    db.query(IntegrationClient).filter(IntegrationClient.actor_user_id == user_id).update(
        {"actor_user_id": None}, **sync
    )
    db.query(RecheckRequest).filter(RecheckRequest.assigned_reviewer_id == user_id).update(
        {"assigned_reviewer_id": None}, **sync
    )
    db.query(AuditLog).filter(AuditLog.actor_id == user_id).update(
        {"actor_id": None}, **sync
    )

    # 2. Review-scoring graph — collect affected assignment / score ids
    #    first, then delete child rows before their parents.
    assignment_ids = [
        row.id
        for row in db.query(ReviewerAssignment.id)
        .filter(
            (ReviewerAssignment.reviewer_id == user_id)
            | (ReviewerAssignment.student_id == user_id)
        )
        .all()
    ]
    score_ids = (
        [
            row.id
            for row in db.query(Score.id)
            .filter(Score.assignment_id.in_(assignment_ids))
            .all()
        ]
        if assignment_ids
        else []
    )
    db.query(OutlierFlag).filter(OutlierFlag.student_id == user_id).delete(**sync)
    if score_ids:
        db.query(OutlierFlag).filter(OutlierFlag.score_id.in_(score_ids)).delete(**sync)
        db.query(Score).filter(Score.id.in_(score_ids)).delete(**sync)
    if assignment_ids:
        db.query(ReviewerAssignment).filter(
            ReviewerAssignment.id.in_(assignment_ids)
        ).delete(**sync)
    db.query(RecheckRequest).filter(
        (RecheckRequest.student_id == user_id)
        | (RecheckRequest.requested_by == user_id)
    ).delete(**sync)

    # 3. Finance ledger — null out bank-statement match references first so
    #    the FK on matched_entry_id does not block LedgerEntry deletion, then
    #    delete entries before their parent account.
    entry_ids = [
        row.id
        for row in db.query(LedgerEntry.id)
        .filter(LedgerEntry.student_id == user_id)
        .all()
    ]
    if entry_ids:
        db.query(BankStatementLine).filter(
            BankStatementLine.matched_entry_id.in_(entry_ids)
        ).update({"matched_entry_id": None, "matched": False}, **sync)
        db.query(LedgerEntry).filter(LedgerEntry.id.in_(entry_ids)).delete(**sync)
    db.query(LedgerAccount).filter(LedgerAccount.student_id == user_id).delete(**sync)

    # 4. Registration-domain rows.
    db.query(Enrollment).filter(Enrollment.student_id == user_id).delete(**sync)
    db.query(WaitlistEntry).filter(WaitlistEntry.student_id == user_id).delete(**sync)
    db.query(AddDropRequest).filter(AddDropRequest.actor_id == user_id).delete(**sync)
    db.query(RegistrationHistory).filter(
        RegistrationHistory.student_id == user_id
    ).delete(**sync)

    # 5. Messaging deliveries to this recipient. NotificationLog has an FK
    #    to Notification, so delete logs before the parent Notifications.
    notif_ids = [
        row.id
        for row in db.query(Notification.id)
        .filter(Notification.recipient_id == user_id)
        .all()
    ]
    db.query(NotificationLog).filter(NotificationLog.recipient_id == user_id).delete(**sync)
    if notif_ids:
        db.query(NotificationLog).filter(
            NotificationLog.notification_id.in_(notif_ids)
        ).delete(**sync)
        db.query(Notification).filter(Notification.id.in_(notif_ids)).delete(**sync)
    db.query(NotificationSchedule).filter(
        NotificationSchedule.recipient_id == user_id
    ).delete(**sync)

    # 6. Access / session data.
    db.query(ScopeGrant).filter(ScopeGrant.user_id == user_id).delete(**sync)
    db.query(SessionToken).filter(SessionToken.user_id == user_id).delete(**sync)


@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    before = _to_dict(user, ["id", "username", "is_active", "org_id", "reports_to"])
    auth_service.revoke_user_sessions(db, user.id, commit=False)
    _purge_user_dependencies(db, user.id)
    db.delete(user)
    write_audit_log(db, actor_id=admin.id, action="user.delete", entity_name="User", entity_id=user_id, before=before, after=None)
    db.commit()
    return {"message": "Deleted."}


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdateIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    before = _to_dict(user, ["id", "username", "is_active", "org_id", "reports_to"])
    data = payload.model_dump(exclude_unset=True)
    if "role" in data and data["role"] is not None:
        user.role = _parse_role(data.pop("role"))
    dq_payload = {
        "username": user.username,
        "role": user.role.value,
        "org_id": data.get("org_id", user.org_id),
        "reports_to": data.get("reports_to", user.reports_to),
        "existing_entity_id": user.id,
    }
    _enforce_admin_write_quality("AdminUserWrite", dq_payload, db)
    for key, value in data.items():
        setattr(user, key, value)
    if payload.is_active is False:
        auth_service.revoke_user_sessions(db, user.id, commit=False)
    data_quality_service.flush_or_raise_conflict(db, detail="Duplicate user detected.")
    after = _to_dict(user, ["id", "username", "is_active", "org_id", "reports_to"])
    write_audit_log(db, actor_id=admin.id, action="user.update", entity_name="User", entity_id=user.id, before=before, after=after)
    db.commit()
    return UserOut(
        id=user.id,
        username=user.username,
        role=user.role.value,
        is_active=user.is_active,
        org_id=user.org_id,
        reports_to=user.reports_to,
    )


@router.get("/audit-log", response_model=list[AuditLogOut])
def get_audit_logs(
    entity_name: str | None = Query(default=None),
    action: str | None = Query(default=None),
    actor_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    query = db.query(AuditLog)
    if entity_name:
        query = query.filter(AuditLog.entity_name == entity_name)
    if action:
        query = query.filter(AuditLog.action == action)
    if actor_id:
        query = query.filter(AuditLog.actor_id == actor_id)
    rows = query.order_by(AuditLog.id.desc()).offset(offset).limit(limit).all()
    return [
        AuditLogOut(
            id=row.id,
            actor_id=row.actor_id,
            action=row.action,
            entity_name=row.entity_name,
            entity_id=row.entity_id,
            before_hash=row.before_hash,
            after_hash=row.after_hash,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post("/audit-log/retention", response_model=AuditRetentionRunOut)
def run_audit_log_retention(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    archived_count, purged_count, cutoff = audit_retention_service.run_archive_and_purge(db)
    write_audit_log(
        db,
        actor_id=admin.id,
        action="audit.retention.run",
        entity_name="AuditLog",
        entity_id=None,
        before=None,
        after={"archived_count": archived_count, "purged_count": purged_count, "cutoff_iso": cutoff.isoformat()},
    )
    db.commit()
    return AuditRetentionRunOut(archived_count=archived_count, purged_count=purged_count, cutoff_iso=cutoff.isoformat())


@router.post("/scope-grants", response_model=ScopeGrantOut)
def create_scope_grant(payload: ScopeGrantIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    scope_type = _parse_scope_type(payload.scope_type)
    user = db.query(User).filter(User.id == payload.user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    if scope_type == ScopeType.organization:
        exists_scope = db.query(Organization.id).filter(Organization.id == payload.scope_id).first()
    else:
        exists_scope = db.query(Section.id).filter(Section.id == payload.scope_id).first()
    if exists_scope is None:
        raise HTTPException(status_code=404, detail="Scope target not found.")

    grant = (
        db.query(ScopeGrant)
        .filter(
            ScopeGrant.user_id == payload.user_id,
            ScopeGrant.scope_type == scope_type,
            ScopeGrant.scope_id == payload.scope_id,
        )
        .first()
    )
    if grant is None:
        grant = ScopeGrant(user_id=payload.user_id, scope_type=scope_type, scope_id=payload.scope_id)
        db.add(grant)
        data_quality_service.flush_or_raise_conflict(db, detail="Duplicate scope grant detected.")
        write_audit_log(
            db,
            actor_id=admin.id,
            action="scope_grant.create",
            entity_name="ScopeGrant",
            entity_id=grant.id,
            before=None,
            after={"id": grant.id, "user_id": grant.user_id, "scope_type": grant.scope_type.value, "scope_id": grant.scope_id},
        )
        db.commit()

    return ScopeGrantOut(
        id=grant.id,
        user_id=grant.user_id,
        scope_type=grant.scope_type.value,
        scope_id=grant.scope_id,
        created_at=grant.created_at,
    )


@router.get("/scope-grants", response_model=list[ScopeGrantOut])
def list_scope_grants(
    user_id: int | None = Query(default=None),
    scope_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    query = db.query(ScopeGrant)
    if user_id is not None:
        query = query.filter(ScopeGrant.user_id == user_id)
    if scope_type is not None:
        query = query.filter(ScopeGrant.scope_type == _parse_scope_type(scope_type))
    rows = query.order_by(ScopeGrant.id.asc()).all()
    return [
        ScopeGrantOut(
            id=row.id,
            user_id=row.user_id,
            scope_type=row.scope_type.value,
            scope_id=row.scope_id,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.delete("/scope-grants/{grant_id}")
def delete_scope_grant(grant_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    grant = db.query(ScopeGrant).filter(ScopeGrant.id == grant_id).first()
    if grant is None:
        raise HTTPException(status_code=404, detail="Scope grant not found.")

    before = {
        "id": grant.id,
        "user_id": grant.user_id,
        "scope_type": grant.scope_type.value,
        "scope_id": grant.scope_id,
    }
    db.delete(grant)
    write_audit_log(
        db,
        actor_id=admin.id,
        action="scope_grant.delete",
        entity_name="ScopeGrant",
        entity_id=grant_id,
        before=before,
        after=None,
    )
    db.commit()
    return {"message": "Deleted."}
