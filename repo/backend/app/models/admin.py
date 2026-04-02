from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Term(Base):
    __tablename__ = "terms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    starts_on: Mapped[str] = mapped_column(String(10), nullable=False)
    ends_on: Mapped[str] = mapped_column(String(10), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    prerequisites: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


class Section(Base):
    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    instructor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=True)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)


class RegistrationRound(Base):
    __tablename__ = "registration_rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_name: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=True)
    before_hash: Mapped[str] = mapped_column(String(64), nullable=True)
    after_hash: Mapped[str] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=True)
