"""All provider replies here are HTTP stubs, not live NVIDIA execution evidence."""
import json
import os
import unittest
from unittest.mock import patch

import httpx

from agent.core import AgentError, ModelSession, read_evidence
from agent.worker import Config, WorkerAPI, handle_job
from service.catalog import evidence_for_mode, search_places


def job(mode="real_place"):
    return {"session_id": "s1", "request_id": "r1",
        "request": {"schema_version": 1, "session_id": "s1", "question": "What is this? Nearby, within 1 km.",
            "photo_id": "p1" if mode == "real_place" else None, "dataset_mode": mode, "response_language": "en",
            "location": {"lat": 37.5790, "lng": 126.9730, "origin": "selected"} if mode == "real_place" else None,
            "radius_m": 1000, "confirmed_food_id": None, "confirmed_shop_id": None},
        "history": [{"role": "user", "content": "Keep my vegan preference."}],
        "allowed_source_ids": [record["id"] for record in evidence_for_mode(mode)]}


def decision(mode="real_place"):
    return {"intent": "guide" if mode == "real_place" else "itinerary",
            "food_ids": ["samgyetang"] if mode == "real_place" else [],
            "place_ids": [], "search_kinds": [], "observation_summary": "",
            "needs_confirmation": False, "search_places": mode == "real_place",
            "source_ids": job(mode)["allowed_source_ids"]}


def draft(mode="real_place"):
    return {"speech_text": "Please check the listed options with staff.", "menu_ids": ["samgyetang"] if mode == "real_place" else [],
        "claims": [{"text": "Samgyetang is associated with summer Sambok food culture.", "scope": "culture",
                    "evidence_ids": ["koreanet:samgyetang-culture"]}] if mode == "real_place" else [],
        "conflicts": [] if mode == "real_place" else [{"evidence_ids": ["task:market-notice", "task:market-blog"],
            "decision": "Use the date-specific 10:00–14:00 opening.", "reason": "Same market and visit date; association notice applies."}],
        "itinerary": [] if mode == "real_place" else [
            {"time": "10:00", "activity": "Fictional market visit; confirm ingredient alternatives.", "buffer_minutes": 10,
             "evidence_ids": ["task:visitor", "task:market-notice", "task:food-glossary"]}],
        "unknowns": ["Complete ingredients are unknown."], "next_question": None, "order_ko": "육수나 젓갈이 들어가나요?"}


class Harness:
    def __init__(self, replies, assignment=None, stale=False, model_status=200):
        self.assignment = assignment or job()
        self.replies = list(replies)
        self.stale = stale
        self.model_status = model_status
        self.model_requests = []
        self.service_requests = []
        self.submitted = []
        self.failures = []

    def service(self, request):
        self.service_requests.append(request)
        path = request.url.path
        if path == "/worker/jobs/next":
            return httpx.Response(200, json=self.assignment)
        if path.startswith("/worker/photos/"):
            assert request.url.params["request_id"] == "r1"
            return httpx.Response(200, content=b"unit-test-normalized-jpeg", headers={"content-type": "image/jpeg"})
        if path == "/worker/search":
            if self.stale:
                return httpx.Response(409, json={"error_code": "superseded"})
            data = json.loads(request.content)
            found = search_places(data["food_id"], data["shop_id"], self.assignment["request"]["location"], data["radius_m"], kind=data.get("kind"))
            return httpx.Response(200, json=found)
        if path == "/worker/results":
            if self.stale:
                return httpx.Response(409, json={"error_code": "superseded"})
            self.submitted.append(json.loads(request.content))
            return httpx.Response(200, json={"saved": True, "result_id": "r1"})
        if path == "/worker/fail":
            self.failures.append(json.loads(request.content))
            return httpx.Response(200, json={"accepted": True})
        raise AssertionError("unexpected service route: " + path)

    def model(self, request):
        assert request.url.path == "/v1/chat/completions"
        self.model_requests.append(json.loads(request.content))
        if self.model_status != 200:
            return httpx.Response(self.model_status, text="upstream sensitive text must never be relayed")
        answer = self.replies.pop(0)
        return httpx.Response(200, json={"choices": [{"message": {"content": answer if isinstance(answer, str) else json.dumps(answer)}}]})

    async def run(self):
        async with httpx.AsyncClient(base_url="http://server/", transport=httpx.MockTransport(self.service)) as service, \
                httpx.AsyncClient(base_url="https://model/v1/", transport=httpx.MockTransport(self.model)) as model:
            api = WorkerAPI(service)
            assignment = await api.claim()
            session = ModelSession(model, "stub-test-model")
            outcome = await handle_job(assignment, api, session)
            return outcome


