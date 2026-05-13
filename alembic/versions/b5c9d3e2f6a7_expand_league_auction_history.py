"""expand_league_auction_history

Revision ID: b5c9d3e2f6a7
Revises: a3f8b2c1d4e5
Create Date: 2026-05-08 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'b5c9d3e2f6a7'
down_revision: Union[str, None] = 'a3f8b2c1d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make player_id nullable (historical players may not be in our DB)
    op.alter_column('league_auction_history', 'player_id', nullable=True)

    # Add new columns for Yahoo sync
    op.add_column('league_auction_history', sa.Column('league_key', sa.String(50), nullable=True))
    op.add_column('league_auction_history', sa.Column('yahoo_player_key', sa.String(50), nullable=True))
    op.add_column('league_auction_history', sa.Column('player_name', sa.String(150), nullable=True))
    op.add_column('league_auction_history', sa.Column('position', sa.String(10), nullable=True))
    op.add_column('league_auction_history', sa.Column('manager_name', sa.String(100), nullable=True))
    op.add_column('league_auction_history', sa.Column('draft_pick_number', sa.Integer(), nullable=True))

    # New unique constraint for Yahoo-sourced records (season + source + yahoo player key)
    op.create_unique_constraint(
        'uq_auction_season_source_yahoo_key',
        'league_auction_history',
        ['season_year', 'source', 'yahoo_player_key'],
    )

    # Indexes for fast lookups
    op.create_index('ix_auction_history_season', 'league_auction_history', ['season_year'])
    op.create_index('ix_auction_history_player_name_season', 'league_auction_history', ['player_name', 'season_year'])


def downgrade() -> None:
    op.drop_index('ix_auction_history_player_name_season', table_name='league_auction_history')
    op.drop_index('ix_auction_history_season', table_name='league_auction_history')
    op.drop_constraint('uq_auction_season_source_yahoo_key', 'league_auction_history', type_='unique')
    op.drop_column('league_auction_history', 'draft_pick_number')
    op.drop_column('league_auction_history', 'manager_name')
    op.drop_column('league_auction_history', 'position')
    op.drop_column('league_auction_history', 'player_name')
    op.drop_column('league_auction_history', 'yahoo_player_key')
    op.drop_column('league_auction_history', 'league_key')
    op.alter_column('league_auction_history', 'player_id', nullable=False)
