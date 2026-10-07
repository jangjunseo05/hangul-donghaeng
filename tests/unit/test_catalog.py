import math
import hashlib
import json
import unittest
from unittest.mock import patch

from service.catalog import DATA_DIR, catalog_summary, evidence_for_mode, food_candidates, get_place, public_catalog, search_places, valid_food_ids


class CatalogTests(unittest.TestCase):
    def test_contract_and_three_menus(self):
        self.assertGreaterEqual(catalog_summary()["catalog_count"], 1)
        self.assertEqual(len(food_candidates()), 3)
        self.assertEqual(valid_food_ids(), {"samgyetang", "roast-chicken", "haemul-pajeon"})
        self.assertIsNone(get_place("unknown"))

    def test_near_far_and_no_location(self):
        near = {"lat": 37.5790, "lng": 126.9730, "origin": "selected"}
        places = search_places("samgyetang", None, near, 500)["places"]
        self.assertEqual(len(places), 1)
        self.assertTrue(150 < places[0]["distance_m"] < 300)
        far = {"lat": 35.1, "lng": 129.0, "origin": "gps"}
        self.assertEqual(search_places(None, None, far, 3000)["places"], [])
        self.assertTrue(search_places(None, None, None, 1000)["needs_location"])

    def test_invalid_inputs_do_not_bypass_with_missing_location(self):
        for args in [("unknown", None, None, 500), (None, "unknown", None, 500), (None, None, None, 501)]:
            with self.assertRaises(ValueError):
                search_places(*args)
        for lat in [math.nan, math.inf, 91, True]:
            with self.assertRaises(ValueError):
                search_places(None, None, {"lat": lat, "lng": 126, "origin": "gps"}, 500)

    def test_evidence_modes_and_copies(self):
        records = evidence_for_mode("real_place")
        self.assertGreaterEqual(len(records), 3)
        self.assertTrue(all(set(r) == {"id", "source", "as_of", "type", "dataset_id"} for r in records))
        self.assertTrue(all(r["dataset_id"] == "fictional_task" for r in evidence_for_mode("fictional_task")))
        records[0]["source"] = "tampered"
        self.assertNotEqual(evidence_for_mode("real_place")[0]["source"], "tampered")
        with self.assertRaises(ValueError):
            evidence_for_mode("restricted")

    def test_approved_heritage_integration_and_evidence_links(self):
        catalog = json.loads((DATA_DIR / "catalog.json").read_text(encoding="utf-8"))
        evidence = json.loads((DATA_DIR / "evidence.json").read_text(encoding="utf-8"))
        records = {r["id"]: r for r in evidence["real_place"]}
        proposal = DATA_DIR / "heritage-proposal.json"
        self.assertEqual(hashlib.sha256(proposal.read_bytes()).hexdigest(),
                         catalog["heritage_integration"]["input_sha256"])
        for place_id in ["local:gyeongbokgung", "local:gwanghwamun"]:
            place = next(p for p in catalog["places"] if p["place_id"] == place_id)
            self.assertEqual(get_place(place_id)["kind"], "heritage")
            self.assertTrue(place["name_en"])
            self.assertEqual(place["food_ids"], [])
            self.assertIsNone(place["currently_open"])
            self.assertIsNone(place["admission_fee"])
            for source_id in [place["source_id"], *place["culture_evidence_ids"], *place["operation_evidence_ids"]]:
                self.assertIn(place_id, records[source_id]["place_ids"])
                self.assertEqual(records[source_id]["dataset_id"], "real_place")
            for source_id in place["culture_evidence_ids"]:
                self.assertEqual(records[source_id]["claim_scopes"], ["culture"])
        palace = next(p for p in catalog["places"] if p["place_id"] == "local:gyeongbokgung")
        self.assertEqual(palace["coordinate_provenance"]["status"], "official_map_point_with_conflicting_jsonld")
        self.assertNotEqual(palace["lat"], palace["coordinate_provenance"]["alternative_jsonld"]["lat"])
        self.assertTrue(all(r["dataset_id"] == "fictional_task" for r in evidence["fictional_task"]))


