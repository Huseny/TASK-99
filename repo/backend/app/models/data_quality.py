from datetime import datetime
import enum

from sqlalchemy import DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _enum_column(enum_cls: type[enum.Enum]) -> Enum:
    return Enum(
        enum_cls,
        native_enum=False,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )


class QuarantineStatus(str, enum.Enum):
    open = "OPEN"
    accepted = "ACCEPTED"
    discarded = "DISCARDED"


class QuarantineEntry(Base):
    __tablename__ = "quarantine_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    rejection_reason: Mapped[str] = mapped_column(Text, nullable=False)
    quality_score: Mapped[int] = mapped_column(Integer, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[QuarantineStatus] = mapped_column(_enum_column(QuarantineStatus), nullable=False, default=QuarantineStatus.open)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[int] = mapped_column(Integer, nullable=True)
