from datetime import datetime
import enum

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _enum_column(enum_cls: type[enum.Enum]) -> Enum:
    return Enum(
        enum_cls,
        native_enum=False,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )


class ReviewRoundStatus(str, enum.Enum):
    draft = "DRAFT"
    active = "ACTIVE"
    closed = "CLOSED"


class IdentityMode(str, enum.Enum):
    blind = "BLIND"
    semi_blind = "SEMI_BLIND"
    open = "OPEN"


class RecheckStatus(str, enum.Enum):
    requested = "REQUESTED"
    assigned = "ASSIGNED"
    resolved = "RESOLVED"


class ScoringForm(Base):
    __tablename__ = "scoring_forms"
    __table_args__ = (UniqueConstraint("source_client_id", "external_id", name="uq_scoring_forms_source_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    source_client_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    external_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    criteria: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ReviewRound(Base):
    __tablename__ = "review_rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id"), nullable=False)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"), nullable=False)
    scoring_form_id: Mapped[int] = mapped_column(ForeignKey("scoring_forms.id"), nullable=False)
    identity_mode: Mapped[IdentityMode] = mapped_column(_enum_column(IdentityMode), nullable=False, default=IdentityMode.blind)
    status: Mapped[ReviewRoundStatus] = mapped_column(_enum_column(ReviewRoundStatus), nullable=False, default=ReviewRoundStatus.draft)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ReviewerAssignment(Base):
    __tablename__ = "reviewer_assignments"
    __table_args__ = (UniqueConstraint("round_id", "reviewer_id", "student_id", name="uq_assignment_round_reviewer_student"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("review_rounds.id"), nullable=False, index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"), nullable=False)
    assigned_manually: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Score(Base):
    __tablename__ = "scores"
    __table_args__ = (UniqueConstraint("assignment_id", name="uq_score_assignment"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("reviewer_assignments.id"), nullable=False, index=True)
    criterion_scores: Mapped[dict] = mapped_column(JSON, nullable=False)
    total_score: Mapped[float] = mapped_column(Float, nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OutlierFlag(Base):
    __tablename__ = "outlier_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("review_rounds.id"), nullable=False, index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    score_id: Mapped[int] = mapped_column(ForeignKey("scores.id"), nullable=False)
    median_score: Mapped[float] = mapped_column(Float, nullable=False)
    deviation: Mapped[float] = mapped_column(Float, nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RecheckRequest(Base):
    __tablename__ = "recheck_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("review_rounds.id"), nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"), nullable=False)
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[RecheckStatus] = mapped_column(_enum_column(RecheckStatus), nullable=False, default=RecheckStatus.requested)
    assigned_reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
