"""add_user_id_to_user_preferences

Revision ID: 407ae5ce903c
Revises: 36bb0c766cba
Create Date: 2026-05-14 14:54:12.466689

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '407ae5ce903c'
down_revision: Union[str, None] = '36bb0c766cba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'user_preferences',
        sa.Column('user_id', UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        'ix_user_preferences_user_id',
        'user_preferences',
        ['user_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_user_preferences_user_id', table_name='user_preferences')
    op.drop_column('user_preferences', 'user_id')
