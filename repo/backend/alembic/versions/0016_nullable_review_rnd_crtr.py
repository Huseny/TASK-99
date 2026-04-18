"""allow nullable review_rounds.created_by

Revision ID: 0016_nullable_review_rnd_crtr
Revises: 0015_integration_actor_users
Create Date: 2026-04-18 12:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "0016_nullable_review_rnd_crtr"
down_revision = "0015_integration_actor_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("review_rounds") as batch_op:
        batch_op.alter_column("created_by", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("review_rounds") as batch_op:
        batch_op.alter_column("created_by", existing_type=sa.Integer(), nullable=False)