class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_photo_history_search_grounded_result(self):
        h = Harness([decision(), draft()])
        self.assertEqual(await h.run(), "saved")
        self.assertEqual(len(h.model_requests), 2)
        text = h.model_requests[0]["messages"][-1]["content"][0]["text"]
        self.assertIn("Keep my vegan preference.", text)
        self.assertNotIn("37.579", text)
        self.assertTrue(h.model_requests[0]["messages"][-1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        result = h.submitted[0]["result"]
        self.assertEqual(result["places"][0]["place_id"], "local:tosokchon")
        self.assertEqual(result["places"][0]["lat"], 37.57760304027)
        self.assertEqual(result["evidence"], evidence_for_mode("real_place"))
        self.assertIsNone(result["scene"]["confirmed_food_id"])
        self.assertIn("unverified", result["speech_text"])

    async def test_ambiguous_photo_does_not_search_or_confirm(self):
        d = decision()
        d["needs_confirmation"] = True
        h = Harness([d, draft()])
        self.assertEqual(await h.run(), "saved")
        result = h.submitted[0]["result"]
        self.assertEqual(result["status"], "need_confirmation")
        self.assertEqual(result["places"], [])
        self.assertFalse(any(r.url.path == "/worker/search" for r in h.service_requests))

    async def test_model_http_error_no_fake_reply_and_sanitized_failure(self):
        h = Harness([], model_status=401)
        self.assertEqual(await h.run(), "model_http_error")
        self.assertEqual(h.submitted, [])
        self.assertEqual(h.failures[0]["detail"], "model_http_error")
        self.assertNotIn("sensitive", json.dumps(h.failures))

    async def test_stale_search_stops_without_result_or_failure(self):
        h = Harness([decision()], stale=True)
        self.assertEqual(await h.run(), "superseded")
        self.assertEqual(h.submitted, [])
        self.assertEqual(h.failures, [])

    async def test_one_repair_and_three_call_limit(self):
        h = Harness(["not-json", decision(), draft()])
        self.assertEqual(await h.run(), "saved")
        self.assertEqual(len(h.model_requests), 3)
        self.assertTrue(all(payload["messages"][0]["content"].startswith("/no_think\n")
                            for payload in h.model_requests))
        bad = draft()
        bad["claims"][0]["evidence_ids"] = ["invented:source"]
        h = Harness(["not-json", decision(), bad])
        self.assertEqual(await h.run(), "invalid_model_output")
        self.assertEqual(len(h.model_requests), 3)
        self.assertEqual(h.submitted, [])

    async def test_fictional_same_core_no_photo_no_map_and_draft(self):
        h = Harness([decision("fictional_task"), draft("fictional_task")], job("fictional_task"))
        self.assertEqual(await h.run(), "saved")
        result = h.submitted[0]["result"]
        self.assertTrue(result["itinerary"])
        self.assertTrue(result["conflicts"])
        self.assertEqual(result["places"], [])
        self.assertTrue(all(e["dataset_id"] == "fictional_task" for e in result["evidence"]))
        self.assertFalse(any("/photos/" in r.url.path or r.url.path == "/worker/search" for r in h.service_requests))
        self.assertIn("fictional", result["speech_text"])

    async def test_need_location_and_dietary_uncertainty(self):
        assignment = job()
        assignment["request"]["location"] = None
        d = decision()
        d["intent"] = "dietary"
        h = Harness([d, draft()], assignment)
        self.assertEqual(await h.run(), "saved")
        self.assertIn("location", h.submitted[0]["result"]["next_question"].lower())
        h = Harness([d, draft()])
        self.assertEqual(await h.run(), "saved")
        self.assertIn("cross-contact", h.submitted[0]["result"]["next_question"])

    async def test_cross_mode_evidence_refused(self):
        d = decision()
        d["source_ids"] = ["task:visitor"]
        h = Harness([d, d])
        self.assertEqual(await h.run(), "invalid_model_output")
        self.assertFalse(h.submitted)

    async def test_job_identity_mismatch_never_calls_model(self):
        assignment = job()
        assignment["session_id"] = "other"
        h = Harness([], assignment)
        self.assertEqual(await h.run(), "job_identity_mismatch")
        self.assertFalse(h.model_requests)


class ConfigTests(unittest.TestCase):
    def test_missing_credentials_fail_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(AgentError) as caught:
                Config.from_env()
            self.assertEqual(caught.exception.code, "missing_worker_token")

    def test_no_credentials_in_repr_or_http_model_endpoint(self):
        with patch.dict(os.environ, {"WORKER_TOKEN": "test-token", "NVIDIA_API_KEY": "test-key",
                                     "NVIDIA_BASE_URL": "http://remote/v1"}, clear=True):
            with self.assertRaises(AgentError):
                Config.from_env()
        self.assertNotIn("test-token", repr(Config("http://localhost", "test-token", "test-key")))

    def test_explicit_self_hosted_without_key_and_hosted_stays_protected(self):
        settings = {"WORKER_TOKEN": "test-token", "NVIDIA_BASE_URL": "http://127.0.0.1:8001/v1",
                    "NVIDIA_ALLOW_UNAUTHENTICATED_LOCAL": "true"}
        with patch.dict(os.environ, settings, clear=True):
            self.assertEqual(Config.from_env().api_key, "")
        settings["NVIDIA_BASE_URL"] = "https://integrate.api.nvidia.com/v1"
        with patch.dict(os.environ, settings, clear=True):
            with self.assertRaises(AgentError):
                Config.from_env()
        settings["NVIDIA_BASE_URL"] = "https://operator-configured.example/v1"
        settings["NVIDIA_ALLOW_UNAUTHENTICATED_SELF_HOSTED"] = "true"
        with patch.dict(os.environ, settings, clear=True):
            self.assertEqual(Config.from_env().api_key, "")

    def test_read_evidence_rejects_arbitrary_paths_and_cross_mode(self):
        for source in ["/hackathon/restricted/file", "../secrets", "task:visitor"]:
            with self.assertRaises(AgentError):
                read_evidence("real_place", [source], [source])


if __name__ == "__main__":
    unittest.main()
