"""add_user_id_user_league_id_to_auction_history

Revision ID: 742ec39b8039
Revises: ce8a4596b413
Create Date: 2026-05-16 14:39:51.071440

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '742ec39b8039'
down_revision: Union[str, None] = 'ce8a4596b413'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('league_auction_history',
        sa.Column('user_id', UUID(as_uuid=True), nullable=True),
    )
    op.add_column('league_auction_history',
        sa.Column('user_league_id', UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_auction_history_user_id', 'league_auction_history', 'users',
        ['user_id'], ['id'], ondelete='CASCADE',
    )
    op.create_foreign_key(
        'fk_auction_history_user_league_id', 'league_auction_history', 'user_leagues',
        ['user_league_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index('ix_auction_history_user_id', 'league_auction_history', ['user_id'])
    op.create_index('ix_auction_history_user_league_id', 'league_auction_history', ['user_league_id'])


def downgrade() -> None:
    op.drop_index('ix_auction_history_user_league_id', table_name='league_auction_history')
    op.drop_index('ix_auction_history_user_id', table_name='league_auction_history')
    op.drop_constraint('fk_auction_history_user_league_id', 'league_auction_history', type_='foreignkey')
    op.drop_constraint('fk_auction_history_user_id', 'league_auction_history', type_='foreignkey')
    op.drop_column('league_auction_history', 'user_league_id')
    op.drop_column('league_auction_history', 'user_id')
