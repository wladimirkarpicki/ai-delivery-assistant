"""canonical titles

Add a canonical_title identity column to risks, blockers, action
items, and decisions, backfill it from the stored titles, and enforce
one row per canonical title per project with partial unique indexes.

Revision ID: 1912a237ecb7
Revises: 8c211c5dcd45
Create Date: 2026-10-16 05:04:44.841659

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '1912a237ecb7'
down_revision = '8c211c5dcd45'
branch_labels = None
depends_on = None


_TABLES = ("risks", "blockers", "action_items", "decisions")


def _normalize_title(title):
    """
    Mirror matching.normalize_title exactly so backfilled rows match
    what the application computes going forward.
    """
    if not isinstance(title, str):
        return ""

    title = title.strip().strip(".,;:!?-–—\"'()[]{}«»„“”")
    return " ".join(title.casefold().split())


def upgrade():
    # New identity column: empty for now, backfilled below.
    for table in _TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    'canonical_title',
                    sa.String(length=300),
                    nullable=False,
                    server_default="",
                )
            )

    # Backfill from stored titles.
    bind = op.get_bind()

    for table in _TABLES:
        rows = bind.execute(
            sa.text(f"SELECT id, title FROM {table}")
        ).fetchall()

        for row in rows:
            canonical = _normalize_title(row.title)

            bind.execute(
                sa.text(
                    f"UPDATE {table} SET canonical_title = :canonical "
                    f"WHERE id = :row_id"
                ),
                {"canonical": canonical, "row_id": row.id},
            )

    # One row per canonical title per project; empty titles (if any)
    # are excluded from the constraint.
    for table in _TABLES:
        op.create_index(
            f"uq_{table}_project_canonical_title",
            table,
            ["project_id", "canonical_title"],
            unique=True,
            postgresql_where=sa.text("canonical_title <> ''"),
            sqlite_where=sa.text("canonical_title <> ''"),
        )


def downgrade():
    for table in _TABLES:
        op.drop_index(
            f"uq_{table}_project_canonical_title",
            table_name=table,
        )

    for table in reversed(_TABLES):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column('canonical_title')
