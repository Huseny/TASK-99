"""Unit tests for app.services.data_quality_service.

Pure service-layer tests – no HTTP, in-memory SQLite.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.admin import Course, Organization
from app.models.data_quality import QuarantineEntry, QuarantineStatus
from app.services import data_quality_service


def _make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


# ---------------------------------------------------------------------------
# _similarity
# ---------------------------------------------------------------------------

class TestSimilarity:
    def test_identical_strings(self):
        assert data_quality_service._similarity("hello", "hello") == 1.0

    def test_completely_different(self):
        assert data_quality_service._similarity("abc", "xyz") < 0.5

    def test_partial_match(self):
        score = data_quality_service._similarity("distributed systems", "distributed system")
        assert score > 0.9


# ---------------------------------------------------------------------------
# _fingerprint
# ---------------------------------------------------------------------------

class TestFingerprint:
    def test_deterministic(self):
        payload = {"code": "CS101", "title": "Intro", "credits": 3}
        assert data_quality_service._fingerprint(payload) == data_quality_service._fingerprint(payload)

    def test_different_payloads_differ(self):
        fp1 = data_quality_service._fingerprint({"a": 1})
        fp2 = data_quality_service._fingerprint({"a": 2})
        assert fp1 != fp2

    def test_key_order_independent(self):
        fp1 = data_quality_service._fingerprint({"a": 1, "b": 2})
        fp2 = data_quality_service._fingerprint({"b": 2, "a": 1})
        assert fp1 == fp2


# ---------------------------------------------------------------------------
# evaluate_payload
# ---------------------------------------------------------------------------

class TestEvaluatePayload:
    def test_accepts_valid_payload(self):
        db = _make_db()
        accepted, score, reasons, _ = data_quality_service.evaluate_payload(
            db,
            entity_type="AdminCourseWrite",
            payload={"code": "CS101", "title": "Intro", "credits": 3, "organization_id": 1},
            required_fields=["code", "title"],
            ranges={"credits": {"min": 1, "max": 6}},
            unique_keys=[],
        )
        assert accepted is True
        assert reasons == []
        assert score == 100

    def test_rejects_missing_required_field(self):
        db = _make_db()
        accepted, score, reasons, _ = data_quality_service.evaluate_payload(
            db,
            entity_type="AdminCourseWrite",
            payload={"title": "No Code Course", "organization_id": 1},
            required_fields=["code", "title"],
            ranges={},
            unique_keys=[],
        )
        assert accepted is False
        assert any("code" in r.lower() for r in reasons)

    def test_rejects_empty_string_required_field(self):
        db = _make_db()
        accepted, score, reasons, _ = data_quality_service.evaluate_payload(
            db,
            entity_type="AdminCourseWrite",
            payload={"code": "", "title": "Something", "organization_id": 1},
            required_fields=["code"],
            ranges={},
            unique_keys=[],
        )
        assert accepted is False

    def test_rejects_value_below_min(self):
        db = _make_db()
        accepted, score, reasons, _ = data_quality_service.evaluate_payload(
            db,
            entity_type="AdminCourseWrite",
            payload={"code": "C1", "title": "T", "credits": 0, "organization_id": 1},
            required_fields=[],
            ranges={"credits": {"min": 1, "max": 6}},
            unique_keys=[],
        )
        assert accepted is False
        assert any("below minimum" in r for r in reasons)

    def test_rejects_value_above_max(self):
        db = _make_db()
        accepted, score, reasons, _ = data_quality_service.evaluate_payload(
            db,
            entity_type="AdminCourseWrite",
            payload={"code": "C2", "title": "T", "credits": 10, "organization_id": 1},
            required_fields=[],
            ranges={"credits": {"min": 1, "max": 6}},
            unique_keys=[],
        )
        assert accepted is False
        assert any("above maximum" in r for r in reasons)

    def test_detects_authoritative_duplicate_course_code(self):
        db = _make_db()
        org = Organization(name="DQ Org", code="DQO", is_active=True)
        db.add(org)
        db.flush()
        db.add(Course(organization_id=org.id, code="CS200", title="Data Structures", credits=3, prerequisites=[]))
        db.flush()

        accepted, score, reasons, _ = data_quality_service.evaluate_payload(
            db,
            entity_type="AdminCourseWrite",
            payload={"code": "CS200", "title": "Different Title", "organization_id": org.id},
            required_fields=[],
            ranges={},
            unique_keys=[],
        )
        assert accepted is False
        assert any("duplicate" in r.lower() for r in reasons)

    def test_quality_score_not_below_zero(self):
        db = _make_db()
        # Trigger many violations
        _, score, _, _ = data_quality_service.evaluate_payload(
            db,
            entity_type="AdminCourseWrite",
            payload={"organization_id": 1},
            required_fields=["code", "title", "credits", "field4", "field5"],
            ranges={},
            unique_keys=[],
        )
        assert score >= 0


# ---------------------------------------------------------------------------
# quarantine_write
# ---------------------------------------------------------------------------

class TestQuarantineWrite:
    def test_creates_entry_in_db(self):
        db = _make_db()
        entry = data_quality_service.quarantine_write(
            db,
            entity_type="AdminCourseWrite",
            payload={"code": "", "title": ""},
            reasons=["Missing required field: code"],
            quality_score=80,
            fingerprint="abc123",
        )
        assert entry.id is not None
        assert entry.status == QuarantineStatus.open
        assert entry.entity_type == "AdminCourseWrite"


# ---------------------------------------------------------------------------
# enforce_write_quality
# ---------------------------------------------------------------------------

class TestEnforceWriteQuality:
    def test_passes_for_valid_payload(self):
        db = _make_db()
        # Should not raise
        data_quality_service.enforce_write_quality(
            db,
            entity_type="AdminCourseWrite",
            payload={"code": "CS999", "title": "Valid Course", "organization_id": 999},
            required_fields=["code", "title"],
        )

    def test_raises_and_creates_quarantine_for_invalid(self):
        db = _make_db()
        with pytest.raises(HTTPException) as exc:
            data_quality_service.enforce_write_quality(
                db,
                entity_type="AdminCourseWrite",
                payload={"code": "", "title": "", "organization_id": 999},
                required_fields=["code", "title"],
            )
        assert exc.value.status_code == 422
        detail = exc.value.detail
        assert detail["accepted"] is False
        assert detail["quarantine_id"] is not None

        # Quarantine entry must have been persisted
        entry = db.query(QuarantineEntry).filter(QuarantineEntry.id == detail["quarantine_id"]).first()
        assert entry is not None


# ---------------------------------------------------------------------------
# resolve_quarantine
# ---------------------------------------------------------------------------

class TestResolveQuarantine:
    def test_accept_action(self):
        db = _make_db()
        entry = data_quality_service.quarantine_write(
            db, entity_type="Test", payload={}, reasons=["x"], quality_score=50, fingerprint="fp1",
        )
        result = data_quality_service.resolve_quarantine(db, entry.id, "ACCEPT", resolver_id=1)
        assert result.status == QuarantineStatus.accepted

    def test_discard_action(self):
        db = _make_db()
        entry = data_quality_service.quarantine_write(
            db, entity_type="Test", payload={}, reasons=["x"], quality_score=50, fingerprint="fp2",
        )
        result = data_quality_service.resolve_quarantine(db, entry.id, "DISCARD", resolver_id=1)
        assert result.status == QuarantineStatus.discarded

    def test_invalid_action_raises(self):
        db = _make_db()
        entry = data_quality_service.quarantine_write(
            db, entity_type="Test", payload={}, reasons=["x"], quality_score=50, fingerprint="fp3",
        )
        with pytest.raises(HTTPException) as exc:
            data_quality_service.resolve_quarantine(db, entry.id, "INVALID", resolver_id=1)
        assert exc.value.status_code == 422

    def test_unknown_entry_raises(self):
        db = _make_db()
        with pytest.raises(HTTPException) as exc:
            data_quality_service.resolve_quarantine(db, 99999, "ACCEPT", resolver_id=1)
        assert exc.value.status_code == 404
