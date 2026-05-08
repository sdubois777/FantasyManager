"""League Auction History — historical auction prices from the user's league."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from backend.database import Base


class LeagueAuctionHistory(Base):
    """One row per player per season per source — tracks what opponents actually paid."""
    __tablename__ = "league_auction_history"
    __table_args__ = (
        UniqueConstraint("player_id", "season_year", "source", name="uq_auction_player_season_source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    season_year: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    team_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # "yahoo" or "manual_csv"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    player = relationship("Player")
