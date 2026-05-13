"""Debug clean_season_baseline computation for Barkley."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.integrations import nfl_data
from backend.utils.seasons import get_analysis_seasons, get_current_season
from backend.agents.player_profiles import _compute_clean_baseline


def main() -> None:
    analysis_seasons = get_analysis_seasons(3)
    current_season = get_current_season()
    print(f"Analysis seasons: {analysis_seasons}, current: {current_season}")

    for season in analysis_seasons:
        try:
            ts_df = nfl_data.compute_target_share(season)
            # Find Barkley
            mask = ts_df["player_name"].str.contains("Barkley", case=False, na=False)
            rows = ts_df[mask]
            if rows.empty:
                print(f"  {season}: Barkley NOT FOUND")
            else:
                for _, row in rows.iterrows():
                    team = row.get("recent_team", "?")
                    games = int(row.get("games", 0) or 0)
                    rec = int(row.get("total_receptions", 0) or 0)
                    rec_yards = int(row.get("total_rec_yards", 0) or 0)
                    rec_tds = int(row.get("total_rec_tds", 0) or 0)
                    rush_yards = int(row.get("total_rush_yards", 0) or 0)
                    rush_tds = int(row.get("total_rush_tds", 0) or 0)
                    ppr_pg = row.get("ppr_per_game", None)
                    print(f"  {season} ({team}): {games}g, rec={rec}/{rec_yards}yd/{rec_tds}td, rush={rush_yards}yd/{rush_tds}td, ppr/g={ppr_pg:.1f}")
        except Exception as e:
            print(f"  {season}: ERROR — {e}")

    # Now test _compute_clean_baseline manually
    print("\n--- Testing _compute_clean_baseline ---")
    seasons_data = []
    for season in analysis_seasons:
        try:
            ts_df = nfl_data.compute_target_share(season)
            mask = (
                ts_df["player_name"].str.contains("Barkley", case=False, na=False) &
                (ts_df["recent_team"] == "PHI")
            )
            rows = ts_df[mask]
            if rows.empty:
                seasons_data.append({"year": season, "games": 0, "backup_qb_season": False, "note": "no data"})
            else:
                row = rows.iloc[0]
                games = int(row.get("games", 0) or 0)
                seasons_data.append({
                    "year": season,
                    "games": games,
                    "backup_qb_season": False,
                    "receptions": int(row.get("total_receptions", 0) or 0),
                    "rec_yards": int(row.get("total_rec_yards", 0) or 0),
                    "rec_tds": int(row.get("total_rec_tds", 0) or 0),
                    "rush_yards": int(row.get("total_rush_yards", 0) or 0),
                    "rush_tds": int(row.get("total_rush_tds", 0) or 0),
                })
        except Exception as e:
            seasons_data.append({"year": season, "games": 0, "note": f"error: {e}"})

    print(f"Seasons data for Barkley/PHI: {seasons_data}")
    baseline = _compute_clean_baseline(seasons_data)
    print(f"Computed baseline: {baseline}")


if __name__ == "__main__":
    main()
