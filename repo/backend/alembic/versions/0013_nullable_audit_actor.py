"""allow nullable audit actor for system events

Revision ID: 0013_nullable_audit_actor
Revises: 0012_msg_triggers_scheduler
Create Date: 2026-04-06 12:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_nullable_audit_actor"
down_revision = "0012_msg_triggers_scheduler"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.alter_column("actor_id", existing_type=sa.Integer(), nullable=True)

    with op.batch_alter_table("audit_logs_archive") as batch_op:
        batch_op.alter_column("actor_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("audit_logs_archive") as batch_op:
        batch_op.alter_column("actor_id", existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.alter_column("actor_id", existing_type=sa.Integer(), nullable=False)
