"""Phase 2 broker routes with mocked OSM/Wikipedia/TTS; no network, GPU or model."""
import io
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from service import nearby, tts, wiki
from service.main import create_app

WORKER = {"Authorization": "Bearer test-worker-token"}
SEOCHON = (37.579, 126.973)
OSM_HALL = {"place_id": "osm:way:77", "name": "예시 전각", "name_en": "Example Hall", "kind": "landmark",
            "category": "historic=building", "lat": 37.5795, "lng": 126.9735, "distance_m": 70.0,
            "source_id": "osm:way:77", "osm_url": "https://www.openstreetmap.org/way/77",
            "wikidata": "Q1", "wikipedia": None}
OSM_PALACE_TWIN = {**OSM_HALL, "place_id": "osm:way:78", "source_id": "osm:way:78", "name": "경복궁",
                   "name_en": "Gyeongbokgung", "lat": 37.5760, "lng": 126.9768, "distance_m": 400.0}


def evidence(place):
    return {"id": place["place_id"], "source": place["osm_url"], "as_of": "2026-10-27T00:00:00+00:00",
            "type": "document", "dataset_id": "real_place"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    places = [OSM_HALL, OSM_PALACE_TWIN]
    monkeypatch.setattr(nearby, "search_nearby", lambda **kwargs: {
        "places": [dict(p) for p in places], "evidence": [evidence(p) for p in places], "error_code": None})
    with TestClient(create_app(tmp_path, worker_token="test-worker-token")) as test_client:
        test_client.post("/api/sessions", json={})
        yield test_client


def sid(client):
    return client.post("/api/sessions", json={}).json()["session_id"]


def jpeg():
    image = io.BytesIO()
    Image.new("RGB", (16, 16), "white").save(image, "JPEG")
    return image.getvalue()


def request_body(session_id, **changes):
    return {"schema_version": 1, "session_id": session_id, "question": "Tell me about this place.",
            "photo_id": None, "dataset_mode": "real_place", "response_language": "en",
            "location": {"lat": SEOCHON[0], "lng": SEOCHON[1], "origin": "selected"}, "radius_m": 1000,
            "confirmed_food_id": None, "confirmed_shop_id": None, **changes}


def test_nearby_merges_catalog_drops_osm_twins_and_requires_session(tmp_path, client):
    assert TestClient(create_app(tmp_path / "x", worker_token="t")).get(
        "/api/nearby", params={"tab": "landmark", "lat": 37.579, "lng": 126.973}).status_code == 401
    response = client.get("/api/nearby", params={"tab": "landmark", "lat": 37.579, "lng": 126.973, "radius_m": 1000})
    assert response.status_code == 200, response.text
    body = response.json()
    ids = [place["place_id"] for place in body["places"]]
    assert "osm:way:77" in ids and "osm:way:78" not in ids  # same-name twin of the catalog palace
    assert {"local:gyeongbokgung", "local:gwanghwamun", "local:geunjeongjeon", "local:gyeonghoeru"} <= set(ids)
    assert [place["distance_m"] for place in body["places"]] == sorted(place["distance_m"] for place in body["places"])
    palace = next(place for place in body["places"] if place["place_id"] == "local:gyeongbokgung")
    assert palace["has_card"] is True and palace["kind"] == "landmark"
    assert [item["id"] for item in body["evidence"]] == ["osm:way:77"]
    assert body["attribution"].startswith("© OpenStreetMap")
    assert client.get("/api/nearby", params={"tab": "landmark", "lat": 37.5, "lng": 127, "radius_m": 750}).status_code == 422
    assert client.get("/api/nearby", params={"tab": "hotel", "lat": 37.5, "lng": 127}).status_code == 422


def test_food_tab_lists_catalog_restaurant(client):
    body = client.get("/api/nearby", params={"tab": "food", "lat": 37.579, "lng": 126.973, "lang": "ko"}).json()
    assert body["places"][0]["place_id"] in {"local:tosokchon", "osm:way:77"}
    assert any(place["place_id"] == "local:tosokchon" for place in body["places"])
    assert "평점" in body["unknowns"][0]


def test_only_issued_external_ids_can_be_confirmed(client):
    session_id = sid(client)
    body = request_body(session_id, confirmed_place_id="osm:way:77")
    assert client.post("/api/requests", json=body).status_code == 422
    client.get("/api/nearby", params={"tab": "landmark", "lat": 37.579, "lng": 126.973})
    created = client.post("/api/requests", json=body)
    assert created.status_code == 202, created.text
    assignment = client.get("/worker/jobs/next", headers=WORKER).json()
    assert assignment["confirmed_external_place"] == {"place_id": "osm:way:77", "name": "예시 전각",
        "name_en": "Example Hall", "kind": "landmark", "category": "historic=building"}
    assert client.post("/api/requests", json=request_body(session_id, confirmed_place_id="osm:way:999")).status_code == 422


def test_catalog_card_route_recomputes_labels_and_hides_quotes(client):
    card = client.get("/api/landmarks/local:gyeongbokgung/card", params={"lang": "en"}).json()
    assert card["blocks"]["what_it_is"]["verification"] == "catalog"  # v2: KHS official record
    assert card["blocks"]["what_to_look_for"]["verification"] == "public_source"  # cites wikipedia:gyeongbokgung
    assert card["verification"] == "public_source"
    assert card["visit_note"]["as_of"]  # dated operation note
    assert client.get("/api/landmarks/local:geunjeongjeon/card").json()["verification"] == "catalog"
    wiki_source = next(source for source in card["sources"] if source["id"] == "wikipedia:gyeongbokgung")
    assert wiki_source["license"].startswith("CC BY-SA 4.0") and wiki_source["title"] == "Gyeongbokgung"
    raw = json.dumps(card, ensure_ascii=False)
    assert "quotes" not in raw and "quote_capture" not in raw
    assert client.get("/api/landmarks/local:tosokchon/card").status_code == 404
    assert client.get("/api/landmarks/osm:way:77/card").json()["error_code"] == "CARD_NOT_FOUND"


def test_routes_are_deterministic_near_filtered_and_note_bukchon_restriction(client):
    body = client.get("/api/routes", params={"near": "37.579,126.973", "lang": "en"}).json()
    assert [route["route_id"] for route in body["routes"]] == ["route:palace-in-a-nutshell", "route:palace-to-hanok"]
    first, second = body["routes"]
    assert first["total_straight_line_m"] == 891 and second["total_straight_line_m"] == 1057
    assert all(leg["route_verified"] is False for route in body["routes"] for leg in route["legs"])
    assert first["visit_note"] is None
    assert second["visit_note"]["evidence_ids"] == ["visitkorea:bukchon-operation", "seoul:bukchon-visit-restriction"]
    assert second["visit_note"]["as_of"] == "2024-11-15"
    assert "2024" in second["visit_note"]["text"] and "2024" in second["ui_note"]
    assert client.get("/api/routes", params={"near": "48.85,2.35"}).json()["routes"] == []
    assert client.get("/api/routes", params={"near": "north"}).status_code == 422
    assert client.get("/api/routes", params={"near": "91,0"}).status_code == 422
    ko = client.get("/api/routes", params={"lang": "ko"}).json()
    assert ko["routes"][0]["stops"][3]["note"].startswith("점심")


def test_observe_frames_skip_photo_limit_ring_of_two_and_delete_after_job(client):
    session_id = sid(client)
    frames = [client.post("/api/photos", files={"file": ("f.jpg", jpeg(), "image/jpeg")},
                          data={"purpose": "observe"}).json() for _ in range(3)]
    assert all(frame["purpose"] == "observe" for frame in frames)
    store = client.app.state.store
    assert frames[0]["photo_id"] not in store.photos  # evicted by the ring
    assert client.post("/api/requests", json=request_body(session_id, photo_id=frames[0]["photo_id"],
                                                          interaction_mode="observe")).status_code == 404
    path = store.photos[frames[2]["photo_id"]]["path"]
    created = client.post("/api/requests", json=request_body(session_id, photo_id=frames[2]["photo_id"],
                                                              interaction_mode="observe")).json()
    rid = created["request_id"]
    client.get("/worker/jobs/next", headers=WORKER)
    assert client.get(f"/worker/photos/{frames[2]['photo_id']}", params={"request_id": rid}, headers=WORKER).status_code == 200
    assert client.post("/worker/progress", headers=WORKER, json={"session_id": session_id, "request_id": rid,
                                                                  "stage": "matching"}).status_code == 200
    assert client.get(created["poll_url"]).json()["stage"] == "matching"
    assert client.post("/worker/progress", headers=WORKER, json={"session_id": session_id, "request_id": rid,
                                                                  "stage": "dreaming"}).status_code == 422
    client.post("/worker/fail", headers=WORKER, json={"session_id": session_id, "request_id": rid,
                                                      "error_code": "model_timeout", "detail": ""})
    status = client.get(created["poll_url"]).json()
    assert status["status"] == "failed" and status["stage"] is None
    assert not path.exists() and frames[2]["photo_id"] not in store.photos
    captures = [client.post("/api/photos", files={"file": ("c.jpg", jpeg(), "image/jpeg")}) for _ in range(20)]
    assert all(response.status_code == 200 for response in captures)
    assert client.post("/api/photos", files={"file": ("c.jpg", jpeg(), "image/jpeg")}).status_code == 429
    assert client.post("/api/photos", files={"file": ("f.jpg", jpeg(), "image/jpeg")},
                       data={"purpose": "observe"}).status_code == 200


def test_landmark_candidates_are_issued_and_bound_to_observation_results(client):
    session_id = sid(client)
    rid = client.post("/api/requests", json=request_body(session_id, interaction_mode="observe")).json()["request_id"]
    client.get("/worker/jobs/next", headers=WORKER)
    search = {"session_id": session_id, "request_id": rid, "food_id": None, "shop_id": None,
              "radius_m": 1000, "kind": "landmark", "live": True}
    assert client.post("/worker/search", headers=WORKER, json={**search, "live": False}).status_code == 422
    found = client.post("/worker/search", headers=WORKER, json=search).json()
    ids = [item["id"] for item in found["candidates"]]
    assert len(ids) == 5 and ids[0] == "osm:way:77"
    assert {item["source"] for item in found["candidates"]} == {"catalog", "osm"}
    base = {"schema_version": 1, "session_id": session_id, "request_id": rid,
            "captured_at": "2026-10-27T00:00:00+00:00", "dataset_mode": "real_place", "status": "need_confirmation",
            "speech_text": "This may be Example Hall.", "response_language": "en",
            "scene": {"food_candidates": [], "confirmed_food_id": None, "confirmed_shop_id": None,
                      "place_candidates": [{"id": "local:gwanghwamun", "name_ko": "광화문", "name_en": "Gwanghwamun Gate"}],
                      "confirmed_place_id": None, "observed_place_name": "Gwanghwamun Gate",
                      "observed_place_source": "osm"},
            "places": [], "menus": [], "claims": [], "evidence": [], "conflicts": [], "itinerary": [],
            "order_ko": None, "unknowns": [], "next_question": "Is this the place?", "error_code": None}
    wrong = client.post("/worker/results", headers=WORKER, json={"session_id": session_id, "request_id": rid, "result": base})
    assert wrong.status_code == 422 and wrong.json()["error_code"] == "INVALID_OBSERVATION"
    base["scene"]["observed_place_source"] = "catalog"
    saved = client.post("/worker/results", headers=WORKER, json={"session_id": session_id, "request_id": rid, "result": base})
    assert saved.status_code == 200, saved.text
    assert "osm:way:77" in client.app.state.store.sessions[client.cookies["guide_session"]].issued_places


def test_tts_unconfigured_is_503_and_rejects_plain_http_to_remote_hosts(client, monkeypatch):
    monkeypatch.delenv("TTS_BASE_URL", raising=False)
    assert client.post("/api/tts", json={"text": "안녕하세요", "lang": "ko"}).json()["error_code"] == "TTS_UNAVAILABLE"
    monkeypatch.setenv("TTS_BASE_URL", "http://203.0.113.5:9000")
    assert client.post("/api/tts", json={"text": "안녕하세요", "lang": "ko"}).status_code == 503


VOICES = {"en-US,ko-KR": {"voices": ["Magpie-Multilingual.KO-KR.Aria", "Magpie-Multilingual.EN-US.Mia.Calm"]}}


def form_fields(request) -> dict:
    """Parse the multipart body the broker sends (NIM reference: multipart/form-data)."""
    assert request.headers["content-type"].startswith("multipart/form-data; boundary=")
    boundary = request.headers["content-type"].split("boundary=")[1].encode()
    fields = {}
    for part in request.content.split(b"--" + boundary)[1:-1]:
        head, _, body = part.strip(b"\r\n").partition(b"\r\n\r\n")
        name = head.decode().split('name="')[1].split('"')[0]
        fields[name] = body.decode()
    return fields


def tts_server(seen, voices=VOICES):
    def handler(request):
        if request.url.path == "/v1/audio/list_voices":
            return httpx.Response(200, json=voices)
        seen.append(request)
        if b"broken" in request.content:
            return httpx.Response(500, text="upstream detail")
        return httpx.Response(200, content=b"RIFFfakewav", headers={"content-type": "audio/wav"})
    return handler


def test_tts_proxies_fixed_voice_caches_and_falls_back_on_upstream_error(client, monkeypatch):
    seen = []

    def handler(request):
        if request.url.path == "/v1/audio/list_voices":
            return httpx.Response(200, json=VOICES)
        seen.append(request)
        if b"broken" in request.content:
            return httpx.Response(500, text="upstream detail")
        return httpx.Response(200, content=b"RIFFfakewav", headers={"content-type": "audio/wav"})

    monkeypatch.setenv("TTS_BASE_URL", "http://127.0.0.1:9000")
    monkeypatch.setenv("TTS_VOICE_KO", "Magpie-Multilingual.KO-KR.Aria")
    monkeypatch.setattr(tts, "_TRANSPORT", httpx.MockTransport(handler))
    tts._CACHE.clear()
    tts._VOICES.clear()
    response = client.post("/api/tts", json={"text": "경복궁에 오신 걸 환영해요!", "lang": "ko"})
    assert response.status_code == 200 and response.content == b"RIFFfakewav"
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["x-tts-voice"] == "Magpie-Multilingual.KO-KR.Aria"
    fields = form_fields(seen[0])
    assert seen[0].url.path == "/v1/audio/synthesize"
    assert fields == {"text": "경복궁에 오신 걸 환영해요!", "language": "ko-KR", "voice": "Magpie-Multilingual.KO-KR.Aria"}
    assert client.post("/api/tts", json={"text": "경복궁에 오신 걸 환영해요!", "lang": "ko"}).status_code == 200
    assert len(seen) == 1  # cached
    failed = client.post("/api/tts", json={"text": "broken", "lang": "ko"})
    assert failed.status_code == 503 and "upstream" not in failed.text
    tts._CACHE.clear()


def test_tts_unlisted_voice_falls_back_to_model_default(client, monkeypatch):
    seen = []
    monkeypatch.setenv("TTS_BASE_URL", "http://127.0.0.1:9000")
    monkeypatch.setenv("TTS_VOICE_EN", "Magpie-Multilingual.EN-US.Nobody")
    monkeypatch.setattr(tts, "_TRANSPORT", httpx.MockTransport(tts_server(seen)))
    tts._CACHE.clear()
    tts._VOICES.clear()
    response = client.post("/api/tts", json={"text": "Hello there.", "lang": "en"})
    assert response.status_code == 200 and response.headers["x-tts-voice"] == "default"
    assert "voice" not in form_fields(seen[0])
    tts._CACHE.clear()
    tts._VOICES.clear()


def test_tts_single_flight_per_session(monkeypatch):
    monkeypatch.setenv("TTS_BASE_URL", "http://127.0.0.1:9000")
    tts._ACTIVE_SESSIONS.add("busy-session")
    try:
        with pytest.raises(tts.TtsBusy):
            tts.synthesize("hello", "en", "busy-session")
    finally:
        tts._ACTIVE_SESSIONS.discard("busy-session")


def test_tts_speaks_text_without_brackets(client, monkeypatch):
    seen = []
    monkeypatch.setenv("TTS_BASE_URL", "http://127.0.0.1:9000")
    monkeypatch.delenv("TTS_VOICE_KO", raising=False)
    monkeypatch.setattr(tts, "_TRANSPORT", httpx.MockTransport(tts_server(seen)))
    tts._CACHE.clear()
    assert client.post("/api/tts", json={"text": "앞마당의 품계석(관리들이 설 자리 표시)을 찾아보세요.", "lang": "ko"}).status_code == 200
    assert form_fields(seen[0])["text"] == "앞마당의 품계석을 찾아보세요."
    assert client.post("/api/tts", json={"text": "()", "lang": "ko"}).status_code == 503
    tts._CACHE.clear()


def test_speakable_turns_free_standing_brackets_into_asides():
    assert tts.speakable("Plan Bukchon (Bukchon-ro 11-gil; re-check).") == "Plan Bukchon, Bukchon-ro 11-gil; re-check."
    assert tts.speakable("방문하세요(북촌로11길, 재확인 필요).") == "방문하세요, 북촌로11길, 재확인 필요."
    assert tts.speakable("No brackets here.") == "No brackets here."


def test_research_merge_is_idempotent(tmp_path):
    import shutil
    from infra.merge_research_content import merge
    root = Path(__file__).resolve().parents[2]
    pack = root.parent / ".orchestra" / "research" / "content"
    if not pack.exists():
        pytest.skip("research pack is outside this checkout")
    (tmp_path / "data").mkdir()
    for name in ("evidence.json", "catalog.json", "cards.json", "routes.json"):
        shutil.copy(root / "data" / name, tmp_path / "data" / name)
    before = {name: (tmp_path / "data" / name).read_bytes() for name in ("evidence.json", "catalog.json")}
    merge(pack, tmp_path)
    merge(pack, tmp_path)
    after = {name: (tmp_path / "data" / name).read_bytes() for name in ("evidence.json", "catalog.json")}
    assert after == before  # data/ already holds the current pack


def test_tts_wraps_escaped_text_in_ssml_pitch_and_keys_cache_by_pitch(client, monkeypatch):
    seen = []
    monkeypatch.setenv("TTS_BASE_URL", "http://127.0.0.1:9100")
    monkeypatch.setenv("TTS_VOICE_EN", "Magpie-Multilingual.EN-US.Mia.Calm")
    monkeypatch.setenv("TTS_SSML_PITCH", "x-high")
    monkeypatch.setattr(tts, "_TRANSPORT", httpx.MockTransport(tts_server(seen)))
    tts._CACHE.clear()
    tts._VOICES.clear()
    text = 'Tom & Jerry <b> say "hi" (twice).'
    assert client.post("/api/tts", json={"text": text, "lang": "en"}).status_code == 200
    assert form_fields(seen[0])["text"] == (
        '<speak><prosody pitch="x-high">Tom &amp; Jerry &lt;b&gt; say &quot;hi&quot;, twice.</prosody></speak>')
    monkeypatch.setenv("TTS_SSML_PITCH", "")
    assert client.post("/api/tts", json={"text": text, "lang": "en"}).status_code == 200
    assert len(seen) == 2 and form_fields(seen[1])["text"] == 'Tom & Jerry <b> say "hi", twice.'
    monkeypatch.setenv("TTS_SSML_PITCH", "+2st")  # rejected by Magpie (400): never forwarded
    assert client.post("/api/tts", json={"text": text, "lang": "en"}).status_code == 200
    assert len(seen) == 2  # same as plain text: served from cache
    tts._CACHE.clear()
    tts._VOICES.clear()