class CultureCatalogTests(unittest.TestCase):
    def setUp(self):
        self.location = {"lat": 37.579, "lng": 126.973, "origin": "selected"}
        self.data = {
            "catalog_version": "test.2", "scope_label": "Curated test anchors",
            "foods": [{"id": "soup", "name_ko": "국", "name_en": "Soup"}],
            "places": [
                {"place_id": "restaurant", "name": "식당", "lat": 37.580,
                 "lng": 126.973, "source_id": "source:restaurant", "food_ids": ["soup"]},
                {"place_id": "heritage-a", "name": "문화 장소", "name_en": "Heritage A",
                 "kind": "heritage", "lat": 37.581, "lng": 126.973,
                 "source_id": "source:heritage-a"},
                {"place_id": "heritage-b", "name": "문화 장소 B", "name_en": "Heritage B",
                 "kind": "heritage", "lat": 37.582, "lng": 126.973,
                 "source_id": "source:heritage-b"},
                {"place_id": "restaurant-far", "name": "먼 식당", "kind": "restaurant",
                 "lat": 37.583, "lng": 126.973, "source_id": "source:restaurant-far",
                 "food_ids": ["soup"]},
            ],
        }
        loader = patch("service.catalog._load", return_value=self.data)
        loader.start()
        self.addCleanup(loader.stop)

    def test_public_metadata_and_canonical_place_fields(self):
        public = public_catalog()
        self.assertEqual(public["catalog_count"], len(public["places"]))
        self.assertEqual(public["scope_label"], self.data["scope_label"])
        self.assertEqual(public["catalog_version"], "test.2")
        expected = {"place_id", "name", "kind", "lat", "lng", "source_id", "catalog_version"}
        for place in public["places"]:
            self.assertEqual(set(place), expected | {"name_en"})
            self.assertEqual(set(get_place(place["place_id"])), expected)
            self.assertEqual(place["catalog_version"], public["catalog_version"])
        self.assertEqual(public["places"][0]["kind"], "restaurant")
        self.assertEqual(public["places"][0]["name_en"], "식당")
        self.assertEqual(public["places"][1]["name_en"], "Heritage A")
        self.assertIsNone(get_place("missing"))
        public["places"][1]["name"] = "tampered"
        self.assertEqual(get_place("heritage-a")["name"], "문화 장소")

    def test_kind_filters_legacy_food_query_and_total_limit(self):
        legacy = search_places("soup", None, self.location, 500)
        self.assertEqual([p["place_id"] for p in legacy["places"]], ["restaurant", "restaurant-far"])
        heritage = search_places(None, None, self.location, 500, kind="heritage")
        self.assertEqual([p["place_id"] for p in heritage["places"]], ["heritage-a", "heritage-b"])
        restaurants = search_places(None, None, self.location, 500, kind="restaurant")
        self.assertEqual([p["place_id"] for p in restaurants["places"]], ["restaurant", "restaurant-far"])
        self.assertEqual(search_places("soup", None, self.location, 500, kind="heritage")["places"], [])
        self.assertEqual(search_places(None, "heritage-a", self.location, 500, kind="restaurant")["places"], [])
        combined = search_places(None, None, self.location, 500)
        self.assertEqual([p["place_id"] for p in combined["places"]], ["restaurant", "heritage-a", "heritage-b"])
        self.assertEqual(combined["catalog_count"], 4)

    def test_targeted_and_separate_searches_keep_request_anchor(self):
        heritage = search_places(None, "heritage-a", self.location, 500, kind="heritage")["places"][0]
        combined = search_places(None, None, self.location, 500)["places"]
        self.assertEqual(heritage, next(p for p in combined if p["place_id"] == "heritage-a"))
        self.assertAlmostEqual(heritage["distance_m"], 222.4, delta=0.1)
        restaurant = search_places("soup", "restaurant", self.location, 500, kind="restaurant")["places"][0]
        self.assertAlmostEqual(restaurant["distance_m"], 111.2, delta=0.1)
        distant = {"lat": 37.600, "lng": 126.973, "origin": "gps"}
        self.assertEqual(search_places(None, "heritage-a", distant, 500)["places"], [])

    def test_no_location_inference_and_invalid_ids(self):
        missing = search_places(None, "heritage-a", None, 500, kind="heritage")
        self.assertEqual(missing["places"], [])
        self.assertTrue(missing["needs_location"])
        for food_id, shop_id, kind in [(None, None, "museum"), ("missing", None, None),
                                       (None, "missing", None)]:
            with self.subTest(food_id=food_id, shop_id=shop_id, kind=kind):
                with self.assertRaises(ValueError):
                    search_places(food_id, shop_id, None, 500, kind=kind)


if __name__ == "__main__":
    unittest.main()
