"""Culture flow checks use HTTP stubs; these are not live model/runtime evidence."""
import json
import unittest

from test_agent import Harness, decision, draft, job
from test_agent_context import second_context
from service.catalog import search_places


PALACE = "local:gyeongbokgung"
GATE = "local:gwanghwamun"
PALACE_CULTURE = "visitseoul:gyeongbokgung-culture"
GATE_CULTURE = "visitkorea:gwanghwamun-culture"


def culture_decision(place_id=PALACE):
    selected = decision()
    selected.update(intent="culture", food_ids=[], place_ids=[place_id],
                    search_kinds=["heritage", "restaurant"], observation_summary="A possible heritage gate.")
    return selected


def culture_draft(source_id=PALACE_CULTURE):
    response = draft()
    response.update(speech_text="This heritage place has a documented historical context.",
                    menu_ids=[], claims=[{"text": "The official source describes this heritage place.",
                                         "scope": "culture", "evidence_ids": [source_id]}],
                    unknowns=["Current admission and gate access are unverified."], order_ko=None)
    return response


def searches(harness):
    return [json.loads(request.content) for request in harness.service_requests
            if request.url.path == "/worker/search"]


class AgentCultureTests(unittest.IsolatedAsyncioTestCase):
    async def test_observe_three_grounded_claims_save_without_repair_or_second_photo(self):
        assignment = job()
        assignment["request"].update(interaction_mode="observe", confirmed_place_id=PALACE)
        response = culture_draft()
        response["claims"] *= 3
        harness = Harness([culture_decision(), response], assignment)
        self.assertEqual(await harness.run(), "saved")
        self.assertEqual(len(harness.model_requests), 2)
        first_parts = harness.model_requests[0]["messages"][-1]["content"]
        self.assertTrue(any(part["type"] == "image_url" for part in first_parts))
        draft_messages = harness.model_requests[1]["messages"]
        self.assertFalse(any(part.get("type") == "image_url" for message in draft_messages
                             if isinstance(message["content"], list) for part in message["content"]))
        context, prompt = second_context(harness)
        self.assertEqual(context["observed_place_candidates"][0]["id"], PALACE)
        self.assertIn("prefer ONE short cited claim; up to 3 are allowed", prompt)
        self.assertIn("Preserve every required JSON key", prompt)
        result = harness.submitted[0]["result"]
        self.assertEqual(result["claims"], response["claims"])
        self.assertEqual(result["status"], "need_confirmation")
        self.assertTrue(result["next_question"])

    async def test_observe_two_grounded_claims_do_not_spend_repair(self):
        assignment = job()
        assignment["request"].update(interaction_mode="observe", confirmed_place_id=PALACE)
        response = culture_draft()
        response["claims"] *= 2
        harness = Harness([culture_decision(), response], assignment)
        self.assertEqual(await harness.run(), "saved")
        self.assertEqual(len(harness.model_requests), 2)
        self.assertEqual(harness.submitted[0]["result"]["claims"], response["claims"])

    async def test_candidate_place_requires_confirmation_even_with_confirmed_food(self):
        for confirmed_food in (None, "samgyetang"):
            with self.subTest(confirmed_food=confirmed_food):
                assignment = job()
                assignment["request"]["confirmed_food_id"] = confirmed_food
                harness = Harness([culture_decision(), culture_draft()], assignment)
                self.assertEqual(await harness.run(), "saved")
                result = harness.submitted[0]["result"]
                self.assertEqual(result["status"], "need_confirmation")
                self.assertEqual(result["places"], [])
                self.assertEqual(searches(harness), [])
                self.assertEqual([p["id"] for p in result["scene"]["place_candidates"]], [PALACE])
                self.assertIsNone(result["scene"]["confirmed_place_id"])
                self.assertTrue(result["next_question"])
                context, _ = second_context(harness)
                self.assertTrue(context["ambiguous_identity"])
                self.assertEqual(context["first_decision"]["place_ids"], [PALACE])

    async def test_confirmed_heritage_two_searches_keep_anchor_and_canonical_places(self):
        assignment = job()
        assignment["request"]["confirmed_place_id"] = PALACE
        # A food confirmation must not filter a heritage search into an empty result.
        assignment["request"]["confirmed_food_id"] = "samgyetang"
        harness = Harness([culture_decision(), culture_draft()], assignment)
        self.assertEqual(await harness.run(), "saved")
        requested = searches(harness)
        self.assertEqual(len(requested), 2)
        self.assertEqual([item["kind"] for item in requested], ["heritage", "restaurant"])
        self.assertIsNone(requested[0]["food_id"])
        self.assertEqual(requested[0]["shop_id"], PALACE)
        self.assertIsNone(requested[1]["shop_id"])
        self.assertTrue(all(item["radius_m"] == assignment["request"]["radius_m"] for item in requested))
        result = harness.submitted[0]["result"]
        self.assertEqual(result["status"], "ready")
        self.assertEqual({p["place_id"] for p in result["places"]}, {PALACE, "local:tosokchon"})
        self.assertLessEqual(len(result["places"]), 3)
        self.assertEqual(len({p["place_id"] for p in result["places"]}), len(result["places"]))
        for place in result["places"]:
            expected = search_places(None, place["place_id"], assignment["request"]["location"], 1000)["places"][0]
            self.assertEqual(place, expected)
            self.assertNotIn("name_en", place)
        scene = result["scene"]
        self.assertEqual(scene["confirmed_place_id"], PALACE)
        self.assertIsNone(scene["confirmed_shop_id"])
        context, _ = second_context(harness)
        self.assertFalse(context["ambiguous_identity"])
        self.assertEqual(context["places"], result["places"])

    async def test_legacy_and_new_confirmation_aliases_preserved_exactly(self):
        for aliases in ({"confirmed_shop_id": PALACE}, {"confirmed_place_id": PALACE},
                        {"confirmed_shop_id": PALACE, "confirmed_place_id": PALACE}):
            with self.subTest(aliases=aliases):
                assignment = job()
                assignment["request"].update(aliases)
                harness = Harness([culture_decision(), culture_draft()], assignment)
                self.assertEqual(await harness.run(), "saved")
                scene = harness.submitted[0]["result"]["scene"]
                for key in ("confirmed_shop_id", "confirmed_place_id"):
                    self.assertEqual(scene[key], assignment["request"].get(key))
                self.assertTrue(searches(harness))

    async def test_observe_requests_require_specific_question_even_with_confirmation(self):
        assignment = job()
        assignment["request"].update(interaction_mode="observe", confirmed_place_id=PALACE)
        response = culture_draft()
        response["next_question"] = "Would you like the history of Gyeongbokgung Palace or nearby food?"
        harness = Harness([culture_decision(), response], assignment)
        self.assertEqual(await harness.run(), "saved")
        result = harness.submitted[0]["result"]
        self.assertEqual(result["status"], "need_confirmation")
        self.assertEqual(result["next_question"], response["next_question"])
        self.assertEqual(result["scene"]["confirmed_place_id"], PALACE)

    async def test_unknown_place_id_is_rejected_before_search(self):
        selected = culture_decision("local:invented")
        harness = Harness([selected, selected])
        self.assertEqual(await harness.run(), "invalid_model_output")
        self.assertEqual(searches(harness), [])
        self.assertEqual(harness.submitted, [])

    async def test_fictional_mode_rejects_real_place_candidates_or_search_kinds(self):
        for extension in ({"place_ids": [PALACE]}, {"search_kinds": ["heritage"]}):
            with self.subTest(extension=extension):
                selected = decision("fictional_task")
                selected.update(extension)
                harness = Harness([selected, selected], job("fictional_task"))
                self.assertEqual(await harness.run(), "invalid_model_output")
                self.assertEqual(searches(harness), [])
                self.assertEqual(harness.submitted, [])

    async def test_search_kind_schema_rejects_unknown_or_more_than_two(self):
        for kinds in (["museum"], ["heritage", "restaurant", "heritage"]):
            with self.subTest(kinds=kinds):
                selected = culture_decision()
                selected["search_kinds"] = kinds
                harness = Harness([selected, selected])
                self.assertEqual(await harness.run(), "invalid_model_output")
                self.assertEqual(searches(harness), [])
                self.assertEqual(harness.submitted, [])

    async def test_gate_culture_accepts_gate_source(self):
        assignment = job()
        assignment["request"]["confirmed_place_id"] = GATE
        harness = Harness([culture_decision(GATE), culture_draft(GATE_CULTURE)], assignment)
        self.assertEqual(await harness.run(), "saved")
        self.assertEqual(harness.submitted[0]["result"]["claims"][0]["evidence_ids"], [GATE_CULTURE])

    async def test_gate_claim_cannot_cite_palace_only_source_or_location_source(self):
        for source_id in (PALACE_CULTURE, "visitkorea:gwanghwamun-location"):
            with self.subTest(source_id=source_id):
                assignment = job()
                assignment["request"]["confirmed_place_id"] = GATE
                invalid = culture_draft(source_id)
                invalid["claims"][0]["text"] = "Gwanghwamun Gate is the southern main gate of Gyeongbokgung."
                harness = Harness([culture_decision(GATE), invalid, invalid], assignment)
                self.assertEqual(await harness.run(), "invalid_model_output")
                self.assertEqual(harness.submitted, [])


if __name__ == "__main__":
    unittest.main()
