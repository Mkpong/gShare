"""Align the live schema with the models so `alembic check` is clean.

Revision ID: 0063_schema_alignment
Revises: 0062_volume_placement

Every item here is a name, a type or a nullability that the hand-written migrations left
different from what the models declare; none changes what the tables hold:

- two CHECK constraints carried the naming convention twice
  (ck_credit_wallet_ck_credit_wallet_wallet_sigma, ck_gpu_device_ck_gpu_device_no_overcommit);
- the project -> group rename kept the old index names (ix_*_project_id);
- image_build.build_args was created as JSON, the model says JSONB;
- five tables were created with nullable created_at/updated_at (TimestampMixin is NOT NULL).

Postgres only: the SQLite test harness builds the schema from the models directly.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0063_schema_alignment"
down_revision = "0062_volume_placement"
branch_labels = None
depends_on = None

_CHECKS = {
    # table: (name on disk, name in the models)
    "credit_wallet": ("ck_credit_wallet_ck_credit_wallet_wallet_sigma", "ck_credit_wallet_wallet_sigma"),
    "gpu_device": ("ck_gpu_device_ck_gpu_device_no_overcommit", "ck_gpu_device_no_overcommit"),
}
_INDEXES = {
    # old name: new name
    "ix_project_org_id": "ix_group_org_id",
    "ix_image_build_project_id": "ix_image_build_group_id",
    "ix_membership_project_id": "ix_membership_group_id",
    "ix_session_project_id": "ix_session_group_id",
}
_TIMESTAMPED = ("node_pool", "node_pool_grant", "resource_request", "session_event", "system_setting")


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _rename_constraint(table: str, old: str, new: str) -> None:
    # Guarded: a database whose schema came from a different path may already carry the new
    # name, and the rename must not fail the whole upgrade over it.
    op.execute(sa.text(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{old}')
               AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{new}') THEN
                EXECUTE 'ALTER TABLE "{table}" RENAME CONSTRAINT {old} TO {new}';
            END IF;
        END $$;
    """))


def _rename_index(old: str, new: str) -> None:
    op.execute(sa.text(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_class WHERE relname = '{old}' AND relkind = 'i')
               AND NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = '{new}' AND relkind = 'i') THEN
                EXECUTE 'ALTER INDEX {old} RENAME TO {new}';
            END IF;
        END $$;
    """))


def upgrade() -> None:
    if not _is_postgres():
        return
    for table, (old, new) in _CHECKS.items():
        _rename_constraint(table, old, new)
    for old, new in _INDEXES.items():
        _rename_index(old, new)
    op.execute(sa.text(
        "ALTER TABLE image_build ALTER COLUMN build_args TYPE JSONB USING build_args::jsonb"
    ))
    for table in _TIMESTAMPED:
        for col in ("created_at", "updated_at"):
            # Backfill first: a NULL timestamp on an old row would otherwise fail SET NOT NULL.
            op.execute(sa.text(f'UPDATE "{table}" SET {col} = now() WHERE {col} IS NULL'))
            op.alter_column(table, col, existing_type=sa.DateTime(timezone=True), nullable=False)


def downgrade() -> None:
    if not _is_postgres():
        return
    for table in _TIMESTAMPED:
        for col in ("created_at", "updated_at"):
            op.alter_column(table, col, existing_type=sa.DateTime(timezone=True), nullable=True)
    op.execute(sa.text(
        "ALTER TABLE image_build ALTER COLUMN build_args TYPE JSON USING build_args::json"
    ))
    for old, new in _INDEXES.items():
        _rename_index(new, old)
    for table, (old, new) in _CHECKS.items():
        _rename_constraint(table, new, old)
