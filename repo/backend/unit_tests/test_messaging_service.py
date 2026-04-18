"""Unit tests for app.services.messaging_service.

Pure service-layer tests – no HTTP, in-memory SQLite.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.security import hash_password
from app.models.messaging import Notification, NotificationTrigger, NotificationTriggerConfig
from app.models.user import User, UserRole
from app.services import messaging_service


def _make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _user(db, username, role=UserRole.admin, org_id=None):
    u = User(username=username, password_hash=hash_password("Pass@1234567"), role=role, is_active=True, org_id=org_id)
    db.add(u)
    db.flush()
    return u


# ---------------------------------------------------------------------------
# _parse_trigger
# ---------------------------------------------------------------------------

class TestParseTrigger:
    def test_valid_trigger(self):
        t = messaging_service._parse_trigger("ASSIGNMENT_POSTED")
        assert t == NotificationTrigger.assignment_posted

    def test_case_insensitive_variants_work(self):
        # All enum values are uppercase
        t = messaging_service._parse_trigger("GRADING_COMPLETED")
        assert t == NotificationTrigger.grading_completed

    def test_invalid_trigger_raises(self):
        with pytest.raises(HTTPException) as exc:
            messaging_service._parse_trigger("NOT_A_REAL_TRIGGER")
        assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# ensure_trigger_configs
# ---------------------------------------------------------------------------

class TestEnsureTriggerConfigs:
    def test_creates_all_default_configs(self):
        db = _make_db()
        messaging_service.ensure_trigger_configs(db)
        rows = db.query(NotificationTriggerConfig).all()
        assert len(rows) == len(messaging_service.DEFAULT_TRIGGER_CONFIG)

    def test_idempotent_on_repeat_calls(self):
        db = _make_db()
        messaging_service.ensure_trigger_configs(db)
        messaging_service.ensure_trigger_configs(db)
        rows = db.query(NotificationTriggerConfig).all()
        assert len(rows) == len(messaging_service.DEFAULT_TRIGGER_CONFIG)


# ---------------------------------------------------------------------------
# update_trigger_config
# ---------------------------------------------------------------------------

class TestUpdateTriggerConfig:
    def test_disable_assignment_posted(self):
        db = _make_db()
        messaging_service.ensure_trigger_configs(db)
        cfg = messaging_service.update_trigger_config(db, "ASSIGNMENT_POSTED", enabled=False, lead_hours=None)
        assert cfg.enabled is False

    def test_deadline_trigger_requires_lead_hours(self):
        db = _make_db()
        messaging_service.ensure_trigger_configs(db)
        with pytest.raises(HTTPException) as exc:
            messaging_service.update_trigger_config(db, "DEADLINE_72H", enabled=True, lead_hours=None)
        assert exc.value.status_code == 422

    def test_deadline_trigger_accepts_lead_hours(self):
        db = _make_db()
        messaging_service.ensure_trigger_configs(db)
        cfg = messaging_service.update_trigger_config(db, "DEADLINE_72H", enabled=True, lead_hours=72)
        assert cfg.lead_hours == 72

    def test_invalid_trigger_type_raises(self):
        db = _make_db()
        with pytest.raises(HTTPException) as exc:
            messaging_service.update_trigger_config(db, "BOGUS_TYPE", enabled=True, lead_hours=None)
        assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# dispatch_notifications
# ---------------------------------------------------------------------------

class TestDispatchNotifications:
    def test_creates_notification_for_each_recipient(self):
        db = _make_db()
        actor = _user(db, "admin_disp", UserRole.admin)
        r1 = _user(db, "rec1", UserRole.student)
        r2 = _user(db, "rec2", UserRole.student)
        messaging_service.ensure_trigger_configs(db)

        result = messaging_service.dispatch_notifications(
            db,
            actor=actor,
            trigger_type="ASSIGNMENT_POSTED",
            title="New assignment",
            message="Check it out",
            recipient_ids=[r1.id, r2.id],
        )
        assert result["created"] == 2
        assert len(result["notification_ids"]) == 2

    def test_disabled_trigger_creates_zero_notifications(self):
        db = _make_db()
        actor = _user(db, "admin_dis", UserRole.admin)
        r = _user(db, "rec_dis", UserRole.student)
        messaging_service.ensure_trigger_configs(db)
        messaging_service.update_trigger_config(db, "ASSIGNMENT_POSTED", enabled=False, lead_hours=None)

        result = messaging_service.dispatch_notifications(
            db,
            actor=actor,
            trigger_type="ASSIGNMENT_POSTED",
            title="Ignored",
            message="Won't arrive",
            recipient_ids=[r.id],
        )
        assert result["created"] == 0

    def test_student_actor_is_forbidden(self):
        db = _make_db()
        stu = _user(db, "stu_actor", UserRole.student)
        r = _user(db, "rec_forbidden", UserRole.student)
        with pytest.raises(HTTPException) as exc:
            messaging_service.dispatch_notifications(
                db,
                actor=stu,
                trigger_type="ASSIGNMENT_POSTED",
                title="Forbidden",
                message="Nope",
                recipient_ids=[r.id],
            )
        assert exc.value.status_code == 403

    def test_unknown_recipient_raises(self):
        db = _make_db()
        actor = _user(db, "admin_unk", UserRole.admin)
        messaging_service.ensure_trigger_configs(db)
        with pytest.raises(HTTPException) as exc:
            messaging_service.dispatch_notifications(
                db,
                actor=actor,
                trigger_type="ASSIGNMENT_POSTED",
                title="T",
                message="M",
                recipient_ids=[99999],
            )
        assert exc.value.status_code == 404

    def test_deduplicated_recipients(self):
        db = _make_db()
        actor = _user(db, "admin_dedup", UserRole.admin)
        r = _user(db, "rec_dedup", UserRole.student)
        messaging_service.ensure_trigger_configs(db)

        result = messaging_service.dispatch_notifications(
            db,
            actor=actor,
            trigger_type="GRADING_COMPLETED",
            title="Grades",
            message="Posted",
            recipient_ids=[r.id, r.id, r.id],
        )
        assert result["created"] == 1


# ---------------------------------------------------------------------------
# list_notifications / mark_read
# ---------------------------------------------------------------------------

class TestListAndMarkRead:
    def test_list_returns_notifications_for_recipient(self):
        db = _make_db()
        actor = _user(db, "admin_list", UserRole.admin)
        r = _user(db, "rec_list", UserRole.student)
        messaging_service.ensure_trigger_configs(db)
        messaging_service.dispatch_notifications(
            db, actor=actor, trigger_type="GRADING_COMPLETED",
            title="T", message="M", recipient_ids=[r.id],
        )
        db.commit()
        unread, rows = messaging_service.list_notifications(db, r.id)
        assert unread == 1
        assert len(rows) == 1

    def test_mark_read_clears_unread(self):
        db = _make_db()
        actor = _user(db, "admin_mr", UserRole.admin)
        r = _user(db, "rec_mr", UserRole.student)
        messaging_service.ensure_trigger_configs(db)
        result = messaging_service.dispatch_notifications(
            db, actor=actor, trigger_type="GRADING_COMPLETED",
            title="T", message="M", recipient_ids=[r.id],
        )
        db.commit()
        notif_id = result["notification_ids"][0]
        messaging_service.mark_read(db, notif_id, r.id)
        unread, _ = messaging_service.list_notifications(db, r.id)
        assert unread == 0

    def test_mark_read_unknown_notification_raises(self):
        db = _make_db()
        r = _user(db, "rec_unk_notif", UserRole.student)
        with pytest.raises(HTTPException) as exc:
            messaging_service.mark_read(db, 99999, r.id)
        assert exc.value.status_code == 404
