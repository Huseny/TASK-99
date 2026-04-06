from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.audit import write_audit_log
from app.core.database import Base


def _make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def test_write_audit_log_rejects_missing_actor_for_privileged_write() -> None:
    db = _make_db()
    try:
        write_audit_log(
            db,
            actor_id=None,
            action="integrations.test.write",
            entity_name="IntegrationClient",
            entity_id=1,
            before=None,
            after={"ok": True},
        )
    except ValueError as exc:
        assert "actor_id is required" in str(exc)
    else:
        raise AssertionError("Expected actorless privileged audit write to be rejected.")
