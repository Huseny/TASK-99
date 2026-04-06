from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.access import ScopeGrant, ScopeType
from app.models.admin import Course, Organization, Section, Term
from app.models.messaging import NotificationSchedule, NotificationScheduleStatus, NotificationTrigger
from app.models.registration import Enrollment, EnrollmentStatus
from app.models.user import User, UserRole


def _create_user(db: Session, username: str, role: UserRole, password: str, org_id: int | None = None) -> User:
    user = User(username=username, password_hash=hash_password(password), role=role, is_active=True, org_id=org_id)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seed_round_context(db: Session) -> tuple[int, int, int]:
    organization = Organization(name="Messaging Org", code="MORG", is_active=True)
    db.add(organization)
    db.flush()
    term = Term(organization_id=organization.id, name="Spring 2027", starts_on="2027-01-10", ends_on="2027-05-10", is_active=True)
    db.add(term)
    db.flush()
    course = Course(organization_id=organization.id, code="MSG101", title="Messaging Course", credits=3, prerequisites=[])
    db.add(course)
    db.flush()
    section = Section(course_id=course.id, term_id=term.id, code="M1", instructor_id=None, capacity=40)
    db.add(section)
    db.commit()
    return organization.id, term.id, section.id


def _grant_section_scope(db: Session, user_id: int, section_id: int) -> None:
    db.add(ScopeGrant(user_id=user_id, scope_type=ScopeType.section, scope_id=section_id))
    db.commit()


def _grant_org_scope(db: Session, user_id: int, org_id: int) -> None:
    db.add(ScopeGrant(user_id=user_id, scope_type=ScopeType.organization, scope_id=org_id))
    db.commit()


def _enroll_user_in_section(db: Session, student_id: int, section_id: int) -> None:
    db.add(Enrollment(student_id=student_id, section_id=section_id, status=EnrollmentStatus.enrolled))
    db.commit()


