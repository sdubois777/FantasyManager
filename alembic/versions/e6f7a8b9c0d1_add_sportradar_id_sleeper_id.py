"""add sportradar_id and sleeper_id to players

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-05-12

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("players", sa.Column("sportradar_id", sa.String(50), nullable=True))
    op.add_column("players", sa.Column("sleeper_id", sa.String(50), nullable=True))
    op.create_index("ix_players_sportradar_id", "players", ["sportradar_id"])
    op.create_index("ix_players_sleeper_id", "players", ["sleeper_id"])


def downgrade() -> None:
    op.drop_index("ix_players_sleeper_id", table_name="players")
    op.drop_index("ix_players_sportradar_id", table_name="players")
    op.drop_column("players", "sleeper_id")
    op.drop_column("players", "sportradar_id")
