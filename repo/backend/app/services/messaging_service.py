import asyncio
from datetime import datetime, timedelta, timezone
import json

from fastapi import HTTPException
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.core.authz import check_scope_access
from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.models.messaging import (
    Notification,
    NotificationLog,
    NotificationSchedule,
    NotificationScheduleStatus,
    NotificationTrigger,
    NotificationTriggerConfig,
)
from app.models.user import User, UserRole

logger = get_logger("app.messaging")


DEFAULT_TRIGGER_CONFIG: dict[NotificationTrigger, tuple[bool, int | None]] = {
    NotificationTrigger.assignment_posted: (True, None),
    NotificationTrigger.deadline_72h: (True, 72),
    NotificationTrigger.deadline_24h: (True, 24),
    NotificationTrigger.deadline_2h: (True, 2),
    NotificationTrigger.grading_completed: (True, None),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_trigger(trigger_type: str) -> NotificationTrigger:
    try:
        return NotificationTrigger(trigger_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Unsupported trigger type.") from exc


def _serialize_metadata(metadata: dict | None) -> str | None:
    if metadata is None:
        return None
    return json.dumps(metadata, sort_keys=True, default=str)


def _parse_deadline_at(metadata: dict | None) -> datetime | None:
    if metadata is None:
        return None
    raw_deadline = metadata.get("deadline_at")
    if raw_deadline is None:
        return None
    if isinstance(raw_deadline, datetime):
        return _to_utc(raw_deadline)
    if not isinstance(raw_deadline, str):
        raise HTTPException(status_code=422, detail="metadata.deadline_at must be an ISO datetime string.")
    normalized = raw_deadline.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="metadata.deadline_at must be an ISO datetime string.") from exc
    return _to_utc(parsed)


def ensure_trigger_configs(db: Session) -> None:
    existing = {row.trigger_type for row in db.query(NotificationTriggerConfig).all()}
    for trigger_type, (enabled, lead_hours) in DEFAULT_TRIGGER_CONFIG.items():
        if trigger_type in existing:
            continue
        db.add(NotificationTriggerConfig(trigger_type=trigger_type, enabled=enabled, lead_hours=lead_hours))
    db.flush()


def list_trigger_configs(db: Session) -> list[NotificationTriggerConfig]:
    ensure_trigger_configs(db)
    return db.query(NotificationTriggerConfig).order_by(NotificationTriggerConfig.id.asc()).all()


def update_trigger_config(db: Session, trigger_type: str, *, enabled: bool, lead_hours: int | None) -> NotificationTriggerConfig:
    parsed_trigger = _parse_trigger(trigger_type)
    ensure_trigger_configs(db)
    row = db.query(NotificationTriggerConfig).filter(NotificationTriggerConfig.trigger_type == parsed_trigger).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Trigger config not found.")
    if parsed_trigger in {
        NotificationTrigger.deadline_72h,
        NotificationTrigger.deadline_24h,
        NotificationTrigger.deadline_2h,
    }:
        if lead_hours is None:
            raise HTTPException(status_code=422, detail="lead_hours is required for deadline triggers.")
    else:
        lead_hours = None
    row.enabled = enabled
    row.lead_hours = lead_hours
    db.flush()
    return row


def _config_map(db: Session) -> dict[NotificationTrigger, NotificationTriggerConfig]:
    ensure_trigger_configs(db)
    rows = db.query(NotificationTriggerConfig).all()
    return {row.trigger_type: row for row in rows}


def _ensure_dispatch_actor(actor: User) -> None:
    if actor.role not in {UserRole.admin, UserRole.instructor, UserRole.finance_clerk}:
        raise HTTPException(status_code=403, detail="Forbidden")


def _validate_recipient_scope(db: Session, actor: User, recipient_ids: list[int]) -> list[int]:
    unique_recipients = sorted(set(recipient_ids))
    if actor.role == UserRole.admin:
        existing_count = db.query(func.count(User.id)).filter(User.id.in_(unique_recipients)).scalar()
        if int(existing_count or 0) != len(unique_recipients):
            raise HTTPException(status_code=404, detail="One or more recipients were not found.")
        return unique_recipients

    recipients = db.query(User).filter(User.id.in_(unique_recipients)).all()
    if len(recipients) != len(unique_recipients):
        raise HTTPException(status_code=404, detail="One or more recipients were not found.")
    for recipient in recipients:
        if not check_scope_access(db, actor, recipient):
            raise HTTPException(status_code=403, detail="One or more recipients are outside your allowed scope.")
    return unique_recipients


def _create_notification(
    db: Session,
    *,
    recipient_id: int,
    trigger: NotificationTrigger,
    title: str,
    message: str,
    metadata: dict | None,
) -> int:
    notification = Notification(
        recipient_id=recipient_id,
        trigger_type=trigger,
        title=title,
        message=message,
        metadata_json=_serialize_metadata(metadata),
    )
    db.add(notification)
    db.flush()
    db.add(
        NotificationLog(
            notification_id=notification.id,
            recipient_id=recipient_id,
            event_type="DELIVERED",
            details=f"trigger={trigger.value}",
        )
    )
    return notification.id


def _queue_deadline_reminders(
    db: Session,
    *,
    recipient_ids: list[int],
    title: str,
    message: str,
    metadata: dict | None,
    deadline_at: datetime,
    config_map: dict[NotificationTrigger, NotificationTriggerConfig],
) -> int:
    queued = 0
    for trigger in [NotificationTrigger.deadline_72h, NotificationTrigger.deadline_24h, NotificationTrigger.deadline_2h]:
        config = config_map[trigger]
        if not config.enabled:
            continue
        lead_hours = int(config.lead_hours or 0)
        due_at = deadline_at - timedelta(hours=lead_hours)
        for recipient_id in recipient_ids:
            db.add(
                NotificationSchedule(
                    recipient_id=recipient_id,
                    trigger_type=trigger,
                    status=NotificationScheduleStatus.pending,
                    title=title,
                    message=message,
                    metadata_json=_serialize_metadata(metadata),
                    due_at=due_at,
                )
            )
            queued += 1
    db.flush()
    return queued


def dispatch_notifications(
    db: Session,
    *,
    actor: User,
    trigger_type: str,
    title: str,
    message: str,
    recipient_ids: list[int],
    metadata: dict | None = None,
) -> dict:
    _ensure_dispatch_actor(actor)
    trigger = _parse_trigger(trigger_type)
    config_map = _config_map(db)
    trigger_config = config_map[trigger]
    if not trigger_config.enabled:
        return {"created": 0, "notification_ids": [], "queued": 0}

    unique_recipients = _validate_recipient_scope(db, actor, recipient_ids)
    created_ids: list[int] = []
    for recipient_id in unique_recipients:
        created_ids.append(
            _create_notification(
                db,
                recipient_id=recipient_id,
                trigger=trigger,
                title=title,
                message=message,
                metadata=metadata,
            )
        )

    queued = 0
    if trigger == NotificationTrigger.assignment_posted:
        deadline_at = _parse_deadline_at(metadata)
        if deadline_at is not None:
            queued = _queue_deadline_reminders(
                db,
                recipient_ids=unique_recipients,
                title=title,
                message=message,
                metadata=metadata,
                deadline_at=deadline_at,
                config_map=config_map,
            )
    return {"created": len(created_ids), "notification_ids": created_ids, "queued": queued}


def process_due_schedules(db: Session, limit: int = 500) -> int:
    config_map = _config_map(db)
    rows = (
        db.query(NotificationSchedule)
        .filter(NotificationSchedule.status == NotificationScheduleStatus.pending, NotificationSchedule.due_at <= _utcnow())
        .order_by(NotificationSchedule.id.asc())
        .limit(limit)
        .all()
    )
    processed = 0
    for row in rows:
        config = config_map.get(row.trigger_type)
        if config is None or not config.enabled:
            row.status = NotificationScheduleStatus.cancelled
            row.dispatched_at = _utcnow()
            continue
        metadata = json.loads(row.metadata_json) if row.metadata_json else None
        notification_id = _create_notification(
            db,
            recipient_id=row.recipient_id,
            trigger=row.trigger_type,
            title=row.title,
            message=row.message,
            metadata=metadata,
        )
        row.status = NotificationScheduleStatus.dispatched
        row.dispatched_at = _utcnow()
        db.add(
            NotificationLog(
                notification_id=notification_id,
                recipient_id=row.recipient_id,
                event_type="SCHEDULE_DISPATCHED",
                details=f"schedule_id={row.id}",
            )
        )
        processed += 1
    db.flush()
    return processed


async def run_due_notification_poller(stop_event: asyncio.Event, interval_seconds: int) -> None:
    while not stop_event.is_set():
        db = SessionLocal()
        try:
            processed = process_due_schedules(db)
            db.commit()
            if processed:
                logger.info(
                    "notification_schedules_processed",
                    extra={"event": "messaging.scheduler.processed", "fields": {"processed": processed}},
                )
        except Exception:
            db.rollback()
            logger.exception("notification_scheduler_failed")
        finally:
            db.close()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=max(1, interval_seconds))
        except asyncio.TimeoutError:
            pass


def list_notifications(db: Session, recipient_id: int, limit: int = 50, offset: int = 0) -> tuple[int, list[Notification]]:
    unread_count = (
        db.query(func.count(Notification.id))
        .filter(Notification.recipient_id == recipient_id, Notification.read.is_(False))
        .scalar()
    )
    rows = (
        db.query(Notification)
        .filter(Notification.recipient_id == recipient_id)
        .order_by(desc(Notification.id))
        .offset(offset)
        .limit(limit)
        .all()
    )
    return int(unread_count or 0), rows


def mark_read(db: Session, notification_id: int, recipient_id: int) -> Notification:
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.recipient_id == recipient_id)
        .first()
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found.")
    if not notification.read:
        notification.read = True
        notification.read_at = _utcnow()
        db.add(
            NotificationLog(
                notification_id=notification.id,
                recipient_id=recipient_id,
                event_type="READ",
                details=None,
            )
        )
        db.commit()
        db.refresh(notification)
    return notification
