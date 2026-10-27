"""Contract v1 extensions: generated schemas stay in sync and published examples validate."""
import copy
import json
from pathlib import Path
import unittest

from pydantic import ValidationError

from shared.export_schemas import DIRECTORY, SCHEMAS, rendered
from shared.models import GuideResult, LandmarkCard, NearbyResponse, RequestStatus, RoutesResponse, TtsRequest

EXAMPLES = {
    "landmark-card.ko.json": LandmarkCard, "landmark-card.en.json": LandmarkCard,
    "landmark-card.model-unverified.en.json": LandmarkCard,
    "nearby.food.json": NearbyResponse, "nearby.landmark.json": NearbyResponse, "nearby.error.json": NearbyResponse,
    "routes.en.json": RoutesResponse, "routes.ko.json": RoutesResponse,
    "result.observe.json": GuideResult, "result.story.json": GuideResult,
    "request-status.running.json": RequestStatus, "tts-request.json": TtsRequest,
}


def example(name):
    return json.loads((DIRECTORY / "examples" / name).read_text(encoding="utf-8"))


class ContractTests(unittest.TestCase):
    def test_schema_files_match_models(self):
        for name, model in SCHEMAS.items():
            with self.subTest(name=name):
                path = DIRECTORY / f"{name}.schema.json"
                self.assertEqual(path.read_text(encoding="utf-8"), rendered(model),
                                 "run: python -m shared.export_schemas")

    def test_every_example_validates_exactly(self):
        self.assertEqual(set(EXAMPLES), {path.name for path in (DIRECTORY / "examples").glob("*.json")})
        for name, model in EXAMPLES.items():
            with self.subTest(name=name):
                model.model_validate(example(name))

    def test_legacy_result_without_new_fields_still_validates(self):
        legacy = example("result.observe.json")
        for key in ("search_origin", "search_origin_label", "landmark_card"):
            legacy.pop(key)
        for key in ("observed_place_source", "observed_place_confidence"):
            legacy["scene"].pop(key)
        self.assertIsNone(GuideResult.model_validate(legacy).landmark_card)

    def test_verified_block_requires_evidence(self):
        card = example("landmark-card.ko.json")
        card["blocks"]["fun_fact"]["evidence_ids"] = []
        with self.assertRaises(ValidationError):
            LandmarkCard.model_validate(card)

    def test_card_summary_must_reflect_weakest_block_and_evidence_union(self):
        card = example("landmark-card.model-unverified.en.json")
        weaker = copy.deepcopy(card)
        weaker["verification"] = "public_source"
        with self.assertRaises(ValidationError):
            LandmarkCard.model_validate(weaker)
        missing = copy.deepcopy(card)
        missing["evidence_ids"] = []
        with self.assertRaises(ValidationError):
            LandmarkCard.model_validate(missing)

    def test_route_legs_connect_stops_and_cannot_claim_verified_walk(self):
        route = example("routes.en.json")
        broken = copy.deepcopy(route)
        broken["routes"][0]["legs"].reverse()
        with self.assertRaises(ValidationError):
            RoutesResponse.model_validate(broken)
        verified = copy.deepcopy(route)
        verified["routes"][0]["legs"][0]["route_verified"] = True
        with self.assertRaises(ValidationError):
            RoutesResponse.model_validate(verified)
        total = copy.deepcopy(route)
        total["routes"][0]["total_straight_line_m"] += 1
        with self.assertRaises(ValidationError):
            RoutesResponse.model_validate(total)



class ContentTests(unittest.TestCase):
    def test_route_examples_are_the_deterministic_server_output(self):
        from service import content
        for lang in ("en", "ko"):
            self.assertEqual(example(f"routes.{lang}.json"), content.routes(lang, (37.579, 126.973)))

    def test_card_examples_match_prepared_cards_and_all_ten_cards_relabel(self):
        from shared.cards import catalog_card
        self.assertEqual(example("landmark-card.ko.json"), catalog_card("local:gyeongbokgung", "ko"))
        self.assertEqual(example("result.story.json")["landmark_card"], catalog_card("local:gyeongbokgung", "en"))
        cards = [catalog_card(place, lang) for place in ("local:gyeongbokgung", "local:gwanghwamun",
                 "local:geunjeongjeon", "local:gyeonghoeru", "local:bukchon") for lang in ("en", "ko")]
        self.assertTrue(all(cards))
        for card in cards:
            for block in [*card["blocks"].values(), card["visit_note"]]:
                if block is None:
                    continue
                public = any(item.startswith("wikipedia:") for item in block["evidence_ids"])
                self.assertEqual(block["verification"], "public_source" if public else "catalog")
            self.assertNotIn("quotes", json.dumps(card))

    def test_merged_research_evidence_keeps_quotes_out_of_public_records(self):
        from service.catalog import evidence_for_mode
        data = json.loads((DIRECTORY.parent / "data" / "evidence.json").read_text(encoding="utf-8"))["real_place"]
        merged = [item for item in data if item.get("quote_capture")]
        self.assertEqual(len(merged), 15)  # research v1 (7) + v2 official (7) + v2.1 khs:jongmyo-intro
        public = {item["id"]: item for item in evidence_for_mode("real_place")}
        self.assertTrue(all(set(public[item["id"]]) == {"id", "source", "as_of", "type", "dataset_id"} for item in merged))


if __name__ == "__main__":
    unittest.main()
