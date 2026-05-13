"""
CLI script to import league auction history from a CSV file.

Usage:
    python scripts/import_league_auction.py --csv data/league_2025.csv --year 2025
"""
import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import AsyncSessionLocal
from backend.engines.league_auction import import_league_auction_csv, refresh_market_value_league


async def main(csv_path: str, year: int) -> None:
    path = Path(csv_path)
    if not path.exists():
        print(f"ERROR: File not found: {csv_path}")
        sys.exit(1)

    async with AsyncSessionLocal() as session:
        print(f"Importing league auction data from {csv_path} (year={year})...")
        result = await import_league_auction_csv(session, csv_path, year)
        print(f"  Matched:   {result['matched']}")
        print(f"  Unmatched: {result['unmatched']}")
        if result["unmatched_names"]:
            print(f"  Unmatched names: {', '.join(result['unmatched_names'][:10])}")
            if len(result["unmatched_names"]) > 10:
                print(f"    ... and {len(result['unmatched_names']) - 10} more")

        print("\nRefreshing market_value_league on player records...")
        refresh = await refresh_market_value_league(session, year)
        print(f"  Updated: {refresh['updated']} players (year={refresh['year_used']})")

    print("\nDone.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import league auction history from CSV")
    parser.add_argument("--csv", required=True, help="Path to CSV file")
    parser.add_argument("--year", required=True, type=int, help="Season year")
    args = parser.parse_args()

    asyncio.run(main(args.csv, args.year))
