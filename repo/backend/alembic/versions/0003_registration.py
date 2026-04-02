"""registration

Revision ID: 0003_registration
Revises: 0002_admin_governance
Create Date: 2026-04-02 01:10:00
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_registration"
down_revision = "0002_admin_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    status_enum = sa.Enum("ENROLLED", "DROPPED", "COMPLETED", name="enrollmentstatus")
    status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "enrollments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("section_id", sa.Integer(), sa.ForeignKey("sections.id"), nullable=False),
        sa.Column("status", status_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("student_id", "section_id", name="uq_enrollment_student_section"),
    )
    op.create_index("ix_enrollments_student_id", "enrollments", ["student_id"])
    op.create_index("ix_enrollments_section_id", "enrollments", ["section_id"])

    op.create_table(
        "waitlist_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("section_id", sa.Integer(), sa.ForeignKey("sections.id"), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("student_id", "section_id", name="uq_waitlist_student_section"),
    )
    op.create_index("ix_waitlist_entries_student_id", "waitlist_entries", ["student_id"])
    op.create_index("ix_waitlist_entries_section_id", "waitlist_entries", ["section_id"])

    op.create_table(
        "add_drop_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("operation", sa.String(length=30), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_code", sa.Integer(), nullable=False),
        sa.Column("response_body", sa.String(length=2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("actor_id", "operation", "idempotency_key", name="uq_idempotency_actor_operation_key"),
    )
    op.create_index("ix_add_drop_requests_actor_id", "add_drop_requests", ["actor_id"])

    op.create_table(
        "registration_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("section_id", sa.Integer(), sa.ForeignKey("sections.id"), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("details", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_registration_history_student_id", "registration_history", ["student_id"])


def downgrade() -> None:
    op.drop_index("ix_registration_history_student_id", table_name="registration_history")
    op.drop_table("registration_history")
    op.drop_index("ix_add_drop_requests_actor_id", table_name="add_drop_requests")
    op.drop_table("add_drop_requests")
    op.drop_index("ix_waitlist_entries_section_id", table_name="waitlist_entries")
    op.drop_index("ix_waitlist_entries_student_id", table_name="waitlist_entries")
    op.drop_table("waitlist_entries")
    op.drop_index("ix_enrollments_section_id", table_name="enrollments")
    op.drop_index("ix_enrollments_student_id", table_name="enrollments")
    op.drop_table("enrollments")
    sa.Enum("ENROLLED", "DROPPED", "COMPLETED", name="enrollmentstatus").drop(op.get_bind(), checkfirst=True)
