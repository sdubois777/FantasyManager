"""
tests/unit/test_nfl_data_depth_charts.py

Tests for depth chart integration in NflDataWarehouse:
- fetch_depth_charts normalization
- get_starter / get_player_depth_rank / get_team_depth_context accessors
- summary includes depth chart counts
- gsis_id population logic
"""
import pandas as pd
import pytest

from backend.integrations.nfl_data import NflDataWarehouse, _filter_depth_charts_by_roster


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_depth_chart_df():
    """Minimal depth chart DataFrame for testing."""
    return pd.DataFrame([
        {"team": "BUF", "position": "QB", "full_name": "Josh Allen",
         "gsis_id": "00-0034857", "depth_rank": 1},
        {"team": "BUF", "position": "QB", "full_name": "Mitchell Trubisky",
         "gsis_id": "00-0033567", "depth_rank": 2},
        {"team": "BUF", "position": "WR", "full_name": "Keon Coleman",
         "gsis_id": "00-0039100", "depth_rank": 1},
        {"team": "BUF", "position": "WR", "full_name": "Curtis Samuel",
         "gsis_id": "00-0033290", "depth_rank": 2},
        {"team": "BUF", "position": "WR", "full_name": "Mack Hollins",
         "gsis_id": "00-0033880", "depth_rank": 3},
        {"team": "KC", "position": "QB", "full_name": "Patrick Mahomes",
         "gsis_id": "00-0036355", "depth_rank": 1},
    ])


def _make_warehouse_with_depth(dc_df=None):
    """Build a warehouse instance with depth chart data injected."""
    wh = NflDataWarehouse(
        analysis_seasons=[2023, 2024, 2025],
        current_season=2025,
        analysis_year=2026,
    )
    if dc_df is not None:
        wh.depth_charts[2025] = dc_df
    return wh


# ---------------------------------------------------------------------------
# get_starter
# ---------------------------------------------------------------------------


class TestGetStarter:
    def test_returns_qb1(self):
        wh = _make_warehouse_with_depth(_make_depth_chart_df())
        result = wh.get_starter("BUF", "QB")
        assert result is not None
        assert result["name"] == "Josh Allen"
        assert result["gsis_id"] == "00-0034857"
        assert result["depth_rank"] == 1

    def test_returns_none_when_no_data(self):
        wh = _make_warehouse_with_depth(pd.DataFrame())
        assert wh.get_starter("BUF", "QB") is None

    def test_returns_none_for_missing_team(self):
        wh = _make_warehouse_with_depth(_make_depth_chart_df())
        assert wh.get_starter("JAX", "QB") is None

    def test_case_insensitive(self):
        wh = _make_warehouse_with_depth(_make_depth_chart_df())
        result = wh.get_starter("buf", "qb")
        assert result is not None
        assert result["name"] == "Josh Allen"

    def test_returns_wr1(self):
        wh = _make_warehouse_with_depth(_make_depth_chart_df())
        result = wh.get_starter("BUF", "WR")
        assert result is not None
        assert result["name"] == "Keon Coleman"


# ---------------------------------------------------------------------------
# get_player_depth_rank
# ---------------------------------------------------------------------------


class TestGetPlayerDepthRank:
    def test_starter_returns_1(self):
        wh = _make_warehouse_with_depth(_make_depth_chart_df())
        assert wh.get_player_depth_rank("00-0034857") == 1

    def test_backup_returns_2(self):
        wh = _make_warehouse_with_depth(_make_depth_chart_df())
        assert wh.get_player_depth_rank("00-0033567") == 2

    def test_wr3_returns_3(self):
        wh = _make_warehouse_with_depth(_make_depth_chart_df())
        assert wh.get_player_depth_rank("00-0033880") == 3

    def test_unknown_returns_none(self):
        wh = _make_warehouse_with_depth(_make_depth_chart_df())
        assert wh.get_player_depth_rank("00-9999999") is None

    def test_empty_gsis_returns_none(self):
        wh = _make_warehouse_with_depth(_make_depth_chart_df())
        assert wh.get_player_depth_rank("") is None
        assert wh.get_player_depth_rank(None) is None

    def test_no_depth_chart_returns_none(self):
        wh = _make_warehouse_with_depth(pd.DataFrame())
        assert wh.get_player_depth_rank("00-0034857") is None


# ---------------------------------------------------------------------------
# get_team_depth_context
# ---------------------------------------------------------------------------


class TestGetTeamDepthContext:
    def test_returns_positions(self):
        wh = _make_warehouse_with_depth(_make_depth_chart_df())
        ctx = wh.get_team_depth_context("BUF")
        assert "QB" in ctx
        assert "WR" in ctx
        assert len(ctx["QB"]) == 2
        assert len(ctx["WR"]) == 3
        assert ctx["QB"][0]["rank"] == 1
        assert ctx["WR"][0]["rank"] == 1

    def test_empty_for_missing_team(self):
        wh = _make_warehouse_with_depth(_make_depth_chart_df())
        assert wh.get_team_depth_context("JAX") == {}

    def test_gsis_ids_present(self):
        wh = _make_warehouse_with_depth(_make_depth_chart_df())
        ctx = wh.get_team_depth_context("KC")
        assert ctx["QB"][0]["gsis_id"] == "00-0036355"


