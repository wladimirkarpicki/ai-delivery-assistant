"""title embeddings

Add a nullable title_embedding JSON column to risks, blockers, action
items, and decisions for semantic candidate matching. Vectors are
backfilled lazily by the application; the partial unique canonical
indexes are managed by an earlier migration and are untouched here.

Revision ID: a89627c92af8
Revises: 7b7c384ea1ac
Create Date: 2026-10-16 16:42:18.666115

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a89627c92af8'
down_revision = '7b7c384ea1ac'
branch_labels = None
depends_on = None


_TABLES = ("risks", "blockers", "action_items", "decisions")


def upgrade():
    for table in _TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column('title_embedding', sa.JSON(), nullable=True))


def downgrade():
    for table in reversed(_TABLES):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column('title_embedding')
