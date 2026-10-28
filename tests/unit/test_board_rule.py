"""M6/M7 name-board rule over closed-set candidates (pure function)."""
import json
from pathlib import Path

from agent.visual_observation import CandidateObservation, board_choice

CANDIDATES = [
    {"id": "local:gwanghwamun", "name_ko": "광화문", "name_hanja": "光化門"},
    {"id": "local:geunjeongjeon", "name_ko": "근정전", "name_hanja": "勤政殿"},
    {"id": "local:bukchon", "name_ko": "북촌한옥마을"},  # no official Hanja board name in the data
]
OTHERS = [{"name_ko": "경회루", "name_hanja": "慶會樓"}, {"name_ko": "토속촌삼계탕"}]


def observe(place_id="local:geunjeongjeon", board=None, cues=("double roof",)):
    return CandidateObservation(visual_basis="Hall.", visual_cues=list(cues), scene_kind="landmark",
                                place_id=place_id, confidence="medium", name_board_text=board)


def test_hanja_board_matches_forward_and_reversed():
    assert board_choice(observe(board="光化門"), CANDIDATES, OTHERS) == ("local:gwanghwamun", "board_match")
    assert board_choice(observe(board="門化光"), CANDIDATES, OTHERS) == ("local:gwanghwamun", "board_match")
    assert board_choice(observe("unknown", board="勤政殿", cues=()), CANDIDATES, OTHERS) == \
        ("local:geunjeongjeon", "board_match")


def test_hangul_name_for_a_hanja_board_place_is_not_evidence():
    # M7 decision 2: the model restating "광화문" falls back to the cue rule, it neither adopts nor rejects.
    assert board_choice(observe(board="광화문"), CANDIDATES, OTHERS) == ("local:geunjeongjeon", "restated_name")
    assert board_choice(observe(board="경회루", cues=()), CANDIDATES, OTHERS) == (None, "restated_name")
    assert board_choice(observe(board="光化門 광화문"), CANDIDATES, OTHERS) == ("local:gwanghwamun", "board_match")


def test_hangul_board_still_counts_for_places_without_a_hanja_name():
    assert board_choice(observe(board="북촌한옥마을"), CANDIDATES, OTHERS) == ("local:bukchon", "board_match")


def test_board_naming_another_place_or_nothing_known_rejects():
    assert board_choice(observe(board="門化光"), CANDIDATES[1:], OTHERS) == (None, "board_mismatch")
    assert board_choice(observe(board="樓會慶"), CANDIDATES, OTHERS) == (None, "board_other_place")
    assert board_choice(observe(board="門漢大"), CANDIDATES, OTHERS) == (None, "board_mismatch")
    assert board_choice(observe("local:bukchon", board="인사동"), CANDIDATES, OTHERS) == (None, "board_mismatch")


def test_board_in_a_script_the_chosen_place_has_no_name_in_says_nothing():
    # A Hanja shop sign photographed in Bukchon (eval bukchon-04), and a Hangul name for a Hanja-board hall.
    assert board_choice(observe("local:bukchon", board="東琳祐工房"), CANDIDATES, OTHERS) == ("local:bukchon", "cues")
    assert board_choice(observe(board="인정전"), CANDIDATES, OTHERS) == ("local:geunjeongjeon", "cues")


def test_missing_or_one_character_board_uses_the_cue_rule():
    assert board_choice(observe(board=None), CANDIDATES, OTHERS) == ("local:geunjeongjeon", "cues")
    assert board_choice(observe(board="門"), CANDIDATES, OTHERS) == ("local:geunjeongjeon", "cues")
    assert board_choice(observe(board=None, cues=()), CANDIDATES, OTHERS) == (None, "cues")


def test_catalog_hanja_names_cite_an_official_source_quote():
    root = Path(__file__).resolve().parents[2] / "data"
    catalog = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
    sources = {item["id"]: item for item in json.loads((root / "evidence.json").read_text(encoding="utf-8"))["name_sources"]}
    named = {place["place_id"]: place for place in catalog["places"] if place.get("name_hanja")}
    assert set(named) == {"local:gyeongbokgung", "local:gwanghwamun", "local:geunjeongjeon", "local:gyeonghoeru"}
    for place_id, place in named.items():
        source = sources[place["name_hanja_source_id"]]
        assert source["place_ids"] == [place_id] and source["name_hanja"] == place["name_hanja"]
        assert place["name_hanja"] in source["quote"] and source["source"].startswith("https://")