def _login(client, username: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_dispatch_list_unread_and_mark_read(client, db_session: Session) -> None:
    instructor = _create_user(db_session, "msg_instructor", UserRole.instructor, "InstructorPass1!", org_id=11)
    student = _create_user(db_session, "msg_student", UserRole.student, "StudentPass1!", org_id=11)
    _grant_org_scope(db_session, instructor.id, 11)

    instructor_headers = _login(client, "msg_instructor", "InstructorPass1!")
    student_headers = _login(client, "msg_student", "StudentPass1!")

    dispatch = client.post(
        "/api/v1/messaging/dispatch",
        json={
            "trigger_type": "ASSIGNMENT_POSTED",
            "title": "New Assignment",
            "message": "Please review submission package.",
            "recipient_ids": [student.id],
            "metadata": {"round": 1},
        },
        headers=instructor_headers,
    )
    assert dispatch.status_code == 200
    assert dispatch.json()["created"] == 1

    listing = client.get("/api/v1/messaging/notifications", headers=student_headers)
    assert listing.status_code == 200
    assert listing.json()["unread_count"] == 1
    notification_id = listing.json()["notifications"][0]["id"]

    mark_read = client.patch(f"/api/v1/messaging/notifications/{notification_id}/read", headers=student_headers)
    assert mark_read.status_code == 200
    assert mark_read.json()["read"] is True

    listing_after = client.get("/api/v1/messaging/notifications", headers=student_headers)
    assert listing_after.status_code == 200
    assert listing_after.json()["unread_count"] == 0


def test_mark_read_denied_for_non_owner_and_dispatch_rbac(client, db_session: Session) -> None:
    instructor = _create_user(db_session, "msg_instructor2", UserRole.instructor, "InstructorPass1!", org_id=21)
    student_a = _create_user(db_session, "msg_student_a", UserRole.student, "StudentPass1!", org_id=21)
    student_b = _create_user(db_session, "msg_student_b", UserRole.student, "StudentPass1!", org_id=22)
    _grant_org_scope(db_session, instructor.id, 21)

    instructor_headers = _login(client, "msg_instructor2", "InstructorPass1!")
    student_a_headers = _login(client, "msg_student_a", "StudentPass1!")
    student_b_headers = _login(client, "msg_student_b", "StudentPass1!")

    dispatch = client.post(
        "/api/v1/messaging/dispatch",
        json={
            "trigger_type": "GRADING_COMPLETED",
            "title": "Grades Ready",
            "message": "Your grading cycle is complete.",
            "recipient_ids": [student_a.id],
        },
        headers=instructor_headers,
    )
    assert dispatch.status_code == 200

    listing = client.get("/api/v1/messaging/notifications", headers=student_a_headers)
    notification_id = listing.json()["notifications"][0]["id"]

    forbidden_read = client.patch(f"/api/v1/messaging/notifications/{notification_id}/read", headers=student_b_headers)
    assert forbidden_read.status_code == 404

    cross_scope_dispatch = client.post(
        "/api/v1/messaging/dispatch",
        json={
            "trigger_type": "GRADING_COMPLETED",
            "title": "Grades Ready",
            "message": "Your grading cycle is complete.",
            "recipient_ids": [student_a.id, student_b.id],
        },
        headers=instructor_headers,
    )
    assert cross_scope_dispatch.status_code == 403

    forbidden_dispatch = client.post(
        "/api/v1/messaging/dispatch",
        json={
            "trigger_type": "DEADLINE_24H",
            "title": "Reminder",
            "message": "24 hour reminder.",
            "recipient_ids": [student_b.id],
        },
        headers=student_a_headers,
    )
    assert forbidden_dispatch.status_code == 403


def test_trigger_config_and_deadline_schedule_processing(client, db_session: Session) -> None:
    admin = _create_user(db_session, "msg_admin", UserRole.admin, "AdminPass1!")
    student = _create_user(db_session, "msg_student_cfg", UserRole.student, "StudentPass1!")
    admin_headers = _login(client, "msg_admin", "AdminPass1!")
    student_headers = _login(client, "msg_student_cfg", "StudentPass1!")

    list_configs = client.get("/api/v1/messaging/triggers", headers=admin_headers)
    assert list_configs.status_code == 200
    assert len(list_configs.json()) == 5

    update_72h = client.put(
        "/api/v1/messaging/triggers/DEADLINE_72H",
        json={"enabled": True, "lead_hours": 1},
        headers=admin_headers,
    )
    assert update_72h.status_code == 200
    assert update_72h.json()["lead_hours"] == 1

    now = datetime.now(timezone.utc)
    dispatch = client.post(
        "/api/v1/messaging/dispatch",
        json={
            "trigger_type": "ASSIGNMENT_POSTED",
            "title": "Assignment Window",
            "message": "Submit your work.",
            "recipient_ids": [student.id],
            "metadata": {"deadline_at": (now + timedelta(minutes=20)).isoformat()},
        },
        headers=admin_headers,
    )
    assert dispatch.status_code == 200
    assert dispatch.json()["created"] == 1
    assert dispatch.json()["queued"] >= 1

    pending_schedule = (
        db_session.query(NotificationSchedule)
        .filter(
            NotificationSchedule.recipient_id == student.id,
            NotificationSchedule.trigger_type == NotificationTrigger.deadline_72h,
            NotificationSchedule.status == NotificationScheduleStatus.pending,
        )
        .first()
    )
    assert pending_schedule is not None
    pending_schedule.due_at = now - timedelta(minutes=1)
    db_session.commit()

    process_due = client.post("/api/v1/messaging/triggers/process-due", headers=admin_headers)
    assert process_due.status_code == 200
    assert process_due.json()["processed"] >= 1

    listing = client.get("/api/v1/messaging/notifications", headers=student_headers)
    assert listing.status_code == 200
    trigger_types = [item["trigger_type"] for item in listing.json()["notifications"]]
    assert "ASSIGNMENT_POSTED" in trigger_types
    assert "DEADLINE_72H" in trigger_types


def test_review_events_emit_assignment_and_grading_notifications(client, db_session: Session) -> None:
    instructor = _create_user(db_session, "msg_review_inst", UserRole.instructor, "InstructorPass1!")
    reviewer = _create_user(db_session, "msg_review_rev", UserRole.reviewer, "ReviewerPass1!")
    student = _create_user(db_session, "msg_review_student", UserRole.student, "StudentPass1!")
    org_id, term_id, section_id = _seed_round_context(db_session)
    _grant_section_scope(db_session, instructor.id, section_id)
    _grant_section_scope(db_session, reviewer.id, section_id)
    _enroll_user_in_section(db_session, student.id, section_id)

    instructor_headers = _login(client, "msg_review_inst", "InstructorPass1!")
    reviewer_headers = _login(client, "msg_review_rev", "ReviewerPass1!")
    student_headers = _login(client, "msg_review_student", "StudentPass1!")

    form = client.post(
        "/api/v1/reviews/forms",
        json={"name": "Msg Form", "organization_id": org_id, "criteria": [{"name": "Q", "weight": 1, "min": 0, "max": 5}]},
        headers=instructor_headers,
    )
    assert form.status_code == 200

    round_response = client.post(
        "/api/v1/reviews/rounds",
        json={"name": "Msg Round", "term_id": term_id, "section_id": section_id, "scoring_form_id": form.json()["id"], "identity_mode": "OPEN"},
        headers=instructor_headers,
    )
    assert round_response.status_code == 200
    round_id = round_response.json()["id"]

    assignment = client.post(
        f"/api/v1/reviews/rounds/{round_id}/assignments/manual",
        json={"reviewer_id": reviewer.id, "student_id": student.id},
        headers=instructor_headers,
    )
    assert assignment.status_code == 200

    score = client.post(
        "/api/v1/reviews/scores",
        json={"assignment_id": assignment.json()["id"], "criterion_scores": {"Q": 5}, "comment": "done"},
        headers=reviewer_headers,
    )
    assert score.status_code == 200

    close_round = client.post(f"/api/v1/reviews/rounds/{round_id}/close", headers=instructor_headers)
    assert close_round.status_code == 200

    listing = client.get("/api/v1/messaging/notifications", headers=student_headers)
    assert listing.status_code == 200
    trigger_types = {item["trigger_type"] for item in listing.json()["notifications"]}
    assert "ASSIGNMENT_POSTED" in trigger_types
    assert "GRADING_COMPLETED" in trigger_types
