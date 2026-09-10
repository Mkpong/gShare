"""Attribute audit rows to a cluster.

With a second cluster attached, an administrator narrowing the console to one cluster still saw
every cluster's audit entries: the rows carried organization and group scope but nothing that
said which cluster a session, node or card action happened on.

Revision ID: 0058_audit_cluster
Revises: 0057_cluster_session_domain
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0058_audit_cluster"
down_revision = "0057_cluster_session_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_log", sa.Column("cluster_id", sa.String(), nullable=True))
    op.create_index("ix_audit_log_cluster_id", "audit_log", ["cluster_id"])
    # Backfill from the targets that can be resolved: sessions and nodes name their cluster,
    # a cluster names itself. Cards are keyed by GPU UUID and resolved through their row.
    op.execute("""
        UPDATE audit_log a SET cluster_id = s.cluster_id
        FROM session s WHERE a.cluster_id IS NULL AND a.target = s.id
    """)
    op.execute("""
        UPDATE audit_log a SET cluster_id = n.cluster_id
        FROM gpu_node n WHERE a.cluster_id IS NULL AND a.target = n.id
    """)
    op.execute("""
        UPDATE audit_log a SET cluster_id = d.cluster_id
        FROM gpu_device d WHERE a.cluster_id IS NULL AND a.target = d.gpu_uuid
    """)
    op.execute("""
        UPDATE audit_log a SET cluster_id = c.id
        FROM cluster c WHERE a.cluster_id IS NULL AND a.target = c.id
    """)


def downgrade() -> None:
    op.drop_index("ix_audit_log_cluster_id", table_name="audit_log")
    op.drop_column("audit_log", "cluster_id")
