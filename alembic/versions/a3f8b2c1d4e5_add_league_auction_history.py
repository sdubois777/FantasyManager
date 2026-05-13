"""add_league_auction_history

Revision ID: a3f8b2c1d4e5
Revises: 7e1af623cb4b
Create Date: 2026-05-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'a3f8b2c1d4e5'
down_revision: Union[str, None] = '7e1af623cb4b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add market_value_league column to players
    op.add_column('players', sa.Column('market_value_league', sa.Numeric(5, 2), nullable=True))

    # Create league_auction_history table
    op.create_table(
        'league_auction_history',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('player_id', UUID(as_uuid=True), sa.ForeignKey('players.id'), nullable=False),
        sa.Column('season_year', sa.Integer(), nullable=False),
        sa.Column('price', sa.Integer(), nullable=False),
        sa.Column('team_key', sa.String(50), nullable=True),
        sa.Column('source', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('player_id', 'season_year', 'source', name='uq_auction_player_season_source'),
    )


def downgrade() -> None:
    op.drop_table('league_auction_history')
    op.drop_column('players', 'market_value_league')
