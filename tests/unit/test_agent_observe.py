"""Observe uses a validated visual classifier; these tests use HTTP stubs only."""
import unittest

from test_agent import Harness, decision, job
from test_agent_culture import culture_decision, culture_draft, visual_observation, PALACE, GATE, GATE_CULTURE


def observe_job():
    # Without a location there are no GPS candidates: free visual recognition (closed-set tests below).
    assignment = job()
    assignment["request"].update(interaction_mode="observe", location=None)
    return assignment


def observation_decision(place_id=None):
    names = {PALACE: "경복궁", GATE: "광화문"}
    return visual_observation(names.get(place_id, place_id))


class ObserveDecisionTests(unittest.IsolatedAsyncioTestCase):
    def assert_observation_only(self, harness, status="need_confirmation"):
        self.assertEqual(len(harness.model_requests), 1)
        self.assertTrue(any(r.url.path.startswith("/worker/photos/") for r in harness.service_requests))
        parts = harness.model_requests[0]["messages"][-1]["content"]
        self.assertTrue(any(part.get("type") == "image_url" and
                            part["image_url"]["url"].startswith("data:image/jpeg;base64,") for part in parts))
        self.assertFalse(any(r.url.path == "/worker/search" for r in harness.service_requests))
        self.assertEqual(len(harness.submitted), 1)
        self.assertEqual(harness.failures, [])
        result = harness.submitted[0]["result"]
        self.assertEqual(result["status"], status)
        for field in ("claims", "menus", "places", "itinerary", "conflicts"):
            self.assertEqual(result[field], [])
        if status == "need_confirmation":
            self.assertTrue(result["next_question"])
        else:
            # A frame without a cultural landmark does not interrupt the visitor.
            self.assertIsNone(result["next_question"])
            self.assertEqual(result["speech_text"], "")
        return result

    async def test_empty_candidates_use_one_photo_decision_without_historical_claims(self):
        harness = Harness([observation_decision()], observe_job())
        self.assertEqual(await harness.run(), "saved")
        result = self.assert_observation_only(harness, status="ready")
        self.assertEqual(result["scene"]["place_candidates"], [])
        self.assertEqual(result["scene"]["food_candidates"], [])
        self.assertIsNone(result["scene"]["confirmed_place_id"])
        self.assertIsNone(result["scene"]["confirmed_shop_id"])
        self.assertEqual(result["evidence"], [])
        self.assertNotIn("1395", result["speech_text"])
        self.assertNotIn("2010", result["speech_text"])

    async def test_unknown_scene_ignores_history_and_question_without_filling_catalog_candidates(self):
        assignment = observe_job()
        assignment["history"] = [{"role": "user", "content": "EARLIER_HISTORY_MARKER: we visited Gyeongbokgung and ate samgyetang."}]
        assignment["request"]["question"] = "QUESTION_TRIGGER_MARKER: continue the previous restaurant and palace search."
        harness = Harness([observation_decision()], assignment)
        self.assertEqual(await harness.run(), "saved")
        result = self.assert_observation_only(harness, status="ready")
        prompt = harness.model_requests[0]["messages"][-1]["content"][0]["text"]
        self.assertNotIn("EARLIER_HISTORY_MARKER", prompt)
        self.assertNotIn("QUESTION_TRIGGER_MARKER", prompt)
        self.assertEqual(result["scene"]["place_candidates"], [])
        self.assertEqual(result["scene"]["food_candidates"], [])

    async def test_broad_catalog_listing_is_repaired_to_unknown_scene(self):
        broad = observation_decision()
        broad.update(place_ids=[PALACE, GATE, "local:tosokchon"],
                     food_ids=["samgyetang", "roast-chicken", "haemul-pajeon"])
        harness = Harness([broad, observation_decision()], observe_job())
        self.assertEqual(await harness.run(), "saved")
        self.assertEqual(len(harness.model_requests), 2)
        self.assertIn("schema_validation", harness.model_requests[1]["messages"][-1]["content"])
        self.assertEqual(harness.submitted[0]["result"]["scene"]["place_candidates"], [])
        self.assertEqual(harness.submitted[0]["result"]["scene"]["food_candidates"], [])
        self.assertEqual(harness.submitted[0]["result"]["claims"], [])
        self.assertFalse(any(r.url.path == "/worker/search" for r in harness.service_requests))
        messages = harness.model_requests[0]["messages"]
        prompt = messages[0]["content"] + messages[-1]["content"][0]["text"]
        self.assertIn("Do not identify people", prompt)

    async def test_visual_category_mismatch_blank_basis_or_extra_tool_field_require_repair(self):
        invalids = [
            {key: value for key, value in observation_decision(PALACE).items() if key != "identification_supported"},
            {**observation_decision(), "visual_basis": ""},
            {**observation_decision(), "search_places": True},
        ]
        for invalid in invalids:
            with self.subTest(invalid=invalid):
                harness = Harness([invalid, observation_decision()], observe_job())
                self.assertEqual(await harness.run(), "saved")
                self.assertEqual(len(harness.model_requests), 2)
                self.assertIn("schema_validation", harness.model_requests[1]["messages"][-1]["content"])
                result = harness.submitted[0]["result"]
                self.assertEqual(result["scene"]["place_candidates"], [])
                self.assertEqual(result["scene"]["food_candidates"], [])
                self.assertEqual(result["claims"], [])
                self.assertFalse(any(r.url.path == "/worker/search" for r in harness.service_requests))

    async def test_manual_unknown_culture_identity_uses_one_decision_even_without_model_uncertainty(self):
        for needs_confirmation in (True, False):
            with self.subTest(needs_confirmation=needs_confirmation):
                assignment = job()
                assignment["request"].update(interaction_mode="ask", question="What is this place?")
                selected = decision()
                selected.update(intent="culture", food_ids=[], place_ids=[], search_places=False,
                                search_kinds=[], needs_confirmation=needs_confirmation)
                harness = Harness([selected], assignment)
                self.assertEqual(await harness.run(), "saved")
                result = self.assert_observation_only(harness)
                self.assertEqual(result["scene"]["place_candidates"], [])
                self.assertEqual(result["evidence"], [])
                self.assertIsNone(result["scene"]["confirmed_place_id"])

    async def test_explicitly_confirmed_manual_gate_reaches_grounded_draft(self):
        assignment = job()
        assignment["request"].update(interaction_mode="ask", confirmed_place_id=GATE,
                                     question="Tell me the history of this gate.")
        selected = culture_decision(GATE)
        selected.update(search_places=False, search_kinds=[])
        response = culture_draft(GATE_CULTURE)
        harness = Harness([selected, response], assignment)
        self.assertEqual(await harness.run(), "saved")
        self.assertEqual(len(harness.model_requests), 2)
        result = harness.submitted[0]["result"]
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["claims"], response["claims"])
        self.assertEqual(result["scene"]["confirmed_place_id"], GATE)
        self.assertIn(GATE_CULTURE, {record["id"] for record in result["evidence"]})

    async def test_free_recognition_name_stays_model_observation_without_catalog_candidate(self):
        # M5 decision 1(c): a free name ("경복궁") is not mapped to local:gyeongbokgung.
        harness = Harness([observation_decision(PALACE)], observe_job())
        self.assertEqual(await harness.run(), "saved")
        result = self.assert_observation_only(harness)
        self.assertEqual(result["scene"]["place_candidates"], [])
        self.assertEqual((result["scene"]["observed_place_name"], result["scene"]["observed_place_source"]), ("경복궁", "model"))
        self.assertIn("경복궁", result["next_question"])
        self.assertIsNone(result["scene"]["confirmed_place_id"])
        self.assertIsNone(result["scene"]["confirmed_shop_id"])

    async def test_incoming_confirmation_aliases_are_echoed_exactly(self):
        for aliases in ({"confirmed_place_id": PALACE}, {"confirmed_shop_id": PALACE},
                        {"confirmed_place_id": PALACE, "confirmed_shop_id": PALACE}):
            with self.subTest(aliases=aliases):
                assignment = observe_job()
                assignment["request"].update(aliases)
                harness = Harness([observation_decision(PALACE)], assignment)
                self.assertEqual(await harness.run(), "saved")
                result = self.assert_observation_only(harness)
                for key in ("confirmed_place_id", "confirmed_shop_id"):
                    self.assertEqual(result["scene"][key], assignment["request"].get(key))

    async def test_provider_http_error_has_no_fallback_observation(self):
        harness = Harness([], observe_job(), model_status=401)
        self.assertEqual(await harness.run(), "model_http_error")
        self.assertEqual(len(harness.model_requests), 1)
        self.assertEqual(harness.submitted, [])
        self.assertEqual(harness.failures[0]["error_code"], "model_http_error")
        self.assertFalse(any(r.url.path == "/worker/search" for r in harness.service_requests))

    async def test_invalid_decision_has_no_fallback_observation(self):
        selected = {**observation_decision(PALACE), "scene_kind": "palace"}
        harness = Harness([selected, selected], observe_job())
        self.assertEqual(await harness.run(), "invalid_model_output")
        self.assertEqual(len(harness.model_requests), 2)
        self.assertEqual(harness.submitted, [])
        self.assertEqual(harness.failures[0]["error_code"], "invalid_model_output")
        self.assertFalse(any(r.url.path == "/worker/search" for r in harness.service_requests))


if __name__ == "__main__":
    unittest.main()
