"""Menu-source enrichment uses approved evidence only; provider replies are stubs."""
import unittest

from agent.core import catalog_data
from test_agent import Harness, decision, job
from test_agent_context import second_context
from test_agent_culture import culture_draft, PALACE, GATE, PALACE_CULTURE, GATE_CULTURE


MENU_SOURCE = "visitkorea:tosokchon-menu"


def scenario():
    assignment = job()
    assignment["request"].update(confirmed_food_id="samgyetang", question="Find nearby heritage places within 1 km.")
    selected = decision()
    selected.update(intent="culture", food_ids=["samgyetang"], place_ids=[], search_kinds=["heritage"],
                    source_ids=[PALACE_CULTURE, GATE_CULTURE])
    response = culture_draft(GATE_CULTURE)
    response["menu_ids"] = ["samgyetang"]
    return assignment, selected, response


class MenuGroundingTests(unittest.IsolatedAsyncioTestCase):
    async def test_confirmed_food_enriches_approved_menu_source_omitted_by_decision(self):
        assignment, selected, response = scenario()
        self.assertNotIn(MENU_SOURCE, selected["source_ids"])
        self.assertIn(MENU_SOURCE, assignment["allowed_source_ids"])
        harness = Harness([selected, response], assignment)
        self.assertEqual(await harness.run(), "saved")
        self.assertEqual(len(harness.model_requests), 2)
        result = harness.submitted[0]["result"]
        self.assertEqual({place["place_id"] for place in result["places"]}, {PALACE, GATE})
        self.assertIn(MENU_SOURCE, {record["id"] for record in result["evidence"]})
        canonical = next(menu for menu in catalog_data()["menus"] if menu["food_id"] == "samgyetang")
        self.assertEqual(len(result["menus"]), 1)
        self.assertEqual(result["menus"][0]["name_ko"], canonical["name_ko"])
        self.assertEqual(result["menus"][0]["description"], canonical["description_en"])
        self.assertEqual(result["menus"][0]["evidence_ids"], [MENU_SOURCE])
        context, _ = second_context(harness)
        self.assertEqual(set(context["allowed_menu_ids"]), {"samgyetang", "roast-chicken", "haemul-pajeon"})
        self.assertEqual(len(context["available_menus"]), 3)
        self.assertTrue(all(menu["evidence_ids"] == [MENU_SOURCE] for menu in context["available_menus"]))
        self.assertIn(MENU_SOURCE, {record["id"] for record in context["evidence"]})

    async def test_menu_source_excluded_from_assignment_cannot_be_enriched(self):
        assignment, selected, response = scenario()
        assignment["allowed_source_ids"].remove(MENU_SOURCE)
        harness = Harness([selected, response, response], assignment)
        self.assertEqual(await harness.run(), "invalid_model_output")
        self.assertEqual(len(harness.model_requests), 3)
        self.assertEqual(harness.submitted, [])
        context, _ = second_context(harness)
        self.assertEqual(context["available_menus"], [])
        self.assertEqual(context["allowed_menu_ids"], [])
        self.assertNotIn(MENU_SOURCE, {record["id"] for record in context["evidence"]})

    async def test_unknown_menu_id_still_rejects_after_one_repair(self):
        assignment, selected, response = scenario()
        response["menu_ids"] = ["invented-royal-menu"]
        harness = Harness([selected, response, response], assignment)
        self.assertEqual(await harness.run(), "invalid_model_output")
        self.assertEqual(len(harness.model_requests), 3)
        self.assertEqual(harness.submitted, [])
        self.assertIn("unknown_menu", harness.model_requests[2]["messages"][-1]["content"])


if __name__ == "__main__":
    unittest.main()
