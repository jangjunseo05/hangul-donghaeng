"""Fictional-mode isolation regressions use HTTP stubs, not live GPU evidence."""
from contextlib import redirect_stderr
import io
import json
import unittest

from test_agent import Harness, decision, draft, job


class FictionalModeTests(unittest.IsolatedAsyncioTestCase):
    def assert_no_real_tools(self, harness):
        self.assertFalse(any(request.url.path == "/worker/search" or "/worker/photos/" in request.url.path
                             for request in harness.service_requests))

    async def test_forbidden_search_repaired_to_fictional_decision_and_draft(self):
        invalid = decision("fictional_task")
        invalid.update(search_places=True, search_kinds=["heritage"])
        harness = Harness([invalid, decision("fictional_task"), draft("fictional_task")], job("fictional_task"))
        logs = io.StringIO()
        with redirect_stderr(logs):
            self.assertEqual(await harness.run(), "saved")
        self.assertEqual(len(harness.model_requests), 3)
        self.assert_no_real_tools(harness)
        self.assertEqual(len(harness.submitted), 1)
        result = harness.submitted[0]["result"]
        self.assertEqual(result["dataset_mode"], "fictional_task")
        self.assertEqual(result["places"], [])
        self.assertEqual(result["menus"], [])
        self.assertTrue(result["itinerary"])
        self.assertTrue(all(record["dataset_id"] == "fictional_task" for record in result["evidence"]))
        events = [json.loads(line) for line in logs.getvalue().splitlines() if line.startswith("{")]
        calls = [event for event in events if event.get("event") == "model_call"]
        self.assertEqual([(event["stage"], event["schema"]) for event in calls],
                         [("decision", "FictionalDecision"), ("decision", "FictionalDecision"),
                          ("draft", "FictionalDraft")])
        self.assertEqual([event["call"] for event in calls], [1, 2, 3])
        self.assertEqual(calls[0]["validation"]["code"], "schema_validation")
        self.assertEqual(harness.failures, [])

    async def test_repeated_forbidden_search_rejects_without_output(self):
        for extension in ({"search_places": True}, {"search_kinds": ["heritage"]}):
            with self.subTest(extension=extension):
                invalid = decision("fictional_task")
                invalid.update(extension)
                harness = Harness([invalid, invalid], job("fictional_task"))
                self.assertEqual(await harness.run(), "invalid_model_output")
                self.assertEqual(len(harness.model_requests), 2)
                self.assert_no_real_tools(harness)
                self.assertEqual(harness.submitted, [])
                self.assertEqual(harness.failures[0]["error_code"], "invalid_model_output")

    async def test_first_prompt_schema_and_instructions_exclude_real_search(self):
        harness = Harness([decision("fictional_task"), draft("fictional_task")], job("fictional_task"))
        self.assertEqual(await harness.run(), "saved")
        prompt = harness.model_requests[0]["messages"][-1]["content"][0]["text"]
        schema, _ = json.JSONDecoder().raw_decode(prompt.split("Output ", 1)[1])
        self.assertEqual(schema["title"], "FictionalDecision")
        properties = schema["properties"]
        self.assertIs(properties["search_places"]["const"], False)
        self.assertEqual(properties["intent"]["const"], "itinerary")
        for field in ("food_ids", "place_ids", "search_kinds"):
            self.assertEqual(properties[field]["maxItems"], 0)
        self.assertEqual(properties["observation_summary"]["const"], "")
        self.assertIn("search_places=false", prompt)
        for forbidden in ("search_places=true", '"search_places": true', "Food candidates:",
                          "Catalog place candidates:", "local:tosokchon", "local:gyeongbokgung",
                          "local:gwanghwamun", "visitseoul:", "visitkorea:", "koreanet:",
                          "samgyetang", "roast-chicken", "haemul-pajeon"):
            self.assertNotIn(forbidden, prompt)
        self.assertIn("task:visitor", prompt)
        self.assertEqual(len(harness.model_requests), 2)
        self.assert_no_real_tools(harness)


if __name__ == "__main__":
    unittest.main()
