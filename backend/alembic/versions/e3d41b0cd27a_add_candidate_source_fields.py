"""add candidate source fields

Revision ID: e3d41b0cd27a
Revises: 998627ffd761
Create Date: 2026-10-07 14:41:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e3d41b0cd27a'
down_revision: Union[str, Sequence[str], None] = '998627ffd761'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('candidates', sa.Column('cv_filename', sa.String(length=255), nullable=True))
    op.add_column(
        'candidates',
        sa.Column('source', sa.String(length=20), nullable=False, server_default='upload'),
    )
    op.add_column('candidates', sa.Column('source_file_id', sa.String(length=200), nullable=True))
    op.add_column('candidates', sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True))
    op.alter_column('candidates', 'full_name', existing_type=sa.String(length=255), nullable=True)
    op.alter_column('candidates', 'email', existing_type=sa.String(length=255), nullable=True)
    op.create_unique_constraint(
        'uq_candidates_source_file_id', 'candidates', ['source_file_id']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_candidates_source_file_id', 'candidates', type_='unique')
    op.alter_column('candidates', 'email', existing_type=sa.String(length=255), nullable=False)
    op.alter_column('candidates', 'full_name', existing_type=sa.String(length=255), nullable=False)
    op.drop_column('candidates', 'applied_at')
    op.drop_column('candidates', 'source_file_id')
    op.drop_column('candidates', 'source')
    op.drop_column('candidates', 'cv_filename')