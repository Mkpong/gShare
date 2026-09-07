"""Drop the notice and inquiry boards.

The boards were removed from the product: the announcement and support features are gone from the
console and the API, and the tables go with them. This is a one-way migration by decision — the
data was declared disposable when the feature was retired.

Revision ID: 0051_drop_boards
Revises: 0050_session_liveness
"""
from alembic import op

revision = "0051_drop_boards"
down_revision = "0050_session_liveness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("inquiry_reply")
    op.drop_table("inquiry")
    op.drop_table("notice")


def downgrade() -> None:
    raise RuntimeError("the boards were retired; restore the tables from a backup if needed")
