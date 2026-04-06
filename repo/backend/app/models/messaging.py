from datetime import datetime
import enum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _enum_column(enum_cls: type[enum.Enum]) -> Enum:
    return Enum(
        enum_cls,
        native_enum=False,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )


class NotificationTrigger(str, enum.Enum):
    assignment_posted = "ASSIGNMENT_POSTED"
    deadline_72h = "DEADLINE_72H"
    deadline_24h = "DEADLINE_24H"
    deadline_2h = "DEADLINE_2H"
    grading_completed = "GRADING_COMPLETED"


class NotificationScheduleStatus(str, enum.Enum):
    pending = "PENDING"
    dispatched = "DISPATCHED"
    cancelled = "CANCELLED"


class NotificationTriggerConfig(Base):
    __tablename__ = "notification_trigger_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trigger_type: Mapped[NotificationTrigger] = mapped_column(_enum_column(NotificationTrigger), nullable=False, unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    lead_hours: Mapped[int] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    trigger_type: Mapped[NotificationTrigger] = mapped_column(_enum_column(NotificationTrigger), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notification_id: Mapped[int] = mapped_column(ForeignKey("notifications.id"), nullable=False, index=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=True)


class NotificationSchedule(Base):
    __tablename__ = "notification_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    trigger_type: Mapped[NotificationTrigger] = mapped_column(_enum_column(NotificationTrigger), nullable=False)
    status: Mapped[NotificationScheduleStatus] = mapped_column(
        _enum_column(NotificationScheduleStatus), nullable=False, default=NotificationScheduleStatus.pending
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    dispatched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
