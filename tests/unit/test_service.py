"""Meaningful broker boundaries independent of live model availability."""
import io
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from service.main import create_app
from service import catalog

AUTH = {"Authorization": "Bearer test-worker-token"}


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path, worker_token="test-worker-token")


def session(client):
    return client.post("/api/sessions", json={}).json()["session_id"]


def request_body(sid, **changes):
    return {"schema_version": 1, "session_id": sid, "question": "Find this nearby",
            "photo_id": None, "dataset_mode": "real_place", "response_language": "en",
            "location": {"lat": 37.579, "lng": 126.973, "origin": "selected"}, "radius_m": 1000,
            "confirmed_food_id": "samgyetang", "confirmed_shop_id": None, **changes}


def new_job(client, sid, **changes):
    response = client.post("/api/requests", json=request_body(sid, **changes))
    assert response.status_code == 202, response.text
    return response.json()["request_id"]


def result(sid, rid, **changes):
    return {"schema_version": 1, "session_id": sid, "request_id": rid,
            "captured_at": datetime.now(timezone.utc).isoformat(), "dataset_mode": "real_place",
            "status": "need_confirmation", "speech_text": "Please confirm the food.", "response_language": "en",
            "scene": {"food_candidates": [], "confirmed_food_id": None, "confirmed_shop_id": None},
            "places": [], "menus": [], "claims": [], "evidence": [], "conflicts": [], "itinerary": [],
            "order_ko": None, "unknowns": [], "next_question": "Is this samgyetang?", "error_code": None, **changes}


def save(client, sid, rid, **changes):
    return client.post("/worker/results", headers=AUTH,
                       json={"session_id": sid, "request_id": rid, "result": result(sid, rid, **changes)})


def test_browser_and_worker_credentials_are_separate(app):
    with TestClient(app) as client:
        sid = session(client)
        assert client.get("/worker/jobs/next").status_code == 401
        assert client.post("/api/requests", json=request_body("someone-else")).status_code == 403
        assert client.get("/worker/jobs/next", headers=AUTH).status_code == 204


def test_cross_session_job_and_photo_are_denied(app):
    owner, other = TestClient(app), TestClient(app)
    sid = session(owner)
    other_sid = session(other)
    rid = new_job(owner, sid)
    assert other.get(f"/api/requests/{rid}").status_code == 404
    image = Image.new("RGB", (8, 8), "white")
    stream = io.BytesIO()
    image.save(stream, format="JPEG", exif=b"Exif\x00\x00private-metadata")
    uploaded = owner.post("/api/photos", files={"file": ("sample.jpg", stream.getvalue(), "image/jpeg")})
    assert uploaded.status_code == 200
    pid = uploaded.json()["photo_id"]
    assert other.post("/api/requests", json=request_body(other_sid, photo_id=pid)).status_code == 404
    normalized = app.state.store.photos[pid]["path"].read_bytes()
    assert b"private-metadata" not in normalized


def test_stale_result_cannot_save_or_replace_new_request(app):
    with TestClient(app) as client:
        sid = session(client)
        old = new_job(client, sid)
        assert client.get("/worker/jobs/next", headers=AUTH).json()["request_id"] == old
        current = new_job(client, sid, radius_m=2000)
        assert save(client, sid, old).status_code == 409
        assert not (app.state.store.output / old).exists()
        assert client.get("/worker/jobs/next", headers=AUTH).json()["request_id"] == current
        assert save(client, sid, current).status_code == 200
        saved = (app.state.store.output / current / "travel-card.json").read_bytes()
        assert save(client, sid, current).status_code == 409
        assert (app.state.store.output / current / "travel-card.json").read_bytes() == saved


def test_forged_coordinates_and_evidence_are_rejected(app):
    with TestClient(app) as client:
        sid = session(client)
        rid = new_job(client, sid)
        client.get("/worker/jobs/next", headers=AUTH)
        found = client.post("/worker/search", headers=AUTH, json={"session_id": sid, "request_id": rid,
                 "food_id": "samgyetang", "shop_id": None, "radius_m": 1000}).json()
        altered = {**found["places"][0], "lat": 0}
        assert save(client, sid, rid, places=[altered]).status_code == 422
        fake = {**catalog.evidence_for_mode("real_place")[0], "source": "https://fake.example"}
        assert save(client, sid, rid, evidence=[fake]).status_code == 422
        assert not (app.state.store.output / rid).exists()


def test_correct_result_is_downloadable_only_by_owner(app):
    client, other = TestClient(app), TestClient(app)
    sid = session(client)
    session(other)
    rid = new_job(client, sid)
    client.get("/worker/jobs/next", headers=AUTH)
    assert save(client, sid, rid, speech_text="<script>alert(1)</script>").status_code == 200
    html = client.get(f"/api/results/{rid}/download?format=html")
    assert html.status_code == 200 and "&lt;script&gt;" in html.text
    assert "<script>" not in html.text
    assert other.get(f"/api/results/{rid}/download").status_code == 404


