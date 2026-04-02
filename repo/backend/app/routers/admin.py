from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.auth import require_admin
from app.core.database import get_db
from app.core.security import hash_password, validate_password_complexity
from app.models.admin import AuditLog, Course, Organization, RegistrationRound, Section, Term
from app.models.user import SessionToken, User, UserRole
from app.schemas.admin import (
    AuditLogOut,
    CourseIn,
    CourseOut,
    OrganizationIn,
    OrganizationOut,
    RegistrationRoundIn,
    RegistrationRoundOut,
    SectionIn,
    SectionOut,
    TermIn,
    TermOut,
    UserCreateIn,
    UserOut,
    UserUpdateIn,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _to_dict(instance, fields: list[str]) -> dict:
    return {field: getattr(instance, field) for field in fields}


def _parse_role(role_value: str) -> UserRole:
    try:
        return UserRole(role_value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid role.") from exc


@router.post("/organizations", response_model=OrganizationOut)
def create_organization(payload: OrganizationIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    entity = Organization(**payload.model_dump())
    db.add(entity)
    db.flush()
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
    db.flush()
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
    db.flush()
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
    db.flush()
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
    entity = Course(**payload.model_dump())
    db.add(entity)
    db.flush()
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
    before = _to_dict(entity, ["id", "organization_id", "code", "title", "credits", "prerequisites"])
    for key, value in payload.model_dump().items():
        setattr(entity, key, value)
    db.flush()
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
    entity = Section(**payload.model_dump())
    db.add(entity)
    db.flush()
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
    before = _to_dict(entity, ["id", "course_id", "term_id", "code", "instructor_id", "capacity"])
    for key, value in payload.model_dump().items():
        setattr(entity, key, value)
    db.flush()
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
    db.flush()
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
    db.flush()
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
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=role,
        is_active=payload.is_active,
        org_id=payload.org_id,
        reports_to=payload.reports_to,
    )
    db.add(user)
    db.flush()
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


@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    before = _to_dict(user, ["id", "username", "is_active", "org_id", "reports_to"])
    db.query(SessionToken).filter(SessionToken.user_id == user.id, SessionToken.revoked.is_(False)).update({"revoked": True})
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
    for key, value in data.items():
        setattr(user, key, value)
    if payload.is_active is False:
        db.query(SessionToken).filter(SessionToken.user_id == user.id, SessionToken.revoked.is_(False)).update(
            {"revoked": True}
        )
    db.flush()
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
