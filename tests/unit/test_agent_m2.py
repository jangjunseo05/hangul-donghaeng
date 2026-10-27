"""Phase 2 agent paths with HTTP-stub models: closed-set observation, catalog cards,
and a public-source card for a confirmed OSM place through the real broker."""
import tempfile
from pathlib import Path
import unittest

import httpx

from agent.core import ModelSession
from agent.worker import WorkerAPI, handle_job
from service import nearby, wiki
from service.main import create_app
from shared.cards import catalog_card
from test_agent import Harness, job
from test_agent_culture import culture_decision, culture_draft, PALACE, GATE, GATE_CULTURE

CANDIDATES = [
    {"id": GATE, "name_ko": "광화문", "name_en": "Gwanghwamun Gate", "kind": "heritage", "distance_m": 300.0, "source": "catalog"},
    {"id": "osm:way:77", "name_ko": "예시 전각", "name_en": "Example Hall", "kind": "landmark", "distance_m": 70.0, "source": "osm"},
    {"id": PALACE, "name_ko": "경복궁", "name_en": "Gyeongbokgung Palace", "kind": "heritage", "distance_m": 400.0, "source": "catalog"},
]


def choice(place_id="unknown", scene_kind="landmark", confidence="medium", landmark_name=None):
    return {"visual_basis": "Stone gate with three arches.", "visual_cues": ["three arches", "tiled roof"],
            "scene_kind": scene_kind, "place_id": place_id, "confidence": confidence, "landmark_name": landmark_name}


def observe_job():
    assignment = job()
    assignment["request"]["interaction_mode"] = "observe"
    return assignment


class ClosedSetObservationTests(unittest.IsolatedAsyncioTestCase):
    async def test_candidate_choice_reports_source_confidence_and_alternative_chips(self):
        harness = Harness([choice(GATE, confidence="high")], observe_job(), candidates=CANDIDATES)
        self.assertEqual(await harness.run(), "saved")
        scene = harness.submitted[0]["result"]["scene"]
        self.assertEqual([item["id"] for item in scene["place_candidates"]], [GATE, "osm:way:77", PALACE])
        self.assertEqual((scene["observed_place_source"], scene["observed_place_confidence"]), ("catalog", "high"))
        self.assertEqual(scene["observed_place_name"], "Gwanghwamun Gate")
        self.assertEqual(harness.submitted[0]["result"]["status"], "need_confirmation")
        prompt = harness.model_requests[0]["messages"][-1]["content"][0]["text"]
        self.assertIn("osm:way:77", prompt)
        self.assertNotIn("37.579", prompt)
        self.assertEqual(harness.stages, ["observing", "matching"])

    async def test_osm_candidate_choice_is_labelled_osm(self):
        harness = Harness([choice("osm:way:77", confidence="low")], observe_job(), candidates=CANDIDATES)
        self.assertEqual(await harness.run(), "saved")
        scene = harness.submitted[0]["result"]["scene"]
        self.assertEqual((scene["observed_place_source"], scene["place_candidates"][0]["id"]), ("osm", "osm:way:77"))

    async def test_invented_candidate_is_repaired_once(self):
        harness = Harness([choice("local:invented"), choice(PALACE)], observe_job(), candidates=CANDIDATES)
        self.assertEqual(await harness.run(), "saved")
        self.assertIn("unknown_candidate", harness.model_requests[1]["messages"][-1]["content"])

    async def test_unknown_with_recognized_name_is_model_source_and_silent_otherwise(self):
        harness = Harness([choice(landmark_name="N Seoul Tower")], observe_job(), candidates=CANDIDATES)
        self.assertEqual(await harness.run(), "saved")
        scene = harness.submitted[0]["result"]["scene"]
        self.assertEqual((scene["observed_place_source"], scene["observed_place_name"]), ("model", "N Seoul Tower"))
        silent = Harness([choice(scene_kind="other")], observe_job(), candidates=CANDIDATES)
        self.assertEqual(await silent.run(), "saved")
        result = silent.submitted[0]["result"]
        self.assertEqual((result["status"], result["speech_text"], result["next_question"]), ("ready", "", None))
        self.assertEqual(result["scene"]["place_candidates"], [])

    async def test_no_candidates_falls_back_to_free_recognition(self):
        free = {"visual_basis": "A tower.", "visible_text": None, "scene_kind": "landmark",
                "is_cultural_landmark": True, "landmark_name": "N Seoul Tower", "identification_supported": True}
        harness = Harness([free], observe_job(), candidates=[])
        self.assertEqual(await harness.run(), "saved")
        self.assertEqual(harness.submitted[0]["result"]["scene"]["observed_place_source"], "model")