def test_timeout_and_search_limits(app):
    with TestClient(app) as client:
        sid = session(client)
        rid = new_job(client, sid)
        client.get("/worker/jobs/next", headers=AUTH)
        body = {"session_id": sid, "request_id": rid, "food_id": "samgyetang", "shop_id": None, "radius_m": 1000}
        assert client.post("/worker/search", headers=AUTH, json={**body, "radius_m": 3000}).status_code == 422
        assert client.post("/worker/search", headers=AUTH, json=body).status_code == 200
        assert client.post("/worker/search", headers=AUTH, json=body).status_code == 200
        assert client.post("/worker/search", headers=AUTH, json=body).status_code == 429
        app.state.store.jobs[rid]["created"] -= 31
        assert client.get(f"/api/requests/{rid}").json()["status"] == "failed"
        assert save(client, sid, rid).status_code == 409


def test_origin_and_fictional_search_boundary(app):
    with TestClient(app) as client:
        assert client.post("/api/sessions", json={}, headers={"Origin": "https://evil.example"}).status_code == 403
        sid = session(client)
        rid = new_job(client, sid, dataset_mode="fictional_task")
        client.get("/worker/jobs/next", headers=AUTH)
        assert client.post("/worker/search", headers=AUTH, json={"session_id": sid, "request_id": rid,
               "food_id": "samgyetang", "shop_id": None, "radius_m": 1000}).status_code == 403


def test_expired_sessions_release_capacity_and_private_photos(app):
    from service.main import Session
    client = TestClient(app)
    sid = session(client)
    rid = new_job(client, sid)
    stream = io.BytesIO()
    Image.new("RGB", (8, 8)).save(stream, format="JPEG")
    pid = client.post("/api/photos", files={"file": ("sample.jpg", stream.getvalue(), "image/jpeg")}).json()["photo_id"]
    path = app.state.store.photos[pid]["path"]
    for index in range(63):
        app.state.store.sessions[f"expired-{index}"] = Session(id=f"expired-{index}")
    for entry in app.state.store.sessions.values():
        entry.last_seen -= 3601
    assert len(app.state.store.sessions) == 64
    response = client.post("/api/sessions", json={})
    assert response.status_code == 200 and response.json()["session_id"] != sid
    assert len(app.state.store.sessions) == 1
    assert rid not in app.state.store.jobs and pid not in app.state.store.photos
    assert not path.exists()


def test_session_creation_rate_limit_does_not_block_existing_session(app):
    client = TestClient(app)
    for _ in range(10):
        client.cookies.clear()
        assert client.post("/api/sessions", json={}).status_code == 200
    assert client.post("/api/sessions", json={}).status_code == 200
    client.cookies.clear()
    assert client.post("/api/sessions", json={}).status_code == 429
    assert len(app.state.store.sessions) == 10


def test_dataset_switch_clears_conversation_context(app):
    client = TestClient(app)
    sid = session(client)
    first = new_job(client, sid, dataset_mode="fictional_task")
    client.get("/worker/jobs/next", headers=AUTH)
    assert save(client, sid, first, dataset_mode="fictional_task", speech_text="FICTIONAL_ONLY_FACT").status_code == 200
    same_mode = new_job(client, sid, dataset_mode="fictional_task")
    assert "FICTIONAL_ONLY_FACT" in json.dumps(app.state.store.jobs[same_mode]["history"])
    real = new_job(client, sid, dataset_mode="real_place")
    assert app.state.store.jobs[real]["history"] == []


def test_human_readable_card_preserves_reasoning_and_citations():
    from service.render import markdown_card, html_card
    card = result("session", "request", claims=[{"text": "CULTURE_FACT", "scope": "culture", "evidence_ids": ["source-a"]}],
                  conflicts=[{"decision": "CONFLICT_DECISION", "reason": "VISIT_DATE_REASON", "evidence_ids": ["source-a", "source-b"]}],
                  next_question="CONFIRM_INGREDIENTS")
    for rendered in (markdown_card(card), html_card(card)):
        for required in ("CULTURE_FACT", "CONFLICT_DECISION", "VISIT_DATE_REASON", "source-a", "source-b", "CONFIRM_INGREDIENTS"):
            assert required in rendered


def test_chunked_oversized_body_rejected_before_validation(app):
    client = TestClient(app)
    sid = session(client)
    payload = json.dumps(request_body(sid, question="x" * 300000)).encode()
    response = client.post("/api/requests", content=iter([payload[:100000], payload[100000:]]),
                           headers={"Content-Type": "application/json"})
    assert "content-length" not in response.request.headers
    assert response.status_code == 413
    assert response.json()["error_code"] == "BODY_TOO_LARGE"
