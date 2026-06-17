"""Pure-logic tests for the FantasyPros ADP parser.

The Playwright DOM extraction is verified live (sync_adp match counts); here we
test the position-rank helper that turns FP's "POS" cell ("RB1") into a bare
position ("RB").
"""
from backend.integrations.fantasypros import _position_from_pos_rank


def test_position_from_pos_rank_strips_rank():
    assert _position_from_pos_rank("RB1") == "RB"
    assert _position_from_pos_rank("WR12") == "WR"
    assert _position_from_pos_rank("QB10") == "QB"
    assert _position_from_pos_rank("TE5") == "TE"


def test_position_from_pos_rank_handles_dst_and_k():
    assert _position_from_pos_rank("DST3") == "DST"
    assert _position_from_pos_rank("K7") == "K"


def test_position_from_pos_rank_uppercases_and_trims():
    assert _position_from_pos_rank("  rb1 ") == "RB"


def test_position_from_pos_rank_empty_safe():
    assert _position_from_pos_rank("") == ""
    assert _position_from_pos_rank(None) == ""
