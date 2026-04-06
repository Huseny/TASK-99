"""integration actor users

Revision ID: 0015_integration_actor_users
Revises: 0014_iter2_integrations_dedup
Create Date: 2026-04-06 16:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "0015_integration_actor_users"
down_revision = "0014_iter2_integrations_dedup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("integration_clients") as batch_op:
        batch_op.add_column(sa.Column("actor_user_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_integration_clients_actor_user_id", ["actor_user_id"])
        batch_op.create_foreign_key("fk_integration_clients_actor_user_id", "users", ["actor_user_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("integration_clients") as batch_op:
        batch_op.drop_constraint("fk_integration_clients_actor_user_id", type_="foreignkey")
        batch_op.drop_index("ix_integration_clients_actor_user_id")
        batch_op.drop_column("actor_user_id")
