"""M6 decision 1: deterministic name-board rule over closed-set candidates (pure function)."""
from agent.visual_observation import CandidateObservation, board_choice

CANDIDATES = [
    {"id": "local:gwanghwamun", "name_ko": "광화문"},
    {"id": "local:geunjeongjeon", "name_ko": "근정전"},
    {"id": "local:gyeongbokgung", "name_ko": "경복궁"},
]
OTHERS = [{"name_ko": "북촌한옥마을"}]


def observe(place_id="local:geunjeongjeon", board=None, cues=("double roof",)):
    return CandidateObservation(visual_basis="Hall.", visual_cues=list(cues), scene_kind="landmark",
                                place_id=place_id, confidence="medium", name_board_text=board)


def test_board_matches_forward_and_reversed():
    assert board_choice(observe(board="光化門 광화문"), CANDIDATES, OTHERS) == ("local:gwanghwamun", "board_match")
    assert board_choice(observe(board="문화광"), CANDIDATES, OTHERS) == ("local:gwanghwamun", "board_match")
    assert board_choice(observe("unknown", board="근정전", cues=()), CANDIDATES, OTHERS) == ("local:geunjeongjeon", "board_match")


def test_board_naming_another_place_or_nothing_known_rejects():
    assert board_choice(observe(board="북촌한옥마을"), CANDIDATES, OTHERS) == (None, "board_other_place")
    assert board_choice(observe(board="인정전"), CANDIDATES, OTHERS) == (None, "board_mismatch")


def test_hanja_board_needs_hanja_names_in_the_data():
    assert board_choice(observe(board="門化光"), CANDIDATES, OTHERS) == ("local:geunjeongjeon", "cues")
    with_hanja = [{**CANDIDATES[0], "name_hanja": "光化門"}, *CANDIDATES[1:]]
    assert board_choice(observe(board="門化光"), with_hanja, OTHERS) == ("local:gwanghwamun", "board_match")
    assert board_choice(observe(board="仁政殿"), with_hanja, OTHERS) == (None, "board_mismatch")


def test_missing_or_one_character_board_uses_the_cue_rule():
    assert board_choice(observe(board=None), CANDIDATES, OTHERS) == ("local:geunjeongjeon", "cues")
    assert board_choice(observe(board="門"), CANDIDATES, OTHERS) == ("local:geunjeongjeon", "cues")
    assert board_choice(observe(board=None, cues=()), CANDIDATES, OTHERS) == (None, "cues")
