"""add prior season market value columns

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-05-18

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b9c0d1e2f3a4"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("players", sa.Column("market_value_prior_season", sa.Numeric(8, 2), nullable=True))
    op.add_column("players", sa.Column("market_value_prior_season_year", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("players", "market_value_prior_season_year")
    op.drop_column("players", "market_value_prior_season")
