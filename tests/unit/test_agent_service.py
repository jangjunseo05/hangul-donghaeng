"""Actual FastAPI service + actual worker core; NVIDIA alone is an HTTP stub."""
import io
import tempfile
from pathlib import Path
import unittest

import httpx
from PIL import Image

from agent.core import ModelSession
from agent.worker import WorkerAPI, handle_job
from service.main import create_app
from test_agent import Harness, decision, draft, job


class AgentServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_culture_and_food_searches_save_with_exact_confirmation_fields(self):
        with tempfile.TemporaryDirectory(prefix="guide-culture-test-") as directory:
            app = create_app(Path(directory), worker_token="integration-test-token")
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test/") as browser, \
                    httpx.AsyncClient(transport=transport, base_url="http://test/",
                        headers={"Authorization": "Bearer integration-test-token"}) as service:
                sid = (await browser.post("/api/sessions", json={})).json()["session_id"]
                public = (await browser.get("/api/catalog")).json()
                self.assertEqual({p["kind"] for p in public["places"]}, {"restaurant", "heritage"})
                api = WorkerAPI(service)
                for confirmation_field in ("confirmed_place_id", "confirmed_shop_id"):
                    body = job()["request"]
                    body.update(session_id=sid, photo_id=None, question="Explain this palace and nearby food.")
                    body[confirmation_field] = "local:gyeongbokgung"
                    created = await browser.post("/api/requests", json=body)
                    self.assertEqual(created.status_code, 202)
                    selected = decision()
                    selected.update(intent="culture", food_ids=[], place_ids=["local:gyeongbokgung"],
                                    search_kinds=["heritage", "restaurant"])
                    answer = draft()
                    answer["claims"] = [{"text": "Gyeongbokgung was built in 1395.", "scope": "culture",
                                         "evidence_ids": ["visitseoul:gyeongbokgung-culture"]}]
                    stub = Harness([selected, answer])
                    assignment = await api.claim()
                    async with httpx.AsyncClient(base_url="https://model/v1/",
                            transport=httpx.MockTransport(stub.model)) as model:
                        self.assertEqual(await handle_job(assignment, api, ModelSession(model, "stub-test-model")), "saved")
                    result = (await browser.get(created.json()["poll_url"])).json()["result"]
                    self.assertEqual({p["place_id"] for p in result["places"]}, {"local:gyeongbokgung", "local:tosokchon"})
                    self.assertEqual(api.search_count, 2)
                    for field in ("confirmed_place_id", "confirmed_shop_id"):
                        self.assertEqual(result["scene"][field], body.get(field))

    async def test_photo_search_save_poll_and_download(self):
        with tempfile.TemporaryDirectory(prefix="guide-agent-test-") as directory:
            app = create_app(Path(directory), worker_token="integration-test-token")
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test/") as browser, \
                    httpx.AsyncClient(transport=transport, base_url="http://test/",
                        headers={"Authorization": "Bearer integration-test-token"}) as service:
                sid = (await browser.post("/api/sessions", json={})).json()["session_id"]
                image = io.BytesIO()
                Image.new("RGB", (16, 16), "white").save(image, "JPEG")
                photo = (await browser.post("/api/photos",
                    files={"file": ("synthetic-test.jpg", image.getvalue(), "image/jpeg")})).json()["photo_id"]
                body = job()["request"]
                body.update(session_id=sid, photo_id=photo)
                created = await browser.post("/api/requests", json=body)
                self.assertEqual(created.status_code, 202)
                request_id = created.json()["request_id"]
                api = WorkerAPI(service)
                assignment = await api.claim()
                self.assertEqual(assignment["request_id"], request_id)
                stub = Harness([decision(), draft()])
                async with httpx.AsyncClient(base_url="https://model/v1/",
                        transport=httpx.MockTransport(stub.model)) as model:
                    self.assertEqual(await handle_job(assignment, api, ModelSession(model, "stub-test-model")), "saved")
                polled = (await browser.get(f"/api/requests/{request_id}")).json()
                self.assertEqual(polled["status"], "completed")
                self.assertEqual(polled["result"]["places"][0]["place_id"], "local:tosokchon")
                for extension in ("json", "html", "md"):
                    response = await browser.get(f"/api/results/{request_id}/download?format={extension}")
                    self.assertEqual(response.status_code, 200)
                # Verify through the public route; storage directory details belong to the server.
                self.assertTrue(polled["result"]["evidence"])
                self.assertEqual(len(stub.model_requests), 2)

    async def test_fictional_result_saves_with_exact_approved_evidence(self):
        with tempfile.TemporaryDirectory(prefix="guide-agent-task-") as directory:
            app = create_app(Path(directory), worker_token="integration-test-token")
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test/") as browser, \
                    httpx.AsyncClient(transport=transport, base_url="http://test/",
                        headers={"Authorization": "Bearer integration-test-token"}) as service:
                sid = (await browser.post("/api/sessions", json={})).json()["session_id"]
                body = job("fictional_task")["request"]
                body["session_id"] = sid
                # Mode switches may retain an explicit confirmation. Echo each field
                # as contracted, without using it for real search or evidence.
                body["confirmed_place_id"] = "local:gyeongbokgung"
                body["confirmed_shop_id"] = "local:gyeongbokgung"
                created = await browser.post("/api/requests", json=body)
                self.assertEqual(created.status_code, 202)
                api = WorkerAPI(service)
                assignment = await api.claim()
                stub = Harness([decision("fictional_task"), draft("fictional_task")])
                async with httpx.AsyncClient(base_url="https://model/v1/",
                        transport=httpx.MockTransport(stub.model)) as model:
                    self.assertEqual(await handle_job(assignment, api, ModelSession(model, "stub-test-model")), "saved")
                result = (await browser.get(created.json()["poll_url"])).json()["result"]
                self.assertEqual(result["places"], [])
                self.assertEqual(result["scene"]["place_candidates"], [])
                self.assertEqual(result["scene"]["confirmed_place_id"], body["confirmed_place_id"])
                self.assertEqual(result["scene"]["confirmed_shop_id"], body["confirmed_shop_id"])
                self.assertEqual(api.search_count, 0)
                self.assertTrue(result["itinerary"])
                self.assertTrue(all(item["type"] == "example" for item in result["evidence"]))


if __name__ == "__main__":
    unittest.main()