class CardTests(unittest.IsolatedAsyncioTestCase):
    async def test_confirmed_catalog_place_carries_prepared_card(self):
        assignment = job()
        assignment["request"].update(confirmed_place_id=GATE, question="Tell me the history of this gate.")
        selected = culture_decision(GATE)
        selected.update(search_places=False, search_kinds=[])
        harness = Harness([selected, culture_draft(GATE_CULTURE)], assignment)
        self.assertEqual(await harness.run(), "saved")
        result = harness.submitted[0]["result"]
        self.assertEqual(result["landmark_card"], catalog_card(GATE, "en"))
        self.assertEqual(harness.stages, ["observing", "writing"])

    async def test_unconfirmed_or_restaurant_targets_have_no_card(self):
        harness = Harness([culture_decision(), culture_draft()], job())
        self.assertEqual(await harness.run(), "saved")
        self.assertIsNone(harness.submitted[0]["result"]["landmark_card"])


WIKI_RECORD = {"type": "standard", "pageid": 4242, "title": "Example Hall",
               "extract": "Example Hall is a wooden hall built for royal ceremonies.",
               "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Example_Hall"}}}


def card_reply(cite=True):
    ids = ["wikipedia:en:4242"] if cite else []
    return {"blocks": {
        "what_it_is": {"text": "Example Hall is a wooden hall that was built for royal ceremonies.", "evidence_ids": ids,
                       "verification": "catalog"},
        "why_it_matters": {"text": "Think of it as the stage where the court held its biggest moments together.",
                           "evidence_ids": [], "analogy": True},
        "what_to_look_for": {"text": "Look up at the painted wooden beams under the roof and count the colours you can see.",
                             "evidence_ids": ["wikipedia:en:999"]},
        "fun_fact": None}, "visit_note": None}


class ExternalPlaceRoundTripTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.patches = []
        self.original_search, self.original_wiki = nearby.search_nearby, wiki._TRANSPORT
        nearby.search_nearby = lambda **kwargs: {"places": [{
            "place_id": "osm:way:77", "name": "예시 전각", "name_en": "Example Hall", "kind": "landmark",
            "category": "historic=building", "lat": 37.5795, "lng": 126.9735, "distance_m": 70.0,
            "source_id": "osm:way:77", "osm_url": "https://www.openstreetmap.org/way/77",
            "wikidata": None, "wikipedia": "en:Example Hall"}], "evidence": [], "error_code": None}
        wiki._TRANSPORT = httpx.MockTransport(lambda request: httpx.Response(200, json=WIKI_RECORD))
        wiki._CACHE.clear()

    async def asyncTearDown(self):
        nearby.search_nearby, wiki._TRANSPORT = self.original_search, self.original_wiki
        wiki._CACHE.clear()

    async def run_once(self, replies):
        with tempfile.TemporaryDirectory(prefix="guide-m2-test-") as directory:
            app = create_app(Path(directory), worker_token="integration-test-token")
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test/") as browser, \
                    httpx.AsyncClient(transport=transport, base_url="http://test/",
                        headers={"Authorization": "Bearer integration-test-token"}) as service:
                sid = (await browser.post("/api/sessions", json={})).json()["session_id"]
                await browser.get("/api/nearby", params={"tab": "landmark", "lat": 37.579, "lng": 126.973})
                body = job()["request"]
                body.update(session_id=sid, photo_id=None, confirmed_place_id="osm:way:77",
                            question="Tell me about this hall.")
                created = await browser.post("/api/requests", json=body)
                self.assertEqual(created.status_code, 202, created.text)
                stub = Harness(replies)
                api = WorkerAPI(service)
                assignment = await api.claim()
                async with httpx.AsyncClient(base_url="https://model/v1/", transport=httpx.MockTransport(stub.model)) as model:
                    outcome = await handle_job(assignment, api, ModelSession(model, "stub-test-model"))
                return outcome, (await browser.get(created.json()["poll_url"])).json(), stub

    async def test_public_source_card_is_relabelled_and_accepted_by_broker(self):
        outcome, polled, stub = await self.run_once([card_reply()])
        self.assertEqual(outcome, "saved", polled)
        card = polled["result"]["landmark_card"]
        self.assertEqual(card["place_id"], "osm:way:77")
        self.assertEqual(card["blocks"]["what_it_is"]["verification"], "public_source")  # model said catalog
        self.assertEqual(card["blocks"]["why_it_matters"]["verification"], "model_unverified")
        self.assertEqual(card["blocks"]["what_to_look_for"]["evidence_ids"], [])  # invented id dropped
        self.assertEqual(card["verification"], "model_unverified")
        self.assertEqual(card["sources"][0]["url"], "https://en.wikipedia.org/wiki/Example_Hall")
        self.assertEqual([item["id"] for item in polled["result"]["evidence"]], ["wikipedia:en:4242"])
        self.assertTrue(any("unverified" in item for item in polled["result"]["unknowns"]))
        prompt = stub.model_requests[0]["messages"][-1]["content"][0]["text"]
        self.assertIn("royal ceremonies", prompt)
        self.assertIn("allow_unverified", prompt)

    async def test_operation_facts_in_story_are_repaired(self):
        bad = card_reply()
        bad["blocks"]["what_to_look_for"]["text"] = "Admission tickets are sold at the gate, so check the opening hours first."
        outcome, polled, stub = await self.run_once([bad, card_reply()])
        self.assertEqual(outcome, "saved")
        self.assertIn("operation_in_story", stub.model_requests[1]["messages"][-1]["content"])


if __name__ == "__main__":
    unittest.main()
