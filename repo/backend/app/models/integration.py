from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class IntegrationClient(Base):
    __tablename__ = "integration_clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    secret_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    rate_limit_rpm: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class NonceLog(Base):
    __tablename__ = "nonce_logs"
    __table_args__ = (UniqueConstraint("client_id", "nonce", name="uq_nonce_per_client"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    nonce: Mapped[str] = mapped_column(String(120), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    body_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class IntegrationImport(Base):
    __tablename__ = "integration_imports"
    __table_args__ = (UniqueConstraint("client_id", "import_type", "import_id", name="uq_integration_import_client_type_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    import_type: Mapped[str] = mapped_column(String(64), nullable=False)
    import_id: Mapped[str] = mapped_column(String(120), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
