"""Unit tests for app.services.review_service.

No HTTP layer – exercises service functions directly against an in-memory
SQLite database that mirrors the real schema.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from app.core.database import Base
from app.core.security import hash_password
from app.models.access import ScopeGrant, ScopeType
from app.models.admin import Course, Organization, Section, Term
from app.models.registration import Enrollment, EnrollmentStatus
from app.models.review import (
    IdentityMode,
    ReviewRound,
    ReviewRoundStatus,
    ReviewerAssignment,
    Score,
    ScoringForm,
    OutlierFlag,
)
from app.models.user import User, UserRole
from app.services import review_service


def _make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _org(db, name="Test Org", code="TORG"):
    org = Organization(name=name, code=code, is_active=True)
    db.add(org)
    db.flush()
    return org


def _term(db, org_id):
    t = Term(organization_id=org_id, name="Fall", starts_on="2026-09-01", ends_on="2026-12-20", is_active=True)
    db.add(t)
    db.flush()
    return t


def _section(db, course_id, term_id):
    s = Section(course_id=course_id, term_id=term_id, code="S1", capacity=30)
    db.add(s)
    db.flush()
    return s


def _course(db, org_id):
    c = Course(organization_id=org_id, code="CS101", title="Intro", credits=3, prerequisites=[])
    db.add(c)
    db.flush()
    return c


def _form(db, org_id, criteria=None):
    criteria = criteria or [{"name": "Quality", "weight": 1.0, "min": 0, "max": 5}]
    f = ScoringForm(name="Test Form", organization_id=org_id, criteria=criteria)
    db.add(f)
    db.flush()
    return f


def _user(db, username, role, org_id=None):
    u = User(username=username, password_hash=hash_password("Pass@1234567"), role=role, is_active=True, org_id=org_id)
    db.add(u)
    db.flush()
    return u


def _round(db, form_id, section_id, term_id, mode=IdentityMode.open):
    r = ReviewRound(
        name="Round 1",
        term_id=term_id,
        section_id=section_id,
        scoring_form_id=form_id,
        identity_mode=mode,
        status=ReviewRoundStatus.active,
    )
    db.add(r)
    db.flush()
    return r


def _enroll(db, student_id, section_id):
    e = Enrollment(student_id=student_id, section_id=section_id, status=EnrollmentStatus.enrolled)
    db.add(e)
    db.flush()


def _scope_grant(db, user_id, section_id):
    g = ScopeGrant(user_id=user_id, scope_type=ScopeType.section, scope_id=section_id)
    db.add(g)
    db.flush()


# ---------------------------------------------------------------------------
# _calculate_total_score
# ---------------------------------------------------------------------------

class TestCalculateTotalScore:
    def test_single_criterion(self):
        form = ScoringForm(criteria=[{"name": "Q", "weight": 1, "min": 0, "max": 5}])
        assert review_service._calculate_total_score(form, {"Q": 4.0}) == 4.0

    def test_weighted_average(self):
        form = ScoringForm(
            criteria=[
                {"name": "A", "weight": 0.6, "min": 0, "max": 10},
                {"name": "B", "weight": 0.4, "min": 0, "max": 10},
            ]
        )
        total = review_service._calculate_total_score(form, {"A": 10.0, "B": 0.0})
        assert total == round((10.0 * 0.6 + 0.0 * 0.4) / (0.6 + 0.4), 4)

    def test_missing_criterion_raises(self):
        form = ScoringForm(criteria=[{"name": "X", "weight": 1, "min": 0, "max": 5}])
        with pytest.raises(HTTPException) as exc:
            review_service._calculate_total_score(form, {})
        assert exc.value.status_code == 422

    def test_score_below_min_raises(self):
        form = ScoringForm(criteria=[{"name": "X", "weight": 1, "min": 2, "max": 5}])
        with pytest.raises(HTTPException) as exc:
            review_service._calculate_total_score(form, {"X": 1.0})
        assert exc.value.status_code == 422

    def test_score_above_max_raises(self):
        form = ScoringForm(criteria=[{"name": "X", "weight": 1, "min": 0, "max": 5}])
        with pytest.raises(HTTPException) as exc:
            review_service._calculate_total_score(form, {"X": 6.0})
        assert exc.value.status_code == 422

    def test_empty_criteria_raises(self):
        form = ScoringForm(criteria=[])
        with pytest.raises(HTTPException) as exc:
            review_service._calculate_total_score(form, {})
        assert exc.value.status_code == 422

    def test_zero_weight_raises(self):
        form = ScoringForm(criteria=[{"name": "X", "weight": 0, "min": 0, "max": 5}])
        with pytest.raises(HTTPException) as exc:
            review_service._calculate_total_score(form, {"X": 3.0})
        assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# _evaluate_outliers
# ---------------------------------------------------------------------------


class TestEvaluateOutliers:
    def test_no_flag_when_only_one_score(self):
        db = _make_db()
        org = _org(db)
        course = _course(db, org.id)
        term = _term(db, org.id)
        section = _section(db, course.id, term.id)
        form = _form(db, org.id)
        reviewer = _user(db, "rev_solo", UserRole.reviewer)
        student = _user(db, "stu_solo", UserRole.student)
        round_obj = _round(db, form.id, section.id, term.id)
        a = ReviewerAssignment(round_id=round_obj.id, reviewer_id=reviewer.id, student_id=student.id, section_id=section.id)
        db.add(a)
        db.flush()
        db.add(Score(assignment_id=a.id, criterion_scores={"Quality": 3.0}, total_score=3.0))
        db.flush()

        review_service._evaluate_outliers(db, round_obj.id, student.id)
        assert db.query(OutlierFlag).count() == 0


# ---------------------------------------------------------------------------
# auto_assign_reviewers
# ---------------------------------------------------------------------------

class TestAutoAssignReviewers:
    def _setup(self, db, n_reviewers=2):
        org = _org(db)
        course = _course(db, org.id)
        term = _term(db, org.id)
        section = _section(db, course.id, term.id)
        form = _form(db, org.id)
        round_obj = _round(db, form.id, section.id, term.id)
        reviewers = []
        for i in range(n_reviewers):
            r = _user(db, f"rev_{i}", UserRole.reviewer)
            _scope_grant(db, r.id, section.id)
            reviewers.append(r)
        student = _user(db, "stu", UserRole.student)
        _enroll(db, student.id, section.id)
        return round_obj, reviewers, student, section

    def test_assigns_correct_count(self):
        db = _make_db()
        round_obj, reviewers, student, section = self._setup(db, n_reviewers=2)
        assignments = review_service.auto_assign_reviewers(db, round_obj, [student.id], reviewers_per_student=2)
        assert len(assignments) == 2

    def test_raises_when_no_reviewers(self):
        db = _make_db()
        org = _org(db)
        course = _course(db, org.id)
        term = _term(db, org.id)
        section = _section(db, course.id, term.id)
        form = _form(db, org.id)
        round_obj = _round(db, form.id, section.id, term.id)
        student = _user(db, "stu_no_rev", UserRole.student)
        _enroll(db, student.id, section.id)

        with pytest.raises(HTTPException) as exc:
            review_service.auto_assign_reviewers(db, round_obj, [student.id], reviewers_per_student=1)
        assert exc.value.status_code in (422, 403)

    def test_coi_blocks_same_section_reviewer(self):
        """Reviewer and student both enrolled in section → COI → 409."""
        db = _make_db()
        round_obj, reviewers, student, section = self._setup(db, n_reviewers=1)
        # Also enrol the only reviewer in the section → COI for all reviewers
        _enroll(db, reviewers[0].id, section.id)

        with pytest.raises(HTTPException) as exc:
            review_service.auto_assign_reviewers(db, round_obj, [student.id], reviewers_per_student=1)
        assert exc.value.status_code == 409


# ---------------------------------------------------------------------------
# mask_assignment_for_view
# ---------------------------------------------------------------------------

class TestMaskAssignmentForView:
    def _make_assignment(self, round_id=1, reviewer_id=10, student_id=20, section_id=5):
        a = ReviewerAssignment()
        a.id = 1
        a.round_id = round_id
        a.reviewer_id = reviewer_id
        a.student_id = student_id
        a.section_id = section_id
        a.assigned_manually = False
        return a

    def _reviewer_user(self):
        u = User()
        u.id = 10
        u.role = UserRole.reviewer
        return u

    def _instructor_user(self):
        u = User()
        u.id = 99
        u.role = UserRole.instructor
        return u

    def test_open_mode_reveals_student_id_to_reviewer(self):
        a = self._make_assignment()
        result = review_service.mask_assignment_for_view(IdentityMode.open, a, self._reviewer_user())
        assert result["student_id"] == 20

    def test_blind_mode_hides_student_id_for_reviewer(self):
        a = self._make_assignment()
        result = review_service.mask_assignment_for_view(IdentityMode.blind, a, self._reviewer_user())
        assert result["student_id"] is None
        assert result["student_ref"] is None

    def test_semi_blind_provides_stable_pseudonym(self):
        a = self._make_assignment()
        r = self._reviewer_user()
        result1 = review_service.mask_assignment_for_view(IdentityMode.semi_blind, a, r)
        result2 = review_service.mask_assignment_for_view(IdentityMode.semi_blind, a, r)
        assert result1["student_id"] is None
        assert result1["student_ref"] is not None
        assert result1["student_ref"].startswith("SR-")
        assert result1["student_ref"] == result2["student_ref"]

    def test_instructor_always_sees_real_student_id(self):
        a = self._make_assignment()
        instr = self._instructor_user()
        for mode in (IdentityMode.blind, IdentityMode.semi_blind, IdentityMode.open):
            result = review_service.mask_assignment_for_view(mode, a, instr)
            assert result["student_id"] == 20


# ---------------------------------------------------------------------------
# ensure_round_closable
# ---------------------------------------------------------------------------

class TestEnsureRoundClosable:
    def test_raises_when_unresolved_flags_present(self):
        db = _make_db()
        org = _org(db)
        course = _course(db, org.id)
        term = _term(db, org.id)
        section = _section(db, course.id, term.id)
        form = _form(db, org.id)
        round_obj = _round(db, form.id, section.id, term.id)
        db.add(OutlierFlag(round_id=round_obj.id, student_id=1, score_id=1, median_score=3.0, deviation=2.5, resolved=False))
        db.flush()

        with pytest.raises(HTTPException) as exc:
            review_service.ensure_round_closable(db, round_obj)
        assert exc.value.status_code == 409

    def test_no_raise_when_all_flags_resolved(self):
        db = _make_db()
        org = _org(db)
        course = _course(db, org.id)
        term = _term(db, org.id)
        section = _section(db, course.id, term.id)
        form = _form(db, org.id)
        round_obj = _round(db, form.id, section.id, term.id)
        db.add(OutlierFlag(round_id=round_obj.id, student_id=1, score_id=1, median_score=3.0, deviation=2.5, resolved=True))
        db.flush()
        # Should not raise
        review_service.ensure_round_closable(db, round_obj)

    def test_no_raise_when_no_flags(self):
        db = _make_db()
        org = _org(db)
        course = _course(db, org.id)
        term = _term(db, org.id)
        section = _section(db, course.id, term.id)
        form = _form(db, org.id)
        round_obj = _round(db, form.id, section.id, term.id)
        review_service.ensure_round_closable(db, round_obj)
