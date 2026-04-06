from datetime import datetime
import enum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _enum_column(enum_cls: type[enum.Enum]) -> Enum:
    return Enum(
        enum_cls,
        native_enum=False,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )


class ScopeType(str, enum.Enum):
    organization = "ORGANIZATION"
    section = "SECTION"


class ScopeGrant(Base):
    __tablename__ = "scope_grants"
    __table_args__ = (UniqueConstraint("user_id", "scope_type", "scope_id", name="uq_scope_grant_user_scope"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    scope_type: Mapped[ScopeType] = mapped_column(_enum_column(ScopeType), nullable=False)
    scope_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
