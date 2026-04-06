from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.config import settings
from app.core.security import hash_password
from app.models.admin import Course, Organization, RegistrationRound, Section, Term
from app.models.registration import Enrollment, EnrollmentStatus
from app.models.user import User, UserRole
from app.services import registration_service


def _postgres_test_database_url() -> str | None:
    explicit = os.getenv("POSTGRES_TEST_DATABASE_URL")
    if explicit:
        return explicit
    configured = settings.database_url
    if configured.startswith("postgresql"):
        return configured
    return None


@pytest.mark.concurrent
@pytest.mark.postgres
def test_parallel_enrollment_does_not_oversubscribe_capacity() -> None:
    database_url = _postgres_test_database_url()
    if not database_url:
        pytest.skip("Postgres required")
    engine = create_engine(database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    seed_db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    org = Organization(name=f"Concurrency Org {suffix}", code=f"CONC{suffix}", is_active=True)
    seed_db.add(org)
    seed_db.flush()
    term = Term(organization_id=org.id, name="Fall 2027", starts_on="2027-09-01", ends_on="2027-12-20", is_active=True)
    seed_db.add(term)
    seed_db.flush()
    prereq_course = Course(organization_id=org.id, code=f"MATH{suffix}", title="Math", credits=3, prerequisites=[])
    target_course = Course(organization_id=org.id, code=f"CS{suffix}", title="Systems", credits=3, prerequisites=[prereq_course.code])
    seed_db.add(prereq_course)
    seed_db.add(target_course)
    seed_db.flush()
    prereq_section = Section(course_id=prereq_course.id, term_id=term.id, code=f"P{suffix}", instructor_id=None, capacity=30)
    target_section = Section(course_id=target_course.id, term_id=term.id, code=f"S{suffix}", instructor_id=None, capacity=1)
    seed_db.add(prereq_section)
    seed_db.add(target_section)
    seed_db.add(
        RegistrationRound(
            term_id=term.id,
            name=f"Primary {suffix}",
            starts_at=datetime.now(timezone.utc) - timedelta(hours=1),
            ends_at=datetime.now(timezone.utc) + timedelta(hours=2),
            is_active=True,
        )
    )
    students = [
        User(username=f"conc_{idx}_{suffix}", password_hash=hash_password("StudentPass123!"), role=UserRole.student, is_active=True, org_id=org.id)
        for idx in range(6)
    ]
    for student in students:
        seed_db.add(student)
    seed_db.flush()
    for student in students:
        seed_db.add(Enrollment(student_id=student.id, section_id=prereq_section.id, status=EnrollmentStatus.completed))
    seed_db.commit()
    seed_db.close()

    def _attempt(student_id: int, key: str) -> tuple[int, str]:
        db = SessionLocal()
        try:
            student = db.query(User).filter(User.id == student_id).first()
            assert student is not None
            code, response = registration_service.enroll(db, student, target_section.id, key)
            return code, response["status"]
        finally:
            db.close()

    work_items = [(student.id, f"key-{index}-{suffix}") for index, student in enumerate(students, start=1)]
    with ThreadPoolExecutor(max_workers=len(work_items)) as pool:
        results = list(pool.map(lambda item: _attempt(*item), work_items))

    success_count = sum(1 for code, status in results if code == 200 and status in {"enrolled", "already_enrolled"})
    assert success_count == 1
    full_count = sum(1 for code, status in results if code == 409 and status == "full")
    assert full_count == len(work_items) - 1

    verify_db = SessionLocal()
    try:
        enrolled_count = (
            verify_db.query(Enrollment)
            .filter(Enrollment.section_id == target_section.id, Enrollment.status == EnrollmentStatus.enrolled)
            .count()
        )
        assert enrolled_count == 1
        total_rows = verify_db.query(Enrollment).filter(Enrollment.section_id == target_section.id).count()
        assert total_rows == 1
    finally:
        verify_db.close()
