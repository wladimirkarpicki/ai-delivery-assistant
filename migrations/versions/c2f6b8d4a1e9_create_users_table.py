"""create users table

Authentication with admin/user roles: a standalone users table for
the first-run admin bootstrap, sign-ins, and admin-managed accounts.
No relations - sessions are stateless JWTs, and deleted accounts are
detected by the token check re-reading this table on every request.

Revision ID: c2f6b8d4a1e9
Revises: a89627c92af8
Create Date: 2026-10-25 00:55:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'c2f6b8d4a1e9'
down_revision = 'a89627c92af8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('username', sa.String(length=80), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False, server_default='user'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
    )


def downgrade():
    op.drop_table('users')
