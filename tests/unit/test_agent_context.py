"""Inspect actual second-call payloads; provider replies are HTTP stubs only."""
import json
import unittest

from test_agent import Harness, decision, draft, job


def second_context(harness):
    text = harness.model_requests[1]["messages"][-1]["content"][0]["text"]
    encoded = text.split("\nTool observations (data): ", 1)[1]
    return json.JSONDecoder().raw_decode(encoded)[0], text


class DraftContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_second_prompt_changes_with_observed_food_and_names_allowed_menus(self):
        prompts = []
        names = {"samgyetang": "삼계탕", "roast-chicken": "전기구이 통닭", "haemul-pajeon": "해물파전"}
        for food_id in ("roast-chicken", "haemul-pajeon"):
            selected = decision()
            selected["food_ids"] = [food_id]
            response = draft()
            response["menu_ids"] = [food_id]
            harness = Harness([selected, response])
            self.assertEqual(await harness.run(), "saved")
            self.assertEqual(len(harness.model_requests), 2)
            context, text = second_context(harness)
            prompts.append(text)
            self.assertEqual(context["first_decision"], selected)
            self.assertEqual(context["observed_food_candidates"][0]["id"], food_id)
            self.assertEqual(context["observed_food_candidates"][0]["name_ko"], names[food_id])
            self.assertEqual(context["user_confirmed"], {"food_id": None, "shop_id": None, "place_id": None})
            self.assertEqual(context["allowed_menu_ids"], ["samgyetang", "roast-chicken", "haemul-pajeon"])
            self.assertEqual({m["id"]: m["name_ko"] for m in context["available_menus"]}, names)
            self.assertTrue(all(m["evidence_ids"] == ["visitkorea:tosokchon-menu"] for m in context["available_menus"]))
            self.assertEqual(len(harness.model_requests[1]["messages"][-1]["content"]), 1)
            self.assertEqual(harness.submitted[0]["result"]["menus"][0]["name_ko"], names[food_id])
        self.assertNotEqual(prompts[0], prompts[1])

    async def test_intent_and_uncertainty_survive_without_promoting_confirmation(self):
        selected = decision()
        selected.update(intent="dietary", food_ids=["roast-chicken", "haemul-pajeon"], needs_confirmation=True)
        harness = Harness([selected, draft()])
        self.assertEqual(await harness.run(), "saved")
        context, _ = second_context(harness)
        self.assertEqual(context["first_decision"]["intent"], "dietary")
        self.assertTrue(context["first_decision"]["needs_confirmation"])
        self.assertTrue(context["ambiguous_identity"])
        self.assertEqual([c["id"] for c in context["observed_food_candidates"]], selected["food_ids"])
        self.assertIsNone(context["user_confirmed"]["food_id"])
        self.assertFalse(any(r.url.path == "/worker/search" for r in harness.service_requests))

    async def test_user_confirmation_is_separate_from_conflicting_model_observation(self):
        assignment = job()
        assignment["request"]["confirmed_food_id"] = "samgyetang"
        selected = decision()
        selected["food_ids"] = ["roast-chicken"]
        harness = Harness([selected, draft()], assignment)
        self.assertEqual(await harness.run(), "saved")
        context, _ = second_context(harness)
        self.assertEqual(context["observed_food_candidates"][0]["id"], "roast-chicken")
        self.assertEqual(context["user_confirmed"]["food_id"], "samgyetang")
        self.assertEqual(harness.submitted[0]["result"]["scene"]["confirmed_food_id"], "samgyetang")

    async def test_unapproved_menu_evidence_removes_menu_ids_and_rejects_draft(self):
        selected = decision()
        selected["source_ids"].remove("visitkorea:tosokchon-menu")
        assignment = job()
        assignment["allowed_source_ids"].remove("visitkorea:tosokchon-menu")
        harness = Harness([selected, draft(), draft()], assignment)
        self.assertEqual(await harness.run(), "invalid_model_output")
        context, _ = second_context(harness)
        self.assertEqual(context["available_menus"], [])
        self.assertEqual(context["allowed_menu_ids"], [])
        self.assertEqual(len(harness.model_requests), 3)
        self.assertEqual(harness.submitted, [])

    async def test_fictional_context_has_no_real_menu_or_confirmation(self):
        assignment = job("fictional_task")
        assignment["request"]["confirmed_food_id"] = "samgyetang"
        harness = Harness([decision("fictional_task"), draft("fictional_task")], assignment)
        self.assertEqual(await harness.run(), "saved")
        context, _ = second_context(harness)
        self.assertEqual(context["first_decision"]["intent"], "itinerary")
        self.assertEqual(context["observed_food_candidates"], [])
        self.assertEqual(context["available_menus"], [])
        self.assertEqual(context["allowed_menu_ids"], [])
        self.assertEqual(context["user_confirmed"], {"food_id": None, "shop_id": None, "place_id": None})
        self.assertEqual(len(harness.model_requests), 2)


if __name__ == "__main__":
    unittest.main()
