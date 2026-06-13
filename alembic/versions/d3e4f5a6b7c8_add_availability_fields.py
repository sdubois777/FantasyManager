"""add games-based availability fields to player_injury_profiles

Revision ID: d3e4f5a6b7c8
Revises: 42e87b841448
Create Date: 2026-06-13

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "d3e4f5a6b7c8"
down_revision = "42e87b841448"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "player_injury_profiles",
        sa.Column("games_played_history", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "player_injury_profiles",
        sa.Column("avg_games_per_season", sa.Numeric(4, 1), nullable=True),
    )
    op.add_column(
        "player_injury_profiles",
        sa.Column("projected_games", sa.Integer(), nullable=True),
    )
    op.add_column(
        "player_injury_profiles",
        sa.Column("availability_risk", sa.String(20), nullable=True),
    )
    op.add_column(
        "player_injury_profiles",
        sa.Column("availability_trend", sa.String(20), nullable=True),
    )
    op.add_column(
        "player_injury_profiles",
        sa.Column("availability_risk_modifier", sa.Numeric(4, 2), nullable=True),
    )
    op.add_column(
        "player_injury_profiles",
        sa.Column(
            "full_season_absence_flag",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("player_injury_profiles", "full_season_absence_flag")
    op.drop_column("player_injury_profiles", "availability_risk_modifier")
    op.drop_column("player_injury_profiles", "availability_trend")
    op.drop_column("player_injury_profiles", "availability_risk")
    op.drop_column("player_injury_profiles", "projected_games")
    op.drop_column("player_injury_profiles", "avg_games_per_season")
    op.drop_column("player_injury_profiles", "games_played_history")
