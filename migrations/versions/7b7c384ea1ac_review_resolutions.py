"""review resolutions

Revision ID: 7b7c384ea1ac
Revises: 1912a237ecb7
Create Date: 2026-10-16 14:16:32.178638

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '7b7c384ea1ac'
down_revision = '1912a237ecb7'
branch_labels = None
depends_on = None


def upgrade():
    # Create the review queue resolution table. The partial unique
    # canonical-title indexes from the previous migration are managed
    # there and must not be recreated here.
    op.create_table('review_resolutions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('history_event_id', sa.Integer(), nullable=False),
    sa.Column('action', sa.String(length=30), nullable=False),
    sa.Column('target_item_id', sa.Integer(), nullable=True),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['history_event_id'], ['history_events.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('review_resolutions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_review_resolutions_history_event_id'), ['history_event_id'], unique=True)


def downgrade():
    with op.batch_alter_table('review_resolutions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_review_resolutions_history_event_id'))

    op.drop_table('review_resolutions')
