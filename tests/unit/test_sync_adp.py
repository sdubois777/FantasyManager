"""Unit tests for scripts/sync_adp.py — name normalization + ADP matching.

The DB/scrape boundary (sync_adp) is integration-tested elsewhere; here we test
the pure pieces: normalize_name (frontend mirror) and apply_adp (matching).
"""
from __future__ import annotations

from types import SimpleNamespace

from scripts.sync_adp import normalize_name, apply_adp


def _p(name: str, position: str = "WR"):
    return SimpleNamespace(
        name=name, position=position, adp_fantasypros=None, adp_scoring=None
    )


class TestNormalizeName:
    def test_strips_generational_suffix(self):
        assert normalize_name("Travis Etienne Jr.") == "travis etienne"
        assert normalize_name("Kenneth Walker III") == "kenneth walker"

    def test_hyphen_maps_to_space(self):
        # The canonical Amon-Ra case: hyphenated == spaced.
        assert normalize_name("Amon-Ra St. Brown") == "amon ra st brown"
        assert normalize_name("Amon-Ra St. Brown") == normalize_name("Amon Ra St. Brown")

    def test_drops_punctuation_and_lowercases(self):
        assert normalize_name("Ja'Marr Chase") == "jamarr chase"
        assert normalize_name("A.J. Brown") == "aj brown"

    def test_safe_on_none(self):
        assert normalize_name(None) == ""


def test_sync_adp_matches_players():
    players = [_p("Amon-Ra St. Brown", "WR"), _p("Bijan Robinson", "RB")]
    adp_data = [
        {"name": "Amon Ra St. Brown", "position": "WR", "adp": 8.5},  # punctuation diff
        {"name": "Bijan Robinson", "position": "RB", "adp": 3.0},
        {"name": "Nobody Here", "position": "TE", "adp": 99.0},        # no match
    ]

    summary = apply_adp(adp_data, players, "ppr")

    assert summary == {"matched": 2, "missed": 1, "scoring": "ppr", "total": 3}
    assert players[0].adp_fantasypros == 8.5  # matched despite spelling difference
    assert players[1].adp_fantasypros == 3.0


def test_sync_adp_normalize_name():
    # Suffix-only difference must still match.
    players = [_p("Michael Pittman", "WR")]
    summary = apply_adp(
        [{"name": "Michael Pittman Jr.", "position": "WR", "adp": 40.0}], players, "ppr"
    )
    assert summary["matched"] == 1
    assert players[0].adp_fantasypros == 40.0


def test_sync_adp_scoring_format_stored():
    players = [_p("Bijan Robinson", "RB")]
    apply_adp(
        [{"name": "Bijan Robinson", "position": "RB", "adp": 3.0}], players, "half_ppr"
    )
    assert players[0].adp_scoring == "half_ppr"


def test_sync_adp_ambiguous_name_disambiguated_by_position():
    # Two distinct players share a normalized name — position breaks the tie.
    rb = _p("Jonathan Taylor", "RB")
    wr = _p("Jonathan Taylor", "WR")
    apply_adp(
        [{"name": "Jonathan Taylor", "position": "RB", "adp": 10.0}], [rb, wr], "ppr"
    )
    assert rb.adp_fantasypros == 10.0
    assert wr.adp_fantasypros is None  # not wrongly assigned


def test_sync_adp_skips_rows_with_no_adp():
    players = [_p("Bijan Robinson", "RB")]
    summary = apply_adp(
        [{"name": "Bijan Robinson", "position": "RB", "adp": None}], players, "ppr"
    )
    assert summary["matched"] == 0
    assert players[0].adp_fantasypros is None
