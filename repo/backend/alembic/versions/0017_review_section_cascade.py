"""cascade review-domain FKs on section / round / assignment / score delete

Revision ID: 0017_review_section_cascade
Revises: 0016_nullable_review_rnd_crtr
Create Date: 2026-04-18 14:00:00
"""

from alembic import op

revision = "0017_review_section_cascade"
down_revision = "0016_nullable_review_rnd_crtr"
branch_labels = None
depends_on = None


# (table, constraint_name, local_column, referent_table, referent_column)
_CASCADE_FKS = [
    ("review_rounds", "review_rounds_section_id_fkey", "section_id", "sections", "id"),
    ("reviewer_assignments", "reviewer_assignments_round_id_fkey", "round_id", "review_rounds", "id"),
    ("reviewer_assignments", "reviewer_assignments_section_id_fkey", "section_id", "sections", "id"),
    ("scores", "scores_assignment_id_fkey", "assignment_id", "reviewer_assignments", "id"),
    ("outlier_flags", "outlier_flags_round_id_fkey", "round_id", "review_rounds", "id"),
    ("outlier_flags", "outlier_flags_score_id_fkey", "score_id", "scores", "id"),
    ("recheck_requests", "recheck_requests_round_id_fkey", "round_id", "review_rounds", "id"),
    ("recheck_requests", "recheck_requests_section_id_fkey", "section_id", "sections", "id"),
]


def upgrade() -> None:
    for table, name, column, ref_table, ref_column in _CASCADE_FKS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(
            name,
            table,
            ref_table,
            [column],
            [ref_column],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    for table, name, column, ref_table, ref_column in _CASCADE_FKS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(
            name,
            table,
            ref_table,
            [column],
            [ref_column],
        )
