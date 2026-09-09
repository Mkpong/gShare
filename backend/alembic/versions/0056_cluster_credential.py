"""Store a remote cluster's kubeconfig, encrypted at rest.

Registration validated the uploaded kubeconfig and then threw it away, keeping only a reference
string. Every later operation re-read the credential from a file nothing created, and when it was
missing the client fell back to the control plane's own service account aimed at the remote
apiserver — an opaque 401 instead of "no credential for this cluster".

Revision ID: 0056_cluster_credential
Revises: 0055_session_privileged
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0056_cluster_credential"
down_revision = "0055_session_privileged"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cluster", sa.Column("kubeconfig_encrypted", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("cluster", "kubeconfig_encrypted")
