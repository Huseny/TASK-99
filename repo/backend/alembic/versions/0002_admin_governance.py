"""admin governance

Revision ID: 0002_admin_governance
Revises: 0001_initial
Create Date: 2026-04-02 00:30:00
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_admin_governance"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=150), nullable=False, unique=True),
        sa.Column("code", sa.String(length=30), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_table(
        "terms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("starts_on", sa.String(length=10), nullable=False),
        sa.Column("ends_on", sa.String(length=10), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("prerequisites", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.create_table(
        "sections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("term_id", sa.Integer(), sa.ForeignKey("terms.id"), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("instructor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=False),
    )
    op.create_table(
        "registration_rounds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("term_id", sa.Integer(), sa.ForeignKey("terms.id"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("entity_name", sa.String(length=120), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("before_hash", sa.String(length=64), nullable=True),
        sa.Column("after_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("registration_rounds")
    op.drop_table("sections")
    op.drop_table("courses")
    op.drop_table("terms")
    op.drop_table("organizations")
