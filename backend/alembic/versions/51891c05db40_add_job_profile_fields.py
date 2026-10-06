"""add job profile fields

Revision ID: 51891c05db40
Revises: abf4274405f9
Create Date: 2026-10-06 11:16:58.966200

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '51891c05db40'
down_revision: Union[str, Sequence[str], None] = 'abf4274405f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('jobs', sa.Column('department', sa.String(length=100), nullable=True))
    op.add_column('jobs', sa.Column('location', sa.String(length=100), nullable=True))
    op.add_column(
        'jobs',
        sa.Column('employment_type', sa.String(length=20), nullable=False, server_default='full_time'),
    )
    op.add_column('jobs', sa.Column('min_experience_years', sa.Integer(), nullable=True))
    op.add_column(
        'jobs',
        sa.Column(
            'requirements',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.alter_column('jobs', 'description', existing_type=sa.TEXT(), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('jobs', 'description', existing_type=sa.TEXT(), nullable=False)
    op.drop_column('jobs', 'requirements')
    op.drop_column('jobs', 'min_experience_years')
    op.drop_column('jobs', 'employment_type')
    op.drop_column('jobs', 'location')
    op.drop_column('jobs', 'department')