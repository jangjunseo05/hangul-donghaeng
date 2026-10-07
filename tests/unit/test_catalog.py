import math
import unittest
from service.catalog import catalog_summary, evidence_for_mode, food_candidates, get_place, search_places, valid_food_ids


class CatalogTests(unittest.TestCase):
    def test_contract_and_three_menus(self):
        self.assertEqual(catalog_summary()["catalog_count"], 1)
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
        self.assertEqual(len(records), 3)
        self.assertTrue(all(set(r) == {"id", "source", "as_of", "type", "dataset_id"} for r in records))
        self.assertTrue(all(r["dataset_id"] == "fictional_task" for r in evidence_for_mode("fictional_task")))
        records[0]["source"] = "tampered"
        self.assertNotEqual(evidence_for_mode("real_place")[0]["source"], "tampered")
        with self.assertRaises(ValueError):
            evidence_for_mode("restricted")


if __name__ == "__main__":
    unittest.main()
