"""Let a deleted organization's name be used again.

Organizations are soft-deleted, but the UNIQUE constraint on `name` counted the deleted rows too,
so an organization that had been removed kept its name forever — re-creating it answered 409
"organization name already exists" against a row nobody could see. Uniqueness now applies to
live rows only, the way clusters already do it.

Revision ID: 0061_org_name_unique_live
Revises: 0060_storage_pool_node_ondelete
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0061_org_name_unique_live"
down_revision = "0060_storage_pool_node_ondelete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_organization_name", "organization", type_="unique")
    op.create_index(
        "uq_organization_name_live", "organization", ["name"], unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_organization_name_live", table_name="organization")
    op.create_unique_constraint("uq_organization_name", "organization", ["name"])
