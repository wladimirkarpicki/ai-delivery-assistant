"""revoked tokens

Logout previously recorded the token id in an in-process set, so a
revoked token was accepted again after a restart until its own expiry,
up to TOKEN_TTL_HOURS. The set is now persisted here: the id is the
primary key so a check is one index lookup, and expires_at lets a check
prune rows that no longer matter instead of growing forever.

No foreign key to users: a revoked token must outlive the deletion of
the account it belonged to, otherwise deleting a user revives every
token they ever had.

Revision ID: d4e7f1a2b3c5
Revises: c2f6b8d4a1e9
Create Date: 2026-11-09 16:30:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = 'd4e7f1a2b3c5'
down_revision = 'c2f6b8d4a1e9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'revoked_tokens',
        sa.Column('jti', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('jti'),
    )


def downgrade():
    op.drop_table('revoked_tokens')
