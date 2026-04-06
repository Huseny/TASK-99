"""iteration 2 integration and dedup hardening

Revision ID: 0014_iter2_integrations_dedup
Revises: 0013_nullable_audit_actor
Create Date: 2026-04-06 14:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "0014_iter2_integrations_dedup"
down_revision = "0013_nullable_audit_actor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("source_client_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("external_id", sa.String(length=120), nullable=True))
        batch_op.create_index("ix_users_source_client_id", ["source_client_id"])
        batch_op.create_index("ix_users_external_id", ["external_id"])
        batch_op.create_unique_constraint("uq_users_source_external", ["source_client_id", "external_id"])

    with op.batch_alter_table("scoring_forms") as batch_op:
        batch_op.add_column(sa.Column("organization_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("source_client_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("external_id", sa.String(length=120), nullable=True))
        batch_op.create_index("ix_scoring_forms_organization_id", ["organization_id"])
        batch_op.create_index("ix_scoring_forms_source_client_id", ["source_client_id"])
        batch_op.create_index("ix_scoring_forms_external_id", ["external_id"])
        batch_op.create_unique_constraint("uq_scoring_forms_source_external", ["source_client_id", "external_id"])
        batch_op.create_foreign_key("fk_scoring_forms_organization_id", "organizations", ["organization_id"], ["id"])

    with op.batch_alter_table("integration_clients") as batch_op:
        batch_op.add_column(sa.Column("organization_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_integration_clients_organization_id", ["organization_id"])
        batch_op.create_foreign_key("fk_integration_clients_organization_id", "organizations", ["organization_id"], ["id"])

    op.create_table(
        "integration_imports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("import_type", sa.String(length=64), nullable=False),
        sa.Column("import_id", sa.String(length=120), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("client_id", "import_type", "import_id", name="uq_integration_import_client_type_id"),
    )
    op.create_index("ix_integration_imports_client_id", "integration_imports", ["client_id"])

    with op.batch_alter_table("ledger_entries") as batch_op:
        batch_op.add_column(sa.Column("external_reference_id", sa.String(length=120), nullable=True))
        batch_op.create_index("ix_ledger_entries_external_reference_id", ["external_reference_id"])

    with op.batch_alter_table("bank_statement_lines") as batch_op:
        batch_op.add_column(sa.Column("reference_id", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("payment_method", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("matched_entry_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("explanation", sa.Text(), nullable=True))
        batch_op.create_foreign_key("fk_bank_statement_lines_matched_entry_id", "ledger_entries", ["matched_entry_id"], ["id"])

    with op.batch_alter_table("reconciliation_reports") as batch_op:
        batch_op.add_column(sa.Column("statement_total", sa.Float(), nullable=False, server_default=sa.text("0")))
        batch_op.add_column(sa.Column("ledger_total", sa.Float(), nullable=False, server_default=sa.text("0")))
        batch_op.add_column(sa.Column("variance_total", sa.Float(), nullable=False, server_default=sa.text("0")))

    with op.batch_alter_table("courses") as batch_op:
        batch_op.create_unique_constraint("uq_courses_org_code", ["organization_id", "code"])

    with op.batch_alter_table("sections") as batch_op:
        batch_op.create_unique_constraint("uq_sections_term_code", ["term_id", "code"])


def downgrade() -> None:
    with op.batch_alter_table("sections") as batch_op:
        batch_op.drop_constraint("uq_sections_term_code", type_="unique")

    with op.batch_alter_table("courses") as batch_op:
        batch_op.drop_constraint("uq_courses_org_code", type_="unique")

    with op.batch_alter_table("reconciliation_reports") as batch_op:
        batch_op.drop_column("variance_total")
        batch_op.drop_column("ledger_total")
        batch_op.drop_column("statement_total")

    with op.batch_alter_table("bank_statement_lines") as batch_op:
        batch_op.drop_constraint("fk_bank_statement_lines_matched_entry_id", type_="foreignkey")
        batch_op.drop_column("explanation")
        batch_op.drop_column("matched_entry_id")
        batch_op.drop_column("payment_method")
        batch_op.drop_column("reference_id")

    with op.batch_alter_table("ledger_entries") as batch_op:
        batch_op.drop_index("ix_ledger_entries_external_reference_id")
        batch_op.drop_column("external_reference_id")

    op.drop_index("ix_integration_imports_client_id", table_name="integration_imports")
    op.drop_table("integration_imports")

    with op.batch_alter_table("integration_clients") as batch_op:
        batch_op.drop_constraint("fk_integration_clients_organization_id", type_="foreignkey")
        batch_op.drop_index("ix_integration_clients_organization_id")
        batch_op.drop_column("organization_id")

    with op.batch_alter_table("scoring_forms") as batch_op:
        batch_op.drop_constraint("fk_scoring_forms_organization_id", type_="foreignkey")
        batch_op.drop_constraint("uq_scoring_forms_source_external", type_="unique")
        batch_op.drop_index("ix_scoring_forms_external_id")
        batch_op.drop_index("ix_scoring_forms_source_client_id")
        batch_op.drop_index("ix_scoring_forms_organization_id")
        batch_op.drop_column("external_id")
        batch_op.drop_column("source_client_id")
        batch_op.drop_column("organization_id")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("uq_users_source_external", type_="unique")
        batch_op.drop_index("ix_users_external_id")
        batch_op.drop_index("ix_users_source_client_id")
        batch_op.drop_column("external_id")
        batch_op.drop_column("source_client_id")
