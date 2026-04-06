from dataclasses import dataclass, field

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.access import ScopeGrant, ScopeType
from app.models.admin import Course, Section
from app.models.finance import BankStatementLine, ReconciliationReport
from app.models.registration import Enrollment, EnrollmentStatus
from app.models.review import ScoringForm
from app.models.user import User, UserRole


@dataclass
class ScopeBinding:
    organization_ids: set[int] = field(default_factory=set)
    section_ids: set[int] = field(default_factory=set)


def has_scope_grant(db: Session, user_id: int, scope_type: ScopeType, scope_id: int) -> bool:
    grant = (
        db.query(ScopeGrant)
        .filter(ScopeGrant.user_id == user_id, ScopeGrant.scope_type == scope_type, ScopeGrant.scope_id == scope_id)
        .first()
    )
    return grant is not None


def _section_org_id(db: Session, section_id: int) -> int | None:
    row = (
        db.query(Course.organization_id)
        .join(Section, Section.course_id == Course.id)
        .filter(Section.id == section_id)
        .first()
    )
    if row is None:
        return None
    return int(row[0])


def _student_section_ids(db: Session, student_id: int) -> set[int]:
    rows = (
        db.query(Enrollment.section_id)
        .filter(
            Enrollment.student_id == student_id,
            Enrollment.status.in_([EnrollmentStatus.enrolled, EnrollmentStatus.completed]),
        )
        .all()
    )
    return {int(row[0]) for row in rows}


def _student_org_id(db: Session, student_id: int) -> int | None:
    row = db.query(User.org_id).filter(User.id == student_id).first()
    if row is None or row[0] is None:
        return None
    return int(row[0])


def get_user_scope_binding(db: Session, user: User) -> ScopeBinding:
    if user.role == UserRole.admin:
        return ScopeBinding()

    org_rows = (
        db.query(ScopeGrant.scope_id)
        .filter(ScopeGrant.user_id == user.id, ScopeGrant.scope_type == ScopeType.organization)
        .all()
    )
    section_rows = (
        db.query(ScopeGrant.scope_id)
        .filter(ScopeGrant.user_id == user.id, ScopeGrant.scope_type == ScopeType.section)
        .all()
    )
    organization_ids = {int(row[0]) for row in org_rows}
    section_ids = {int(row[0]) for row in section_rows}
    for section_id in section_ids:
        section_org_id = _section_org_id(db, section_id)
        if section_org_id is not None:
            organization_ids.add(section_org_id)
    if user.org_id is not None:
        organization_ids.add(int(user.org_id))
    return ScopeBinding(
        organization_ids=organization_ids,
        section_ids=section_ids,
    )


def get_resource_scope_binding(db: Session, resource: object) -> ScopeBinding:
    if isinstance(resource, User):
        binding = ScopeBinding()
        if resource.org_id is not None:
            binding.organization_ids.add(int(resource.org_id))
        binding.section_ids.update(_student_section_ids(db, resource.id))
        return binding

    if isinstance(resource, ReconciliationReport):
        lines = db.query(BankStatementLine.student_id).filter(BankStatementLine.import_id == resource.import_id).all()
        binding = ScopeBinding()
        for (student_id,) in lines:
            if student_id is None:
                continue
            student_org_id = _student_org_id(db, int(student_id))
            if student_org_id is not None:
                binding.organization_ids.add(student_org_id)
            binding.section_ids.update(_student_section_ids(db, int(student_id)))
        return binding

    binding = ScopeBinding()

    section_id = getattr(resource, "section_id", None)
    if section_id is not None:
        binding.section_ids.add(int(section_id))
        org_id = _section_org_id(db, int(section_id))
        if org_id is not None:
            binding.organization_ids.add(org_id)

    organization_id = getattr(resource, "organization_id", None)
    if organization_id is None:
        organization_id = getattr(resource, "org_id", None)
    if organization_id is not None:
        binding.organization_ids.add(int(organization_id))

    student_id = getattr(resource, "student_id", None)
    if student_id is not None:
        student_org_id = _student_org_id(db, int(student_id))
        if student_org_id is not None:
            binding.organization_ids.add(student_org_id)
        binding.section_ids.update(_student_section_ids(db, int(student_id)))

    return binding


def check_scope_access(db: Session, user: User, resource: object) -> bool:
    if user.role == UserRole.admin:
        return True

    user_scope = get_user_scope_binding(db, user)
    resource_scope = get_resource_scope_binding(db, resource)
    if resource_scope.section_ids & user_scope.section_ids:
        return True
    if resource_scope.organization_ids & user_scope.organization_ids:
        return True
    return False


def require_scope_access(db: Session, user: User, resource: object, *, detail: str = "Access denied for requested resource.") -> None:
    if not check_scope_access(db, user, resource):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def can_access_section(db: Session, user: User, section_id: int) -> bool:
    return check_scope_access(db, user, type("SectionResource", (), {"section_id": section_id})())


def require_section_access(db: Session, user: User, section_id: int) -> None:
    if not can_access_section(db, user, section_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied for requested section.")


def can_access_form(db: Session, user: User, form_id: int) -> bool:
    form = db.query(ScoringForm).filter(ScoringForm.id == form_id).first()
    if form is None:
        return False
    return check_scope_access(db, user, form)


def require_form_access(db: Session, user: User, form_id: int) -> None:
    if not can_access_form(db, user, form_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied for requested scoring form.")


def can_access_organization(db: Session, user: User, organization_id: int) -> bool:
    return check_scope_access(db, user, type("OrganizationResource", (), {"organization_id": organization_id})())


def require_organization_access(db: Session, user: User, organization_id: int) -> None:
    if not can_access_organization(db, user, organization_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied for requested organization.")


def can_access_student(db: Session, user: User, student_id: int) -> bool:
    student = db.query(User).filter(User.id == student_id).first()
    if student is None:
        return False
    return check_scope_access(db, user, student)


def require_student_access(db: Session, user: User, student_id: int) -> None:
    if not can_access_student(db, user, student_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied for requested student account.")
