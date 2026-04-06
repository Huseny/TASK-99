from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.access import ScopeGrant, ScopeType
from app.models.admin import AuditLog, Course, Organization, Section, Term
from app.models.data_quality import QuarantineEntry
from app.models.registration import Enrollment, EnrollmentStatus
from app.models.user import User, UserRole


def _create_user(db: Session, username: str, role: UserRole, password: str, org_id: int | None = None) -> User:
    user = User(username=username, password_hash=hash_password(password), role=role, is_active=True, org_id=org_id)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _login(client, username: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _seed_round_context(db: Session) -> tuple[int, int, int]:
    organization = Organization(name="Review Org", code="RORG", is_active=True)
    db.add(organization)
    db.flush()
    term = Term(organization_id=organization.id, name="Spring 2027", starts_on="2027-01-10", ends_on="2027-05-10", is_active=True)
    db.add(term)
    db.flush()
    course = Course(organization_id=organization.id, code="RVW100", title="Review Course", credits=3, prerequisites=[])
    db.add(course)
    db.flush()
    section = Section(course_id=course.id, term_id=term.id, code="R1", instructor_id=None, capacity=40)
    db.add(section)
    db.commit()
    return organization.id, term.id, section.id


def _grant_section_scope(db: Session, user_id: int, section_id: int) -> None:
    db.add(ScopeGrant(user_id=user_id, scope_type=ScopeType.section, scope_id=section_id))
    db.commit()


def _enroll_user_in_section(db: Session, student_id: int, section_id: int) -> None:
    db.add(Enrollment(student_id=student_id, section_id=section_id, status=EnrollmentStatus.enrolled))
    db.commit()


def test_review_round_end_to_end(client, db_session: Session) -> None:
    instructor = _create_user(db_session, "inst1", UserRole.instructor, "InstructorPass1!")
    reviewer_1 = _create_user(db_session, "rev1", UserRole.reviewer, "ReviewerPass1!")
    reviewer_2 = _create_user(db_session, "rev2", UserRole.reviewer, "ReviewerPass1!")
    student = _create_user(db_session, "student1", UserRole.student, "StudentPass1!")
    org_id, term_id, section_id = _seed_round_context(db_session)
    _grant_section_scope(db_session, instructor.id, section_id)
    _grant_section_scope(db_session, reviewer_1.id, section_id)
    _grant_section_scope(db_session, reviewer_2.id, section_id)
    _enroll_user_in_section(db_session, student.id, section_id)

    instructor_headers = _login(client, "inst1", "InstructorPass1!")
    reviewer_headers = _login(client, "rev1", "ReviewerPass1!")

    form = client.post(
        "/api/v1/reviews/forms",
        json={
            "name": "Default Form",
            "organization_id": org_id,
            "criteria": [
                {"name": "Quality", "weight": 0.5, "min": 0, "max": 5},
                {"name": "Completeness", "weight": 0.5, "min": 0, "max": 5},
            ],
        },
        headers=instructor_headers,
    )
    assert form.status_code == 200
    form_id = form.json()["id"]

    round_response = client.post(
        "/api/v1/reviews/rounds",
        json={
            "name": "Round 1",
            "term_id": term_id,
            "section_id": section_id,
            "scoring_form_id": form_id,
            "identity_mode": "BLIND",
        },
        headers=instructor_headers,
    )
    assert round_response.status_code == 200
    round_id = round_response.json()["id"]

    manual_1 = client.post(
        f"/api/v1/reviews/rounds/{round_id}/assignments/manual",
        json={"reviewer_id": reviewer_1.id, "student_id": student.id},
        headers=instructor_headers,
    )
    assert manual_1.status_code == 200

    manual_2 = client.post(
        f"/api/v1/reviews/rounds/{round_id}/assignments/manual",
        json={"reviewer_id": reviewer_2.id, "student_id": student.id},
        headers=instructor_headers,
    )
    assert manual_2.status_code == 200

    assignments_for_reviewer = client.get(f"/api/v1/reviews/rounds/{round_id}/assignments", headers=reviewer_headers)
    assert assignments_for_reviewer.status_code == 200
    assert len(assignments_for_reviewer.json()) == 1
    assert assignments_for_reviewer.json()[0]["reviewer_id"] == reviewer_1.id
    assert assignments_for_reviewer.json()[0]["student_id"] is None
    assert assignments_for_reviewer.json()[0]["student_ref"] is None

    student_headers = _login(client, "student1", "StudentPass1!")
    forbidden_assignment_list = client.get(f"/api/v1/reviews/rounds/{round_id}/assignments", headers=student_headers)
    assert forbidden_assignment_list.status_code == 403

    score_1 = client.post(
        "/api/v1/reviews/scores",
        json={"assignment_id": manual_1.json()["id"], "criterion_scores": {"Quality": 5, "Completeness": 5}, "comment": "Strong"},
        headers=reviewer_headers,
    )
    assert score_1.status_code == 200

    score_1_update = client.post(
        "/api/v1/reviews/scores",
        json={"assignment_id": manual_1.json()["id"], "criterion_scores": {"Quality": 5, "Completeness": 5}, "comment": "Revised"},
        headers=reviewer_headers,
    )
    assert score_1_update.status_code == 200

    instructor_score_attempt = client.post(
        "/api/v1/reviews/scores",
        json={"assignment_id": manual_1.json()["id"], "criterion_scores": {"Quality": 4, "Completeness": 4}, "comment": "override"},
        headers=instructor_headers,
    )
    assert instructor_score_attempt.status_code == 403

    reviewer_2_headers = _login(client, "rev2", "ReviewerPass1!")
    score_2 = client.post(
        "/api/v1/reviews/scores",
        json={"assignment_id": manual_2.json()["id"], "criterion_scores": {"Quality": 1, "Completeness": 1}, "comment": "Weak"},
        headers=reviewer_2_headers,
    )
    assert score_2.status_code == 200

    outliers = client.get(f"/api/v1/reviews/rounds/{round_id}/outliers", headers=instructor_headers)
    assert outliers.status_code == 200
    assert len(outliers.json()) >= 1

    blocked_close = client.post(f"/api/v1/reviews/rounds/{round_id}/close", headers=instructor_headers)
    assert blocked_close.status_code == 409

    for flag in outliers.json():
        resolve = client.post(f"/api/v1/reviews/rounds/{round_id}/outliers/{flag['id']}/resolve", headers=instructor_headers)
        assert resolve.status_code == 200

    close = client.post(f"/api/v1/reviews/rounds/{round_id}/close", headers=instructor_headers)
    assert close.status_code == 200

    audit_actions = {
        row[0]
        for row in db_session.query(AuditLog.action)
        .filter(
            AuditLog.action.in_(
                [
                    "review.assignment.manual.create",
                    "review.score.create",
                    "review.score.update",
                    "review.outlier.resolve",
                    "review.round.close",
                ]
            )
        )
        .all()
    }
    assert "review.assignment.manual.create" in audit_actions
    assert "review.score.create" in audit_actions
    assert "review.score.update" in audit_actions
    assert "review.outlier.resolve" in audit_actions
    assert "review.round.close" in audit_actions

    export_json = client.get(f"/api/v1/reviews/rounds/{round_id}/export?format=json", headers=instructor_headers)
    assert export_json.status_code == 200

    export_csv = client.get(f"/api/v1/reviews/rounds/{round_id}/export?format=csv", headers=instructor_headers)
    assert export_csv.status_code == 200


def test_recheck_and_auto_assignment_and_rbac(client, db_session: Session) -> None:
    instructor = _create_user(db_session, "inst2", UserRole.instructor, "InstructorPass1!")
    reviewer = _create_user(db_session, "rev3", UserRole.reviewer, "ReviewerPass1!")
    student = _create_user(db_session, "student2", UserRole.student, "StudentPass1!")
    org_id, term_id, section_id = _seed_round_context(db_session)
    _grant_section_scope(db_session, instructor.id, section_id)
    _grant_section_scope(db_session, reviewer.id, section_id)
    _enroll_user_in_section(db_session, student.id, section_id)

    instructor_headers = _login(client, "inst2", "InstructorPass1!")
    student_headers = _login(client, "student2", "StudentPass1!")

    form = client.post(
        "/api/v1/reviews/forms",
        json={"name": "Form2", "organization_id": org_id, "criteria": [{"name": "Q", "weight": 1, "min": 0, "max": 5}]},
        headers=instructor_headers,
    )
    round_response = client.post(
        "/api/v1/reviews/rounds",
        json={"name": "Round 2", "term_id": term_id, "section_id": section_id, "scoring_form_id": form.json()["id"], "identity_mode": "OPEN"},
        headers=instructor_headers,
    )
    round_id = round_response.json()["id"]

    auto_assign = client.post(
        f"/api/v1/reviews/rounds/{round_id}/assignments/auto",
        json={"student_ids": [student.id], "reviewers_per_student": 1},
        headers=instructor_headers,
    )
    assert auto_assign.status_code == 200

    recheck = client.post(
        "/api/v1/reviews/rechecks",
        json={"round_id": round_id, "student_id": student.id, "section_id": section_id, "reason": "Please verify score"},
        headers=student_headers,
    )
    assert recheck.status_code == 200

    recheck_create_log = db_session.query(AuditLog).filter(AuditLog.action == "review.recheck.create").first()
    assert recheck_create_log is not None

    assign = client.post(
        f"/api/v1/reviews/rechecks/{recheck.json()['id']}/assign",
        json={"reviewer_id": reviewer.id},
        headers=instructor_headers,
    )
    assert assign.status_code == 200

    recheck_assign_log = db_session.query(AuditLog).filter(AuditLog.action == "review.recheck.assign").first()
    assert recheck_assign_log is not None

    rbac_denied = client.post(
        "/api/v1/reviews/forms",
        json={"name": "Denied", "organization_id": org_id, "criteria": [{"name": "Q", "weight": 1, "min": 0, "max": 5}]},
        headers=student_headers,
    )
    assert rbac_denied.status_code == 403


def test_review_scope_grant_required_for_instructor_round_creation(client, db_session: Session) -> None:
    instructor = _create_user(db_session, "inst_no_scope", UserRole.instructor, "InstructorPass1!")
    org_id, term_id, section_id = _seed_round_context(db_session)
    instructor_headers = _login(client, "inst_no_scope", "InstructorPass1!")

    form = client.post(
        "/api/v1/reviews/forms",
        json={"name": "Scoped Form", "organization_id": org_id, "criteria": [{"name": "Q", "weight": 1, "min": 0, "max": 5}]},
        headers=instructor_headers,
    )
    assert form.status_code == 200

    create_round = client.post(
        "/api/v1/reviews/rounds",
        json={
            "name": "Scoped Round",
            "term_id": term_id,
            "section_id": section_id,
            "scoring_form_id": form.json()["id"],
            "identity_mode": "OPEN",
        },
        headers=instructor_headers,
    )
    assert create_round.status_code == 403


def test_recheck_creation_denies_cross_user_requests(client, db_session: Session) -> None:
    instructor = _create_user(db_session, "inst_cross", UserRole.instructor, "InstructorPass1!")
    reviewer = _create_user(db_session, "rev_cross", UserRole.reviewer, "ReviewerPass1!")
    student_owner = _create_user(db_session, "student_owner", UserRole.student, "StudentPass1!")
    student_other = _create_user(db_session, "student_other", UserRole.student, "StudentPass1!")
    org_id, term_id, section_id = _seed_round_context(db_session)
    _grant_section_scope(db_session, instructor.id, section_id)
    _grant_section_scope(db_session, reviewer.id, section_id)
    _enroll_user_in_section(db_session, student_owner.id, section_id)

    instructor_headers = _login(client, "inst_cross", "InstructorPass1!")
    student_owner_headers = _login(client, "student_owner", "StudentPass1!")

    form = client.post(
        "/api/v1/reviews/forms",
        json={"name": "Cross User Form", "organization_id": org_id, "criteria": [{"name": "Q", "weight": 1, "min": 0, "max": 5}]},
        headers=instructor_headers,
    )
    round_response = client.post(
        "/api/v1/reviews/rounds",
        json={"name": "Cross User Round", "term_id": term_id, "section_id": section_id, "scoring_form_id": form.json()["id"], "identity_mode": "OPEN"},
        headers=instructor_headers,
    )
    round_id = round_response.json()["id"]
    client.post(
        f"/api/v1/reviews/rounds/{round_id}/assignments/manual",
        json={"reviewer_id": reviewer.id, "student_id": student_owner.id},
        headers=instructor_headers,
    )

    cross_user = client.post(
        "/api/v1/reviews/rechecks",
        json={"round_id": round_id, "student_id": student_other.id, "section_id": section_id, "reason": "Fake request"},
        headers=student_owner_headers,
    )
    assert cross_user.status_code == 403


def test_same_section_coi_blocks_manual_and_auto_assignment(client, db_session: Session) -> None:
    instructor = _create_user(db_session, "inst_coi", UserRole.instructor, "InstructorPass1!")
    reviewer = _create_user(db_session, "rev_coi", UserRole.reviewer, "ReviewerPass1!")
    student = _create_user(db_session, "student_coi", UserRole.student, "StudentPass1!")
    org_id, term_id, section_id = _seed_round_context(db_session)
    _grant_section_scope(db_session, instructor.id, section_id)
    _enroll_user_in_section(db_session, reviewer.id, section_id)
    _enroll_user_in_section(db_session, student.id, section_id)

    instructor_headers = _login(client, "inst_coi", "InstructorPass1!")
    form = client.post(
        "/api/v1/reviews/forms",
        json={"name": "COI Form", "organization_id": org_id, "criteria": [{"name": "Q", "weight": 1, "min": 0, "max": 5}]},
        headers=instructor_headers,
    )
    round_response = client.post(
        "/api/v1/reviews/rounds",
        json={"name": "COI Round", "term_id": term_id, "section_id": section_id, "scoring_form_id": form.json()["id"], "identity_mode": "OPEN"},
        headers=instructor_headers,
    )
    round_id = round_response.json()["id"]

    manual = client.post(
        f"/api/v1/reviews/rounds/{round_id}/assignments/manual",
        json={"reviewer_id": reviewer.id, "student_id": student.id},
        headers=instructor_headers,
    )
    assert manual.status_code == 409

    auto = client.post(
        f"/api/v1/reviews/rounds/{round_id}/assignments/auto",
        json={"student_ids": [student.id], "reviewers_per_student": 1},
        headers=instructor_headers,
    )
    assert auto.status_code == 409


def test_recheck_creation_denies_instructor_without_scope(client, db_session: Session) -> None:
    scoped_instructor = _create_user(db_session, "inst_scope_yes", UserRole.instructor, "InstructorPass1!")
    unscoped_instructor = _create_user(db_session, "inst_scope_no", UserRole.instructor, "InstructorPass1!")
    reviewer = _create_user(db_session, "rev_scope", UserRole.reviewer, "ReviewerPass1!")
    student = _create_user(db_session, "student_scope", UserRole.student, "StudentPass1!")
    org_id, term_id, section_id = _seed_round_context(db_session)
    _grant_section_scope(db_session, scoped_instructor.id, section_id)
    _grant_section_scope(db_session, reviewer.id, section_id)
    _enroll_user_in_section(db_session, student.id, section_id)

    scoped_headers = _login(client, "inst_scope_yes", "InstructorPass1!")
    unscoped_headers = _login(client, "inst_scope_no", "InstructorPass1!")

    form = client.post(
        "/api/v1/reviews/forms",
        json={"name": "Scope Form", "organization_id": org_id, "criteria": [{"name": "Q", "weight": 1, "min": 0, "max": 5}]},
        headers=scoped_headers,
    )
    round_response = client.post(
        "/api/v1/reviews/rounds",
        json={"name": "Scope Round", "term_id": term_id, "section_id": section_id, "scoring_form_id": form.json()["id"], "identity_mode": "OPEN"},
        headers=scoped_headers,
    )
    round_id = round_response.json()["id"]
    client.post(
        f"/api/v1/reviews/rounds/{round_id}/assignments/manual",
        json={"reviewer_id": reviewer.id, "student_id": student.id},
        headers=scoped_headers,
    )

    denied = client.post(
        "/api/v1/reviews/rechecks",
        json={"round_id": round_id, "student_id": student.id, "section_id": section_id, "reason": "Scope bypass"},
        headers=unscoped_headers,
    )
    assert denied.status_code == 403


def test_semiblind_reviewer_visibility_uses_stable_pseudonym(client, db_session: Session) -> None:
    instructor = _create_user(db_session, "inst_semiblind", UserRole.instructor, "InstructorPass1!")
    reviewer = _create_user(db_session, "rev_semiblind", UserRole.reviewer, "ReviewerPass1!")
    student = _create_user(db_session, "student_semiblind", UserRole.student, "StudentPass1!")
    org_id, term_id, section_id = _seed_round_context(db_session)
    _grant_section_scope(db_session, instructor.id, section_id)
    _grant_section_scope(db_session, reviewer.id, section_id)
    _enroll_user_in_section(db_session, student.id, section_id)

    instructor_headers = _login(client, "inst_semiblind", "InstructorPass1!")
    reviewer_headers = _login(client, "rev_semiblind", "ReviewerPass1!")

    form = client.post(
        "/api/v1/reviews/forms",
        json={"name": "Semi Blind Form", "organization_id": org_id, "criteria": [{"name": "Q", "weight": 1, "min": 0, "max": 5}]},
        headers=instructor_headers,
    )
    assert form.status_code == 200

    round_response = client.post(
        "/api/v1/reviews/rounds",
        json={
            "name": "Semi Blind Round",
            "term_id": term_id,
            "section_id": section_id,
            "scoring_form_id": form.json()["id"],
            "identity_mode": "SEMI_BLIND",
        },
        headers=instructor_headers,
    )
    assert round_response.status_code == 200
    round_id = round_response.json()["id"]

    assign = client.post(
        f"/api/v1/reviews/rounds/{round_id}/assignments/manual",
        json={"reviewer_id": reviewer.id, "student_id": student.id},
        headers=instructor_headers,
    )
    assert assign.status_code == 200

    reviewer_view_1 = client.get(f"/api/v1/reviews/rounds/{round_id}/assignments", headers=reviewer_headers)
    reviewer_view_2 = client.get(f"/api/v1/reviews/rounds/{round_id}/assignments", headers=reviewer_headers)
    assert reviewer_view_1.status_code == 200
    assert reviewer_view_2.status_code == 200

    item_1 = reviewer_view_1.json()[0]
    item_2 = reviewer_view_2.json()[0]
    assert item_1["student_id"] is None
    assert item_1["student_ref"] is not None
    assert item_1["student_ref"].startswith("SR-")
    assert item_1["student_ref"] == item_2["student_ref"]

    instructor_view = client.get(f"/api/v1/reviews/rounds/{round_id}/assignments", headers=instructor_headers)
    assert instructor_view.status_code == 200
    assert instructor_view.json()[0]["student_id"] == student.id
    assert instructor_view.json()[0]["student_ref"] is None


def test_review_form_rejected_by_data_quality(client, db_session: Session) -> None:
    instructor = _create_user(db_session, "inst_dq_review", UserRole.instructor, "InstructorPass1!")
    headers = _login(client, "inst_dq_review", "InstructorPass1!")

    response = client.post(
        "/api/v1/reviews/forms",
        json={"name": "", "organization_id": 1, "criteria": []},
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["detail"]["accepted"] is False
    quarantine_id = response.json()["detail"]["quarantine_id"]
    assert quarantine_id is not None

    row = db_session.query(QuarantineEntry).filter(QuarantineEntry.id == quarantine_id).first()
    assert row is not None
    assert row.entity_type == "ReviewFormWrite"


def test_manual_assignment_rejects_invalid_reviewer_role(client, db_session: Session) -> None:
    instructor = _create_user(db_session, "inst_invalid_reviewer", UserRole.instructor, "InstructorPass1!")
    invalid_reviewer = _create_user(db_session, "student_as_reviewer", UserRole.student, "StudentPass1!")
    student = _create_user(db_session, "review_valid_student", UserRole.student, "StudentPass1!")
    org_id, term_id, section_id = _seed_round_context(db_session)
    _grant_section_scope(db_session, instructor.id, section_id)
    _enroll_user_in_section(db_session, student.id, section_id)
    _grant_section_scope(db_session, valid_reviewer.id, section_id)

    instructor_headers = _login(client, "inst_invalid_reviewer", "InstructorPass1!")
    form = client.post(
        "/api/v1/reviews/forms",
        json={"name": "Assignment Validation Form", "organization_id": org_id, "criteria": [{"name": "Q", "weight": 1, "min": 0, "max": 5}]},
        headers=instructor_headers,
    )
    round_response = client.post(
        "/api/v1/reviews/rounds",
        json={"name": "Assignment Validation Round", "term_id": term_id, "section_id": section_id, "scoring_form_id": form.json()["id"], "identity_mode": "OPEN"},
        headers=instructor_headers,
    )

    response = client.post(
        f"/api/v1/reviews/rounds/{round_response.json()['id']}/assignments/manual",
        json={"reviewer_id": invalid_reviewer.id, "student_id": student.id},
        headers=instructor_headers,
    )
    assert response.status_code == 422


def test_manual_assignment_rejects_non_enrolled_student(client, db_session: Session) -> None:
    instructor = _create_user(db_session, "inst_non_enrolled", UserRole.instructor, "InstructorPass1!")
    reviewer = _create_user(db_session, "valid_reviewer", UserRole.reviewer, "ReviewerPass1!")
    student = _create_user(db_session, "not_enrolled_student", UserRole.student, "StudentPass1!")
    org_id, term_id, section_id = _seed_round_context(db_session)
    _grant_section_scope(db_session, instructor.id, section_id)

    instructor_headers = _login(client, "inst_non_enrolled", "InstructorPass1!")
    form = client.post(
        "/api/v1/reviews/forms",
        json={"name": "Enrollment Validation Form", "organization_id": org_id, "criteria": [{"name": "Q", "weight": 1, "min": 0, "max": 5}]},
        headers=instructor_headers,
    )
    round_response = client.post(
        "/api/v1/reviews/rounds",
        json={"name": "Enrollment Validation Round", "term_id": term_id, "section_id": section_id, "scoring_form_id": form.json()["id"], "identity_mode": "OPEN"},
        headers=instructor_headers,
    )

    response = client.post(
        f"/api/v1/reviews/rounds/{round_response.json()['id']}/assignments/manual",
        json={"reviewer_id": reviewer.id, "student_id": student.id},
        headers=instructor_headers,
    )
    assert response.status_code == 422


def test_auto_assignment_rejects_cross_org_reviewer_pool(client, db_session: Session) -> None:
    instructor = _create_user(db_session, "inst_auto_scope", UserRole.instructor, "InstructorPass1!")
    reviewer = _create_user(db_session, "rev_cross_org", UserRole.reviewer, "ReviewerPass1!", org_id=999)
    student = _create_user(db_session, "student_auto_scope", UserRole.student, "StudentPass1!")
    org_id, term_id, section_id = _seed_round_context(db_session)
    _grant_section_scope(db_session, instructor.id, section_id)
    _enroll_user_in_section(db_session, student.id, section_id)

    instructor_headers = _login(client, "inst_auto_scope", "InstructorPass1!")
    form = client.post(
        "/api/v1/reviews/forms",
        json={"name": "Scoped Auto Form", "organization_id": org_id, "criteria": [{"name": "Q", "weight": 1, "min": 0, "max": 5}]},
        headers=instructor_headers,
    )
    round_response = client.post(
        "/api/v1/reviews/rounds",
        json={"name": "Scoped Auto Round", "term_id": term_id, "section_id": section_id, "scoring_form_id": form.json()["id"], "identity_mode": "OPEN"},
        headers=instructor_headers,
    )

    response = client.post(
        f"/api/v1/reviews/rounds/{round_response.json()['id']}/assignments/auto",
        json={"student_ids": [student.id], "reviewers_per_student": 1},
        headers=instructor_headers,
    )
    assert response.status_code == 403


def test_cross_tenant_review_form_usage_is_forbidden(client, db_session: Session) -> None:
    instructor = _create_user(db_session, "inst_cross_form", UserRole.instructor, "InstructorPass1!")
    other_org = Organization(name="Other Review Org", code="OTHER_R", is_active=True)
    db_session.add(other_org)
    db_session.commit()
    org_id, term_id, section_id = _seed_round_context(db_session)
    _grant_section_scope(db_session, instructor.id, section_id)

    admin = _create_user(db_session, "admin_cross_form", UserRole.admin, "AdminPass1!")
    admin_headers = _login(client, "admin_cross_form", "AdminPass1!")
    instructor_headers = _login(client, "inst_cross_form", "InstructorPass1!")

    form = client.post(
        "/api/v1/reviews/forms",
        json={"name": "Cross Tenant Form", "organization_id": other_org.id, "criteria": [{"name": "Q", "weight": 1, "min": 0, "max": 5}]},
        headers=admin_headers,
    )
    assert form.status_code == 200

    round_response = client.post(
        "/api/v1/reviews/rounds",
        json={"name": "Cross Tenant Round", "term_id": term_id, "section_id": section_id, "scoring_form_id": form.json()["id"], "identity_mode": "OPEN"},
        headers=instructor_headers,
    )
    assert round_response.status_code == 403


def test_multilevel_reporting_conflict_blocks_assignment(client, db_session: Session) -> None:
    instructor = _create_user(db_session, "inst_multilevel", UserRole.instructor, "InstructorPass1!")
    manager = _create_user(db_session, "mgr_multilevel", UserRole.reviewer, "ReviewerPass1!")
    reviewer = _create_user(db_session, "rev_multilevel", UserRole.reviewer, "ReviewerPass1!")
    student = _create_user(db_session, "student_multilevel", UserRole.student, "StudentPass1!")
    reviewer.reports_to = manager.id
    student.reports_to = reviewer.id
    db_session.commit()

    org_id, term_id, section_id = _seed_round_context(db_session)
    _grant_section_scope(db_session, instructor.id, section_id)
    _grant_section_scope(db_session, reviewer.id, section_id)
    _enroll_user_in_section(db_session, student.id, section_id)

    instructor_headers = _login(client, "inst_multilevel", "InstructorPass1!")
    form = client.post(
        "/api/v1/reviews/forms",
        json={"name": "Hierarchy Form", "organization_id": org_id, "criteria": [{"name": "Q", "weight": 1, "min": 0, "max": 5}]},
        headers=instructor_headers,
    )
    round_response = client.post(
        "/api/v1/reviews/rounds",
        json={"name": "Hierarchy Round", "term_id": term_id, "section_id": section_id, "scoring_form_id": form.json()["id"], "identity_mode": "OPEN"},
        headers=instructor_headers,
    )

    response = client.post(
        f"/api/v1/reviews/rounds/{round_response.json()['id']}/assignments/manual",
        json={"reviewer_id": reviewer.id, "student_id": student.id},
        headers=instructor_headers,
    )
    assert response.status_code == 409