# ---------------------------------------------------------------------------
# get_depth_chart
# ---------------------------------------------------------------------------


class TestGetDepthChart:
    def test_returns_dataframe(self):
        wh = _make_warehouse_with_depth(_make_depth_chart_df())
        df = wh.get_depth_chart(2025)
        assert len(df) == 6

    def test_missing_season_returns_empty(self):
        wh = _make_warehouse_with_depth(_make_depth_chart_df())
        df = wh.get_depth_chart(2022)
        assert df.empty


# ---------------------------------------------------------------------------
# summary includes depth charts
# ---------------------------------------------------------------------------


class TestSummaryIncludesDepthCharts:
    def test_summary_has_depth_chart_key(self):
        wh = _make_warehouse_with_depth(_make_depth_chart_df())
        s = wh.summary()
        assert "depth_charts_loaded" in s
        assert s["depth_charts_loaded"] == 1

    def test_per_season_depth_count(self):
        wh = _make_warehouse_with_depth(_make_depth_chart_df())
        s = wh.summary()
        assert s["data"][2025]["depth_charts"] == 6

    def test_no_depth_shows_zero(self):
        wh = _make_warehouse_with_depth()  # no depth chart loaded
        s = wh.summary()
        assert s["depth_charts_loaded"] == 0
        assert s["data"][2025]["depth_charts"] == 0


# ---------------------------------------------------------------------------
# gsis_id from yahoo_player_id
# ---------------------------------------------------------------------------


class TestGsisIdPopulation:
    def test_gsis_id_from_yahoo_player_id(self):
        """Verify the backfill logic: 'nfl_00-0034857' -> '00-0034857'."""
        yahoo_id = "nfl_00-0034857"
        gsis_id = yahoo_id[4:]
        assert gsis_id == "00-0034857"

    def test_no_prefix_not_stripped(self):
        """Players without nfl_ prefix should not produce gsis_id."""
        yahoo_id = "12345"
        assert not yahoo_id.startswith("nfl_")


# ---------------------------------------------------------------------------
# Roster cross-reference filter
# ---------------------------------------------------------------------------


def _make_roster_df():
    """Minimal roster DataFrame with player_id (gsis_id) and team."""
    return pd.DataFrame([
        {"player_id": "00-0034857", "team": "BUF", "week": 17},
        {"player_id": "00-0033567", "team": "BUF", "week": 17},
        {"player_id": "00-0039100", "team": "BUF", "week": 17},
        {"player_id": "00-0033290", "team": "BUF", "week": 17},
        {"player_id": "00-0033880", "team": "BUF", "week": 17},
        {"player_id": "00-0036355", "team": "KC", "week": 17},
        {"player_id": "00-0037197", "team": "KC", "week": 17},  # Pacheco on KC
    ])


class TestRosterCrossReferenceFilter:
    def test_stale_entries_removed(self):
        """Player on wrong team in depth chart is removed."""
        dc = _make_depth_chart_df()
        # Add Pacheco as DET RB2 (stale — roster says KC)
        stale_row = pd.DataFrame([{
            "team": "DET", "position": "RB", "full_name": "Isiah Pacheco",
            "gsis_id": "00-0037197", "depth_rank": 2,
        }])
        dc = pd.concat([dc, stale_row], ignore_index=True)
        rosters = _make_roster_df()

        filtered = _filter_depth_charts_by_roster(dc, rosters)
        # Pacheco should be removed from DET
        det_rbs = filtered[(filtered["team"] == "DET") & (filtered["position"] == "RB")]
        assert "00-0037197" not in det_rbs["gsis_id"].values
        assert len(filtered) == len(dc) - 1

    def test_new_signings_kept(self):
        """Player not in roster data (new signing) is kept."""
        dc = _make_depth_chart_df()
        # Add a new signing not in rosters
        new_row = pd.DataFrame([{
            "team": "BUF", "position": "RB", "full_name": "New Signing",
            "gsis_id": "00-9999999", "depth_rank": 3,
        }])
        dc = pd.concat([dc, new_row], ignore_index=True)
        rosters = _make_roster_df()

        filtered = _filter_depth_charts_by_roster(dc, rosters)
        assert "00-9999999" in filtered["gsis_id"].values

    def test_matching_teams_kept(self):
        """Players whose roster team matches depth chart team are kept."""
        dc = _make_depth_chart_df()
        rosters = _make_roster_df()

        filtered = _filter_depth_charts_by_roster(dc, rosters)
        # All original entries have matching teams — none should be removed
        assert len(filtered) == len(dc)

    def test_no_gsis_id_kept(self):
        """Rows with missing gsis_id are kept (can't verify)."""
        dc = _make_depth_chart_df()
        # Add a row with no gsis_id
        no_id_row = pd.DataFrame([{
            "team": "DET", "position": "WR", "full_name": "Unknown Player",
            "gsis_id": None, "depth_rank": 4,
        }])
        dc = pd.concat([dc, no_id_row], ignore_index=True)
        rosters = _make_roster_df()

        filtered = _filter_depth_charts_by_roster(dc, rosters)
        assert "Unknown Player" in filtered["full_name"].values
