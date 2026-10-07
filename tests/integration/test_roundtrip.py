"""Broker + real agent code integration; model replies are explicit HTTP stubs.

This verifies protocol integration, not NVIDIA inference or OpenShell isolation.
"""
import asyncio
import io
import json

import httpx
from PIL import Image

from agent.core import ModelSession
from agent.worker import WorkerAPI, handle_job
from service.main import create_app


def test_photo_tools_saved_card_roundtrip(tmp_path):
    async def scenario():
        app = create_app(tmp_path, worker_token="integration-only-token")
        service_transport = httpx.ASGITransport(app=app)
        provider_requests = []
        replies = [
            {"intent": "guide", "food_ids": ["samgyetang"], "needs_confirmation": False,
             "search_places": True, "source_ids": ["visitseoul:tosokchon", "visitkorea:tosokchon-menu"]},
            {"speech_text": "A listed restaurant is within your selected radius.",
             "menu_ids": ["samgyetang"], "claims": [], "conflicts": [], "itinerary": [],
             "unknowns": [], "next_question": None, "order_ko": "이 음식에 고기 육수가 들어가나요?"},
        ]

        def provider(request):
            payload = json.loads(request.content)
            provider_requests.append(payload)
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(replies.pop(0))}}]})

        async with httpx.AsyncClient(transport=service_transport, base_url="http://service/") as browser, \
                httpx.AsyncClient(transport=service_transport, base_url="http://service/",
                                  headers={"Authorization": "Bearer integration-only-token"}) as worker, \
                httpx.AsyncClient(transport=httpx.MockTransport(provider), base_url="https://stub-model.invalid/v1/") as model_client:
            sid = (await browser.post("api/sessions", json={})).json()["session_id"]
            photo = io.BytesIO()
            Image.new("RGB", (12, 12), "white").save(photo, format="PNG")
            uploaded = await browser.post("api/photos", files={"file": ("synthetic.png", photo.getvalue(), "image/png")})
            assert uploaded.status_code == 200
            body = {"schema_version": 1, "session_id": sid, "question": "Find samgyetang nearby.",
                    "photo_id": uploaded.json()["photo_id"], "dataset_mode": "real_place", "response_language": "en",
                    "location": {"lat": 37.579, "lng": 126.973, "origin": "selected"}, "radius_m": 1000,
                    "confirmed_food_id": "samgyetang", "confirmed_shop_id": None}
            submitted = await browser.post("api/requests", json=body)
            assert submitted.status_code == 202
            rid = submitted.json()["request_id"]
            api = WorkerAPI(worker)
            model = ModelSession(model_client, "explicit-http-stub")
            job = await api.claim()
            assert await handle_job(job, api, model) == "saved"
            response = (await browser.get(f"api/requests/{rid}")).json()
            assert response["status"] == "completed"
            assert response["result"]["places"][0]["place_id"] == "local:tosokchon"
            assert response["result"]["menus"][0]["name_ko"] == "삼계탕"
            assert response["result"]["request_id"] == rid
            assert "unverified" in response["result"]["speech_text"]
            assert (await browser.get(f"api/results/{rid}/download?format=json")).status_code == 200
            assert model.calls == 2
            assert len(provider_requests) == 2
            sent = json.dumps(provider_requests)
            assert "data:image/jpeg;base64," in sent
            assert "37.579" not in sent and "126.973" not in sent
            assert "integration-only-token" not in sent and sid not in sent

    asyncio.run(scenario())
