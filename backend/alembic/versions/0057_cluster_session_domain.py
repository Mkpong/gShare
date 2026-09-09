"""Per-cluster session hostname.

The connect URL was built from one global SESSION_DOMAIN with no reference to the session's
cluster, so a session running on a second cluster was advertised at the first cluster's hostname —
where its ingress does not exist. Each cluster terminates its own ingress, so the hostname belongs
to the cluster.

Revision ID: 0057_cluster_session_domain
Revises: 0056_cluster_credential
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0057_cluster_session_domain"
down_revision = "0056_cluster_credential"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cluster", sa.Column("session_domain", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("cluster", "session_domain")
