"""initial

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-02 00:00:00
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    user_role_enum = sa.Enum("STUDENT", "INSTRUCTOR", "REVIEWER", "FINANCE_CLERK", "ADMIN", name="userrole")
    user_role_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", user_role_enum, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("org_id", sa.Integer(), nullable=True),
        sa.Column("reports_to", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_token_hash", "sessions", ["token_hash"], unique=True)

    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_login_attempts_username", "login_attempts", ["username"])
    op.create_index("ix_login_attempts_attempted_at", "login_attempts", ["attempted_at"])


def downgrade() -> None:
    op.drop_index("ix_login_attempts_attempted_at", table_name="login_attempts")
    op.drop_index("ix_login_attempts_username", table_name="login_attempts")
    op.drop_table("login_attempts")

    op.drop_index("ix_sessions_token_hash", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")

    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")

    sa.Enum("STUDENT", "INSTRUCTOR", "REVIEWER", "FINANCE_CLERK", "ADMIN", name="userrole").drop(
        op.get_bind(), checkfirst=True
    )
